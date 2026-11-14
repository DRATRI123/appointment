"""Notifications: event → recipients → rendered messages in an outbox → delivery by the worker.

* ``emit`` never raises into the business flow: a template or address problem is logged, the booking still succeeds.
* Messages are written to ``notifications`` in the same transaction as the change that caused them (outbox),
  so nothing is sent for work that was rolled back. ``dispatch_due`` (worker) delivers them with retries.
* Customer preferences are honoured: email/SMS on by default, WhatsApp only after explicit opt-in.
* Reminders are created by ``schedule_reminders`` and re-checked right before sending, so a cancelled or
  rescheduled appointment never gets a stale reminder.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AppointmentStatus
from app.core.enums import NotificationStatus as S
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models import (
    Appointment,
    Branch,
    Customer,
    Notification,
    NotificationLog,
    NotificationTemplate,
    Organization,
    OrganizationMembership,
    Payment,
    PaymentRefund,
    PaymentSubmission,
    Professional,
    Service,
    User,
)
from app.notifications.catalog import CHANNELS, CUSTOMER, EVENTS, SAMPLE_VALUES, STAFF_RECIPIENT_PERMISSION, Event
from app.notifications.providers import OutboundMessage, get_provider, provider_status
from app.notifications.render import email_html, placeholders, render, single_line
from app.schemas.notification import (
    EventInfo,
    Inbox,
    InboxItem,
    NotificationDetail,
    NotificationLogRead,
    NotificationRead,
    NotificationStats,
    Preferences,
    PreviewResponse,
    ProviderStatus,
    TemplateRead,
    TemplateUpsert,
)
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService

log = get_logger(__name__)
DELIVERABLE = ("email", "sms", "whatsapp")
REMINDER_STATUSES = (AppointmentStatus.CONFIRMED,)


# ------------------------------------------------------------------ format
def inr(paise: int | None) -> str:
    if paise is None:
        return ""
    rupees, p = divmod(abs(int(paise)), 100)
    s = str(rupees)
    if len(s) > 3:  # Indian grouping: 1,23,45,678
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if paise < 0 else ''}₹{s}.{p:02d}"


def _local(dt: datetime | None, tz: str | None) -> datetime | None:
    if dt is None:
        return None
    try:
        return dt.astimezone(ZoneInfo(tz or "Asia/Kolkata"))
    except Exception:  # noqa: BLE001 - bad tz name falls back to IST
        return dt.astimezone(ZoneInfo("Asia/Kolkata"))


def fmt_date(dt: datetime | None, tz: str | None) -> str:
    d = _local(dt, tz)
    return d.strftime("%a, %d %b %Y") if d else ""


def fmt_time(dt: datetime | None, tz: str | None) -> str:
    d = _local(dt, tz)
    return d.strftime("%I:%M %p").lstrip("0").lower() if d else ""


def _address(addr: dict | None) -> str:
    if not addr:
        return ""
    keys = ("line1", "line2", "area", "city", "state", "pincode", "postal_code")
    parts = [str(addr[k]).strip() for k in keys if addr.get(k)]
    return ", ".join(parts) if parts else ", ".join(str(v) for v in addr.values() if isinstance(v, str) and v.strip())


def sms_segments(text: str) -> int:
    gsm = all(ord(c) < 128 for c in text)
    single, multi = (160, 153) if gsm else (70, 67)
    return 1 if len(text) <= single else -(-len(text) // multi)


class NotificationService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # ------------------------------------------------------------ settings
    def settings(self) -> dict[str, Any]:
        return OrganizationService(self.db).get_settings(self.org, "notification")["notification"]

    def channel_enabled(self, channel: str, cfg: dict | None = None) -> bool:
        cfg = cfg or self.settings()
        return bool(cfg.get(f"{channel}_enabled", channel == "in_app"))

    def event_channels(self, event: Event, cfg: dict | None = None) -> tuple[bool, list[str]]:
        cfg = cfg or self.settings()
        override = (cfg.get("events") or {}).get(event.code) or {}
        enabled = bool(override.get("enabled", True))
        if event.code == "staff.new_booking" and not cfg.get("notify_staff_on_booking", True):
            enabled = False
        channels = [c for c in (override.get("channels") or event.default_channels) if c in CHANNELS]
        return enabled, channels

    # ------------------------------------------------------------ templates
    def _custom(self, event: str, channel: str) -> NotificationTemplate | None:
        return self.db.scalar(select(NotificationTemplate).where(NotificationTemplate.organization_id == self.org.id, NotificationTemplate.event == event,
                                                                 NotificationTemplate.channel == channel))

    def template(self, event: Event, channel: str) -> tuple[str | None, str, str | None]:
        row = self._custom(event.code, channel)
        if row is not None and row.is_active:
            return row.subject, row.body, row.provider_template_id
        default = event.templates[channel]
        return default.subject, default.body, row.provider_template_id if row is not None else None

    # ------------------------------------------------------------ context
    def appointment_context(self, appt: Appointment) -> dict[str, str]:
        svc = self.db.get(Service, appt.service_id)
        pro = self.db.get(Professional, appt.professional_id)
        branch = self.db.get(Branch, appt.branch_id)
        cust = self.db.get(Customer, appt.customer_id)
        token = (appt.metadata_ or {}).get("access_token")
        link = f"{get_settings().frontend_url.rstrip('/')}/o/{self.org.slug}/appointments/{appt.reference}" + (f"?t={token}" if token else "")
        meeting = appt.meeting_link if appt.consultation_mode == "online" else ""
        return {
            "customer_name": cust.full_name if cust else "", "customer_mobile": (cust.mobile or "") if cust else "", "organization_name": self.org.name,
            "organization_phone": self.org.phone or (branch.phone if branch and branch.phone else "") or "", "service_name": svc.name if svc else "",
            "professional_name": pro.display_name if pro else "", "branch_name": branch.name if branch else "", "branch_address": _address(branch.address) if branch else "",
            "appointment_date": fmt_date(appt.start_at, appt.timezone), "appointment_time": fmt_time(appt.start_at, appt.timezone),
            "appointment_reference": appt.reference, "manage_link": link, "payment_link": link, "amount_due": inr(max(0, appt.advance_due_paise - (appt.paid_amount_paise or 0))),
            "amount_paid": inr(appt.paid_amount_paise or 0), "payment_deadline": f"{fmt_date(appt.payment_due_at, appt.timezone)}, {fmt_time(appt.payment_due_at, appt.timezone)}" if appt.payment_due_at else "",
            "meeting_link": meeting or "", "status": appt.status.replace("_", " "),
        }

    # ------------------------------------------------------------ recipients
    def _customer_address(self, cust: Customer, channel: str, event: str) -> tuple[str | None, str | None]:
        """Returns (address, skip_reason). Preferences: email/sms default on, WhatsApp needs opt-in, reminders can be turned off."""
        prefs = cust.communication_preferences or {}
        if event == "appointment.reminder" and prefs.get("reminders") is False:
            return None, "customer turned off reminders"
        if channel == "email":
            return (cust.email, None) if cust.email and prefs.get("email", True) else (None, "no email or email turned off")
        if channel == "sms":
            return (cust.mobile, None) if cust.mobile and prefs.get("sms", True) else (None, "no mobile or SMS turned off")
        if channel == "whatsapp":
            return (cust.mobile, None) if cust.mobile and prefs.get("whatsapp") is True else (None, "no WhatsApp opt-in")
        return None, None

    def staff_recipients(self, event: str, appt: Appointment | None) -> list[User]:
        perm = STAFF_RECIPIENT_PERMISSION.get(event)
        if not perm:
            return []
        rows = self.db.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id == self.org.id, OrganizationMembership.status == "active")).all()
        pro = self.db.get(Professional, appt.professional_id) if appt else None
        out: list[User] = []
        for m in rows:
            codes = {p.code for p in m.role.permissions}
            if m.branch_id and appt and m.branch_id != appt.branch_id:
                continue
            if perm in codes and (perm != "appointments:write" or "appointments:read" in codes or (pro is not None and pro.user_id == m.user_id)):
                if self.actor is not None and m.user_id == self.actor.id:
                    continue  # do not notify people about what they just did themselves
                out.append(m.user)
        return out

    # ------------------------------------------------------------ emit
    def emit(self, code: str, *, appointment: Appointment | None = None, payment: Payment | None = None, refund: PaymentRefund | None = None,
             extra: dict[str, str] | None = None, scheduled_for: datetime | None = None, dedupe: str | None = None) -> list[Notification]:
        try:
            with self.db.begin_nested():
                return self._emit(code, appointment=appointment, payment=payment, refund=refund, extra=extra or {}, scheduled_for=scheduled_for, dedupe=dedupe)
        except Exception:  # noqa: BLE001 - notifications must never break the business transaction
            log.exception("notification.emit_failed", event=code, organization=self.org.id)
            return []

    def _emit(self, code: str, *, appointment, payment, refund, extra, scheduled_for, dedupe) -> list[Notification]:
        event = EVENTS[code]
        cfg = self.settings()
        enabled, channels = self.event_channels(event, cfg)
        if not enabled:
            return []
        values = self.appointment_context(appointment) if appointment is not None else {"organization_name": self.org.name, "organization_phone": self.org.phone or ""}
        if payment is not None:
            values["payment_reference"] = payment.reference
            values["amount_due"] = inr(payment.amount_paise)
            if payment.verified_amount_paise:
                values["amount_paid"] = inr(payment.verified_amount_paise)
            utr = self.db.scalar(select(PaymentSubmission.utr).where(PaymentSubmission.payment_id == payment.id, PaymentSubmission.is_superseded.is_(False)).order_by(PaymentSubmission.id.desc()))
            values["utr"] = utr or ""
        if refund is not None:
            values.update({"refund_amount": inr(refund.amount_paise), "refund_reference": refund.refund_reference or "",
                           "refund_method": {"upi": "UPI", "bank_transfer": "bank transfer", "cash": "cash"}.get(refund.refund_method or "", refund.refund_method or ""),
                           "reason": refund.reason or ""})
        values.update({k: v for k, v in extra.items() if v is not None})
        created: list[Notification] = []
        if event.audience == CUSTOMER:
            cust = self.db.get(Customer, appointment.customer_id) if appointment is not None else (self.db.get(Customer, payment.customer_id) if payment is not None and payment.customer_id else None)
            if cust is None:
                return []
            for ch in channels:
                if ch == "in_app":
                    if cust.user_id and self.channel_enabled("in_app", cfg):
                        _add(created, self._create(event, ch, values, user_id=cust.user_id, customer=cust, address=None, appointment=appointment, payment=payment,
                                                    scheduled_for=scheduled_for, dedupe=dedupe, link="/customer/appointments"))
                    continue
                if not self.channel_enabled(ch, cfg):
                    continue
                address, _skip = self._customer_address(cust, ch, code)
                if address:
                    _add(created, self._create(event, ch, values, user_id=None, customer=cust, address=address, appointment=appointment, payment=payment,
                                                scheduled_for=scheduled_for, dedupe=dedupe))
        else:
            link = {"staff.payment_to_verify": "/admin/payments/verification", "staff.refund_requested": "/admin/refunds"}.get(code, "/admin/appointments")
            for user in self.staff_recipients(code, appointment):
                for ch in channels:
                    if ch == "in_app":
                        if self.channel_enabled("in_app", cfg):
                            _add(created, self._create(event, ch, values, user_id=user.id, customer=None, address=None, appointment=appointment, payment=payment,
                                                        scheduled_for=scheduled_for, dedupe=dedupe, link=link, recipient_name=user.full_name))
                    elif ch == "email" and self.channel_enabled("email", cfg) and user.email:
                        _add(created, self._create(event, ch, values, user_id=user.id, customer=None, address=user.email, appointment=appointment, payment=payment,
                                                    scheduled_for=scheduled_for, dedupe=dedupe, recipient_name=user.full_name))
        return created

    def _create(self, event: Event, channel: str, values: dict[str, str], *, user_id, customer, address, appointment, payment, scheduled_for, dedupe,
                link: str | None = None, recipient_name: str | None = None) -> Notification | None:
        subject_t, body_t, provider_template_id = self.template(event, channel)
        body = render(body_t, values)
        subject = single_line(render(subject_t, values), 255) if subject_t else None
        if channel in ("sms", "whatsapp"):
            body = single_line(body) if channel == "sms" else body
        params = [values.get(name, "") for name in _ordered_placeholders(body_t)]
        key = None
        if dedupe:
            raw = f"{self.org.id}|{event.code}|{dedupe}|{channel}|{user_id or address}"
            key = hashlib.sha256(raw.encode()).hexdigest()
            if self.db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
                return None
        now = utcnow()
        in_app = channel == "in_app"
        n = Notification(
            organization_id=self.org.id, event=event.code, channel=channel, recipient_user_id=user_id, recipient_customer_id=customer.id if customer else None,
            recipient_address=address, appointment_id=appointment.id if appointment is not None else None, payment_id=payment.id if payment is not None else None,
            subject=subject, body=body, payload={"template_params": params, "provider_template_id": provider_template_id, "link": link,
                                                 "recipient_name": recipient_name or (customer.full_name if customer else None),
                                                 "start_at": appointment.start_at.isoformat() if appointment is not None else None},
            status=S.SENT if in_app else (S.SCHEDULED if scheduled_for and scheduled_for > now else S.PENDING),
            scheduled_for=scheduled_for or now, sent_at=now if in_app else None, dedupe_key=key,
        )
        self.db.add(n)
        self.db.flush()
        return n

    # ------------------------------------------------- domain hooks
    def on_appointment_status(self, appt: Appointment, from_status: str | None, to_status: str, *, reason: str | None, extra: dict | None) -> None:
        if from_status is None:  # created
            if to_status == AppointmentStatus.PENDING_PAYMENT:
                self.emit("appointment.pending_payment", appointment=appt)
            elif to_status == AppointmentStatus.CONFIRMED:
                self.emit("appointment.confirmed", appointment=appt)
            self.emit("staff.new_booking", appointment=appt)
            return
        if from_status == to_status:
            if extra and extra.get("from") and extra.get("to"):
                prev = datetime.fromisoformat(extra["from"])
                self.emit("appointment.rescheduled", appointment=appt, extra={"previous_date": fmt_date(prev, appt.timezone), "previous_time": fmt_time(prev, appt.timezone)})
            return
        if to_status == AppointmentStatus.CONFIRMED and from_status in (AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION, AppointmentStatus.DRAFT):
            self.emit("appointment.confirmed", appointment=appt)
        elif to_status == AppointmentStatus.CANCELLED:
            pending_refund = self.db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(
                PaymentRefund.appointment_id == appt.id, PaymentRefund.status.in_(["requested", "approved"]))) or 0
            note = f"A refund of {inr(pending_refund)} has been requested; we will tell you when it is sent." if pending_refund else ""
            self.emit("appointment.cancelled", appointment=appt, extra={"reason": f"Reason: {reason}" if reason and reason != "cancel" else "", "refund_note": note})
            by_customer = bool(extra and extra.get("by_customer"))
            if by_customer:
                self.emit("staff.appointment_cancelled", appointment=appt, extra={"reason": reason if reason and reason != "cancel" else ""})
        elif to_status == AppointmentStatus.EXPIRED:
            self.emit("appointment.expired", appointment=appt)

    # ------------------------------------------------- admin: lists
    def get(self, public_id: str) -> Notification:
        n = self.db.scalar(select(Notification).where(Notification.public_id == public_id, Notification.organization_id == self.org.id))
        if n is None:
            raise NotFoundError("Notification not found.")
        return n

    def list(self, *, status: str | None, channel: str | None, event: str | None, search: str | None, page: int, page_size: int) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.organization_id == self.org.id)
        if status:
            stmt = stmt.where(Notification.status.in_(status.split(",")))
        if channel:
            stmt = stmt.where(Notification.channel == channel)
        if event:
            stmt = stmt.where(Notification.event == event)
        if search:
            like = f"%{search.strip()}%"
            appt_ids = select(Appointment.id).where(Appointment.organization_id == self.org.id, Appointment.reference.ilike(like))
            stmt = stmt.where(or_(Notification.recipient_address.ilike(like), Notification.subject.ilike(like), Notification.appointment_id.in_(appt_ids)))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    def to_read(self, n: Notification) -> NotificationRead:
        appt = self.db.get(Appointment, n.appointment_id) if n.appointment_id else None
        payload = n.payload or {}
        return NotificationRead(id=n.public_id, event=n.event, channel=n.channel, status=n.status, recipient=n.recipient_address, recipient_name=payload.get("recipient_name"),
                                subject=n.subject, body=n.body, scheduled_for=n.scheduled_for, sent_at=n.sent_at, read_at=n.read_at, attempts=n.attempts,
                                last_error=n.last_error, appointment_reference=appt.reference if appt else None, created_at=n.created_at)

    def to_detail(self, n: Notification) -> NotificationDetail:
        logs = self.db.scalars(select(NotificationLog).where(NotificationLog.notification_id == n.id).order_by(NotificationLog.id)).all()
        payload = {k: v for k, v in (n.payload or {}).items() if k in ("provider_template_id", "template_params", "link")}
        return NotificationDetail(**self.to_read(n).model_dump(), payload=payload,
                                  logs=[NotificationLogRead(provider=lg.provider, provider_message_id=lg.provider_message_id, status=lg.status, error=lg.error, created_at=lg.created_at) for lg in logs])

    def stats(self) -> NotificationStats:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        base = select(func.count()).select_from(Notification).where(Notification.organization_id == self.org.id, Notification.channel != "in_app")
        return NotificationStats(sent_today=int(self.db.scalar(base.where(Notification.status == S.SENT, Notification.sent_at >= start)) or 0),
                                 failed=int(self.db.scalar(base.where(Notification.status == S.FAILED)) or 0),
                                 scheduled=int(self.db.scalar(base.where(Notification.status == S.SCHEDULED)) or 0),
                                 pending=int(self.db.scalar(base.where(Notification.status.in_([S.PENDING, S.SENDING]))) or 0))

    def retry(self, n: Notification) -> Notification:
        if n.status not in (S.FAILED, S.CANCELLED) or n.channel == "in_app":
            raise ValidationFailed("Only failed or cancelled messages can be sent again.", code="invalid_transition")
        n.status, n.scheduled_for, n.last_error = S.PENDING, utcnow(), None
        n.attempts = 0
        record_audit(self.db, action="notification.retried", actor=self.actor, organization_id=self.org.id, entity_type="notification", entity_id=n.public_id, meta=self.meta)
        return n

    def cancel(self, n: Notification) -> Notification:
        if n.status not in (S.PENDING, S.SCHEDULED):
            raise ValidationFailed("Only messages that have not been sent can be cancelled.", code="invalid_transition")
        n.status, n.last_error = S.CANCELLED, "Cancelled by staff"
        record_audit(self.db, action="notification.cancelled", actor=self.actor, organization_id=self.org.id, entity_type="notification", entity_id=n.public_id, meta=self.meta)
        return n

    # ------------------------------------------------- admin: templates
    def events(self) -> list[EventInfo]:
        cfg = self.settings()
        out = []
        for e in EVENTS.values():
            enabled, channels = self.event_channels(e, cfg)
            out.append(EventInfo(code=e.code, label=e.label, audience=e.audience, description=e.description, variables=e.variables,
                                 default_channels=list(e.default_channels), enabled=enabled, channels=channels))
        return out

    def templates(self) -> list[TemplateRead]:
        custom = {(t.event, t.channel): t for t in self.db.scalars(select(NotificationTemplate).where(NotificationTemplate.organization_id == self.org.id)).all()}
        out = []
        for e in EVENTS.values():
            for ch, d in e.templates.items():
                row = custom.get((e.code, ch))
                out.append(TemplateRead(event=e.code, channel=ch, subject=row.subject if row else d.subject, body=row.body if row else d.body,
                                        provider_template_id=row.provider_template_id if row else None, is_custom=row is not None, is_active=row.is_active if row else True,
                                        default_subject=d.subject, default_body=d.body, updated_at=row.updated_at if row else None))
        return out

    def _check_template(self, code: str, channel: str, subject: str | None, body: str) -> Event:
        event = EVENTS.get(code)
        if event is None or channel not in event.templates:
            raise NotFoundError("Unknown event or channel.")
        unknown = (placeholders(body) | placeholders(subject)) - set(event.variables)
        if unknown:
            raise ValidationFailed(f"Unknown variables: {', '.join(sorted(unknown))}. Available: {', '.join(event.variables)}.", code="unknown_variables")
        if channel == "email" and not (subject and subject.strip()):
            raise ValidationFailed("Emails need a subject.", code="subject_required")
        return event

    def upsert_template(self, code: str, channel: str, payload: TemplateUpsert) -> TemplateRead:
        event = self._check_template(code, channel, payload.subject, payload.body)
        row = self._custom(code, channel)
        before = {"subject": row.subject, "body": row.body} if row else None
        if row is None:
            row = NotificationTemplate(organization_id=self.org.id, event=code, channel=channel, locale="en-IN", name=f"{event.label} ({channel})")
            self.db.add(row)
        row.subject = payload.subject if channel in ("email", "in_app") else None
        row.body = payload.body
        row.provider_template_id = (payload.provider_template_id or "").strip() or None
        row.is_active = payload.is_active
        row.variables = sorted(placeholders(payload.body))
        self.db.flush()
        record_audit(self.db, action="notification.template_saved", actor=self.actor, organization_id=self.org.id, entity_type="notification_template",
                     entity_id=f"{code}:{channel}", before=before, after={"subject": row.subject, "body": row.body}, meta=self.meta)
        return next(t for t in self.templates() if t.event == code and t.channel == channel)

    def reset_template(self, code: str, channel: str) -> TemplateRead:
        row = self._custom(code, channel)
        if row is not None:
            self.db.delete(row)
            self.db.flush()
            record_audit(self.db, action="notification.template_reset", actor=self.actor, organization_id=self.org.id, entity_type="notification_template",
                         entity_id=f"{code}:{channel}", meta=self.meta)
        return next(t for t in self.templates() if t.event == code and t.channel == channel)

    def preview(self, code: str, channel: str, subject: str | None, body: str) -> PreviewResponse:
        event = EVENTS.get(code)
        if event is None or channel not in event.templates:
            raise NotFoundError("Unknown event or channel.")
        values = {**SAMPLE_VALUES, "organization_name": self.org.name, "organization_phone": self.org.phone or SAMPLE_VALUES["organization_phone"]}
        text = render(body, values)
        subj = single_line(render(subject, values)) if subject else None
        if channel == "sms":
            text = single_line(text)
        unknown = sorted((placeholders(body) | placeholders(subject)) - set(event.variables))
        brand = OrganizationService(self.db).get_settings(self.org, "branding")["branding"]
        return PreviewResponse(subject=subj, body=text, html=email_html(text, organization_name=self.org.name, primary_color=brand.get("primary_color") or "#0f766e") if channel == "email" else None,
                               sms_segments=sms_segments(text) if channel == "sms" else None, unknown_variables=unknown)

    def send_test(self, channel: str, to: str) -> NotificationDetail:
        to = to.strip()
        if channel == "email" and "@" not in to:
            raise ValidationFailed("Enter an email address.")
        if channel in ("sms", "whatsapp"):
            from app.services.customer_service import normalize_mobile

            to = normalize_mobile(to)
        body = f"Test message from {self.org.name}. If you received this, {channel} notifications are working."
        n = Notification(organization_id=self.org.id, event="test", channel=channel, recipient_address=to, recipient_user_id=self.actor.id if self.actor else None,
                         subject=f"Test message from {self.org.name}" if channel == "email" else None, body=body,
                         payload={"recipient_name": self.actor.full_name if self.actor else None, "template_params": [self.org.name]},
                         status=S.PENDING, scheduled_for=utcnow())
        self.db.add(n)
        self.db.flush()
        deliver(self.db, n)
        return self.to_detail(n)

    def providers(self) -> list[ProviderStatus]:
        cfg = self.settings()
        return [ProviderStatus(**p, enabled_for_organization=self.channel_enabled(p["channel"], cfg)) for p in provider_status()]


def _add(rows: list[Notification], n: Notification | None) -> None:
    if n is not None:
        rows.append(n)


def _ordered_placeholders(text: str) -> list[str]:
    from app.notifications.render import PLACEHOLDER

    seen: list[str] = []
    for m in PLACEHOLDER.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


# ====================================================================== delivery
def _still_relevant(db: Session, n: Notification) -> str | None:
    """Re-check scheduled messages right before sending. Returns a reason to cancel, or None."""
    if n.organization_id:
        org = db.get(Organization, n.organization_id)
        if org is None or org.deleted_at is not None:
            return "organization removed"
        cfg = NotificationService(db, org).settings()
        if n.channel in DELIVERABLE and not cfg.get(f"{n.channel}_enabled", False) and n.event != "test":
            return f"{n.channel} notifications are turned off"
    if n.event == "appointment.reminder" and n.appointment_id:
        appt = db.get(Appointment, n.appointment_id)
        if appt is None or appt.status not in REMINDER_STATUSES:
            return "appointment is no longer confirmed"
        if (n.payload or {}).get("start_at") != appt.start_at.isoformat():
            return "appointment was rescheduled"
        if appt.start_at <= utcnow():
            return "appointment already started"
    return None


def deliver(db: Session, n: Notification) -> bool:
    """Send one claimed notification and record the attempt. Returns True when sent."""
    settings = get_settings()
    reason = _still_relevant(db, n)
    if reason:
        n.status, n.last_error = S.CANCELLED, reason
        return False
    org = db.get(Organization, n.organization_id) if n.organization_id else None
    payload = n.payload or {}
    html = None
    if n.channel == "email" and org is not None:
        brand = OrganizationService(db).get_settings(org, "branding")["branding"]
        html = email_html(n.body, organization_name=org.name, primary_color=brand.get("primary_color") or "#0f766e")
    reply_to = None
    if org is not None:
        cfg = NotificationService(db, org).settings()
        reply_to = (cfg.get("reply_to_email") or org.email or None)
    message = OutboundMessage(channel=n.channel, to=n.recipient_address or "", body=n.body, subject=n.subject, html=html, from_name=org.name if org else None,
                              reply_to=reply_to, provider_template_id=payload.get("provider_template_id"), template_params=list(payload.get("template_params") or []),
                              reference=n.public_id)
    try:
        provider = get_provider(n.channel)
        result = provider.send(message)
    except Exception as exc:  # noqa: BLE001 - a broken adapter must not stop the worker
        from app.notifications.providers import DeliveryResult

        result = DeliveryResult(provider="unknown", ok=False, retryable=True, error=f"{type(exc).__name__}: {exc}")
    now = utcnow()
    db.add(NotificationLog(notification_id=n.id, provider=result.provider, provider_message_id=result.message_id, status="sent" if result.ok else "failed",
                           response=result.response, error=result.error, created_at=now))
    if result.ok:
        n.status, n.sent_at, n.last_error = S.SENT, now, None
        return True
    n.last_error = result.error
    if result.retryable and n.attempts < settings.notification_max_attempts:
        n.status = S.PENDING
        n.scheduled_for = now + timedelta(minutes=2 ** max(0, n.attempts - 1))  # 1, 2, 4, 8 minutes
    else:
        n.status = S.FAILED
    return False


def dispatch_due(db: Session, *, limit: int = 100, commit: bool = True) -> dict[str, int]:
    """Deliver due messages. Each message is claimed with a conditional UPDATE so parallel workers never double-send."""
    now = utcnow()
    stale = now - timedelta(minutes=10)
    db.execute(update(Notification).where(Notification.status == S.SENDING, Notification.updated_at < stale).values(status=S.PENDING))
    ids = db.scalars(select(Notification.id).where(Notification.status.in_([S.PENDING, S.SCHEDULED]), Notification.channel.in_(DELIVERABLE),
                                                   or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now))
                     .order_by(Notification.scheduled_for, Notification.id).limit(limit)).all()
    counts = {"sent": 0, "failed": 0, "cancelled": 0, "retry": 0}
    for nid in ids:
        claimed = db.execute(update(Notification).where(Notification.id == nid, Notification.status.in_([S.PENDING, S.SCHEDULED]))
                             .values(status=S.SENDING, attempts=Notification.attempts + 1, updated_at=utcnow())).rowcount
        if not claimed:
            continue
        n = db.get(Notification, nid)
        db.refresh(n)
        deliver(db, n)
        counts["sent" if n.status == S.SENT else "failed" if n.status == S.FAILED else "cancelled" if n.status == S.CANCELLED else "retry"] += 1
        if commit:
            db.commit()
        else:
            db.flush()
    return counts


def schedule_reminders(db: Session, *, now: datetime | None = None, commit: bool = True) -> int:
    """Create reminder messages for confirmed appointments whose reminder time has arrived (or arrives within the hour)."""
    now = now or utcnow()
    created = 0
    orgs = db.scalars(select(Organization).where(Organization.deleted_at.is_(None))).all()
    for org in orgs:
        svc = NotificationService(db, org)
        cfg = svc.settings()
        hours = sorted({float(h) for h in (cfg.get("reminder_hours") or []) if 0 < float(h) <= 24 * 14}, reverse=True)
        if not hours:
            continue
        horizon = now + timedelta(hours=max(hours) + 1)
        appts = db.scalars(select(Appointment).where(Appointment.organization_id == org.id, Appointment.status.in_(REMINDER_STATUSES),
                                                     Appointment.start_at > now, Appointment.start_at <= horizon)).all()
        for appt in appts:
            for h in hours:
                send_at = appt.start_at - timedelta(hours=h)
                if send_at > now + timedelta(hours=1):
                    continue  # not yet
                booked_at = appt.confirmed_at or appt.created_at
                if booked_at and booked_at > send_at:
                    continue  # booked after this reminder would have gone out; a confirmation was sent instead
                label = f"{int(h)}" if h == int(h) else f"{h}"
                created += len(svc.emit("appointment.reminder", appointment=appt, scheduled_for=max(send_at, now), extra={"hours_before": label},
                                        dedupe=f"reminder:{appt.id}:{label}:{appt.start_at.isoformat()}"))
        if commit:
            db.commit()
    return created


# ========================================================================= inbox
def inbox_for(db: Session, user: User, *, unread_only: bool = False, limit: int = 30) -> Inbox:
    stmt = select(Notification).where(Notification.recipient_user_id == user.id, Notification.channel == "in_app")
    unread = db.scalar(select(func.count()).select_from(stmt.where(Notification.read_at.is_(None)).subquery())) or 0
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    orgs = {o.id: o.public_id for o in db.scalars(select(Organization).where(Organization.id.in_({r.organization_id for r in rows if r.organization_id}))).all()} if rows else {}
    return Inbox(unread=int(unread), items=[InboxItem(id=r.public_id, event=r.event, title=r.subject, body=r.body, link=(r.payload or {}).get("link"),
                                                      organization_id=orgs.get(r.organization_id), read_at=r.read_at, created_at=r.created_at) for r in rows])


def mark_read(db: Session, user: User, ids: list[str] | None) -> int:
    stmt = update(Notification).where(Notification.recipient_user_id == user.id, Notification.channel == "in_app", Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.public_id.in_(ids))
    return db.execute(stmt.values(read_at=utcnow(), status=S.READ)).rowcount or 0


def preferences_of(customer: Customer) -> Preferences:
    p = customer.communication_preferences or {}
    return Preferences(email=p.get("email", True), sms=p.get("sms", True), whatsapp=p.get("whatsapp") is True, reminders=p.get("reminders", True))
