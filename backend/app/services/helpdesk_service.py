"""Patient help desk: patients ask their clinic about a booking, payment, refund, report or anything else, and staff answer.

Lifecycle: ``open`` (waiting for the clinic) → staff reply → ``pending_customer`` (waiting for the patient) → patient
reply → ``open`` … → ``resolved`` (by staff or the patient; a patient reply reopens it) → ``closed`` after the clinic's
``auto_close_days`` (a closed request cannot be reopened: the patient starts a new one). A request left waiting for the
patient that long is resolved automatically.

* Patients reach only their own requests (records with their verified mobile number / email, app/services/customer_link.py)
  and never see internal notes. Staff need ``helpdesk:read`` / ``helpdesk:write``; staff of one branch see the requests
  about their branch's bookings and the general ones (app/core/branch_scope.py).
* Message text is encrypted at rest; attachments (image or PDF) are stored privately and encrypted, and opening one is
  audit-logged. Notifications never contain the message text: patients read it after signing in.
* First-response target: ``first_response_hours`` after the request; past it and unanswered = overdue.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, RateLimited, ValidationFailed
from app.core.storage import get_storage, validate_upload
from app.core.time import utcnow
from app.models import Appointment, Branch, Customer, Organization, OrganizationMembership, Service, SupportMessage, SupportTicket, User
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService

CATEGORIES = {
    "booking": "Booking", "reschedule_cancel": "Change or cancel", "payment": "Payment", "refund": "Refund",
    "report": "Reports and prescription", "feedback": "Feedback", "other": "Something else",
}
STATUSES = ("open", "pending_customer", "resolved", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")
ATTACHMENT_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}
MAX_OPEN_PER_PATIENT = 10
MAX_BODY = 4000


def policy(db: Session, org: Organization) -> dict[str, Any]:
    return OrganizationService(db).get_settings(org, "helpdesk")["helpdesk"]


def _clean(text: str | None, *, field: str, low: int, high: int) -> str:
    value = (text or "").strip()
    if len(value) < low:
        raise ValidationFailed(f"Please write the {field}.", code=f"{field.replace(' ', '_')}_required")
    if len(value) > high:
        raise ValidationFailed(f"The {field} can be at most {high} characters.", code=f"{field.replace(' ', '_')}_too_long")
    return value


class HelpdeskService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # ===================================================================================================== patients
    def _patient_ids(self) -> list[int]:
        from app.services.customer_link import owned_customer_ids

        ids = owned_customer_ids(self.db, self.actor)
        return list(self.db.scalars(select(Customer.id).where(Customer.id.in_(ids), Customer.organization_id == self.org.id)).all()) if ids else []

    def _patient_record(self) -> Customer:
        ids = self._patient_ids()
        if ids:
            linked = self.db.scalar(select(Customer).where(Customer.id.in_(ids), Customer.user_id == self.actor.id))
            return linked or self.db.get(Customer, ids[0])
        from app.services.customer_service import CustomerService

        return CustomerService(self.db, self.org).for_user(self.actor)

    def patient_list(self) -> list[SupportTicket]:
        ids = self._patient_ids()
        if not ids:
            return []
        return list(self.db.scalars(select(SupportTicket).where(SupportTicket.organization_id == self.org.id, SupportTicket.customer_id.in_(ids))
                                    .order_by(SupportTicket.last_activity_at.desc())).all())

    def patient_get(self, public_id: str) -> SupportTicket:
        t = self.db.scalar(select(SupportTicket).where(SupportTicket.public_id == public_id, SupportTicket.organization_id == self.org.id))
        if t is None or t.customer_id not in self._patient_ids():
            raise NotFoundError("Request not found.")
        return t

    def patient_create(self, *, category: str, subject: str, body: str, appointment_reference: str | None,
                       file: tuple[bytes, str] | None) -> SupportTicket:
        if not policy(self.db, self.org).get("enabled", True):
            raise PermissionDenied("This clinic does not take requests online. Please call the clinic.", code="helpdesk_disabled")
        if category not in CATEGORIES:
            raise ValidationFailed("Choose what your question is about.", code="invalid_category")
        subject = _clean(subject, field="subject", low=3, high=160)
        body = _clean(body, field="message", low=2, high=MAX_BODY)
        customer = self._patient_record()
        open_count = self.db.scalar(select(func.count()).select_from(SupportTicket).where(
            SupportTicket.organization_id == self.org.id, SupportTicket.customer_id == customer.id, SupportTicket.status.in_(("open", "pending_customer"))))
        if open_count >= MAX_OPEN_PER_PATIENT:
            raise RateLimited("You already have many open requests. Please wait for an answer or add to an open one.", code="too_many_open_requests")
        appt = None
        if appointment_reference:
            appt = self.db.scalar(select(Appointment).where(Appointment.reference == appointment_reference, Appointment.organization_id == self.org.id,
                                                            Appointment.customer_id.in_(self._patient_ids() or [customer.id])))
            if appt is None:
                raise ValidationFailed("That booking was not found in your account.", code="appointment_not_found")
        now = utcnow()
        hours = int(policy(self.db, self.org).get("first_response_hours", 24))
        ticket = SupportTicket(organization_id=self.org.id, customer_id=customer.id, requester_user_id=self.actor.id,
                               branch_id=appt.branch_id if appt else None, appointment_id=appt.id if appt else None, category=category,
                               subject=subject, status="open", priority="normal", source="web", first_response_due_at=now + timedelta(hours=hours),
                               last_customer_message_at=now, last_activity_at=now, unread_by_staff=True, unread_by_customer=False)
        self._insert_numbered(ticket)
        self._add_message(ticket, body, kind="customer", internal=False, file=file)
        record_audit(self.db, action="helpdesk.ticket_created", actor=self.actor, organization_id=self.org.id, entity_type="support_ticket",
                     entity_id=ticket.public_id, after={"number": ticket.number, "category": category}, meta=self.meta)
        self._notify_staff(ticket, customer)
        return ticket

    def patient_reply(self, ticket: SupportTicket, body: str, file: tuple[bytes, str] | None) -> SupportMessage:
        if ticket.status == "closed":
            raise ConflictError("This request is closed. Please start a new one.", code="ticket_closed")
        body = _clean(body, field="message", low=1, high=MAX_BODY)
        now = utcnow()
        msg = self._add_message(ticket, body, kind="customer", internal=False, file=file)
        if ticket.status in ("pending_customer", "resolved"):
            ticket.status, ticket.resolved_at = "open", None
        ticket.last_customer_message_at = ticket.last_activity_at = now
        ticket.unread_by_staff = True
        self.db.flush()
        self._notify_staff(ticket, self.db.get(Customer, ticket.customer_id))
        return msg

    def patient_resolve(self, ticket: SupportTicket, rating: int | None) -> SupportTicket:
        if rating is not None and not 1 <= rating <= 5:
            raise ValidationFailed("Rate from 1 to 5.", code="invalid_rating")
        if ticket.status == "closed" and rating is None:
            return ticket
        if ticket.status not in ("resolved", "closed"):
            ticket.status, ticket.resolved_at = "resolved", utcnow()
            self._add_message(ticket, "The patient marked this request as solved.", kind="system", internal=False, file=None)
        if rating is not None:
            ticket.rating = rating
        ticket.last_activity_at = utcnow()
        record_audit(self.db, action="helpdesk.resolved_by_patient", actor=self.actor, organization_id=self.org.id, entity_type="support_ticket",
                     entity_id=ticket.public_id, after={"rating": rating}, meta=self.meta)
        self.db.flush()
        return ticket

    # ======================================================================================================= staff
    def staff_get(self, public_id: str) -> SupportTicket:
        t = self.db.scalar(select(SupportTicket).where(SupportTicket.public_id == public_id, SupportTicket.organization_id == self.org.id))
        if t is None:
            raise NotFoundError("Request not found.")
        return t

    def staff_list(self, *, status: str, assigned: str, category: str | None, search: str | None, page: int, page_size: int) -> tuple[list[SupportTicket], int]:
        stmt = select(SupportTicket).where(SupportTicket.organization_id == self.org.id)
        if status == "active":
            stmt = stmt.where(SupportTicket.status.in_(("open", "pending_customer")))
        elif status == "overdue":
            stmt = stmt.where(SupportTicket.status == "open", SupportTicket.first_response_at.is_(None), SupportTicket.first_response_due_at < utcnow())
        elif status in STATUSES:
            stmt = stmt.where(SupportTicket.status == status)
        if assigned == "me":
            stmt = stmt.where(SupportTicket.assigned_to_user_id == self.actor.id)
        elif assigned == "unassigned":
            stmt = stmt.where(SupportTicket.assigned_to_user_id.is_(None))
        if category in CATEGORIES:
            stmt = stmt.where(SupportTicket.category == category)
        if search and search.strip().startswith("#") and search.strip()[1:].isdigit():
            stmt = stmt.where(SupportTicket.number == int(search.strip()[1:]))  # "#12": that request
        elif search:
            q = search.strip()
            like = f"%{q.lower()}%"
            conditions = [func.lower(SupportTicket.subject).like(like),
                          SupportTicket.customer_id.in_(select(Customer.id).where(Customer.organization_id == self.org.id, func.lower(Customer.full_name).like(like)))]
            if q.isdigit():
                conditions.append(SupportTicket.number == int(q))
            stmt = stmt.where(or_(*conditions))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(SupportTicket.unread_by_staff.desc(), SupportTicket.last_activity_at.desc())
                               .offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def summary(self) -> dict[str, Any]:
        base = select(func.count()).select_from(SupportTicket).where(SupportTicket.organization_id == self.org.id)
        now = utcnow()
        count = lambda *where: self.db.scalar(base.where(*where)) or 0  # noqa: E731
        since = now - timedelta(days=30)
        answered = self.db.execute(select(SupportTicket.created_at, SupportTicket.first_response_at).where(
            SupportTicket.organization_id == self.org.id, SupportTicket.first_response_at.is_not(None), SupportTicket.created_at >= since)).all()
        avg_hours = round(sum((r[1] - r[0]).total_seconds() for r in answered) / len(answered) / 3600, 1) if answered else None
        rating = self.db.scalar(select(func.avg(SupportTicket.rating)).where(SupportTicket.organization_id == self.org.id, SupportTicket.rating.is_not(None)))
        return {
            "open": count(SupportTicket.status == "open"),
            "pending_customer": count(SupportTicket.status == "pending_customer"),
            "unassigned": count(SupportTicket.status.in_(("open", "pending_customer")), SupportTicket.assigned_to_user_id.is_(None)),
            "mine": count(SupportTicket.status.in_(("open", "pending_customer")), SupportTicket.assigned_to_user_id == self.actor.id),
            "overdue": count(SupportTicket.status == "open", SupportTicket.first_response_at.is_(None), SupportTicket.first_response_due_at < now),
            "resolved_30_days": count(SupportTicket.resolved_at >= since),
            "avg_first_response_hours": avg_hours,
            "avg_rating": round(float(rating), 1) if rating is not None else None,
        }

    def agents(self) -> list[dict[str, str]]:
        """Members who can answer requests (for assigning)."""
        rows = self.db.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id == self.org.id,
                                                                    OrganizationMembership.status == "active")).all()
        return sorted(({"id": m.user.public_id, "name": m.user.full_name} for m in rows
                       if m.role is not None and "helpdesk:write" in {p.code for p in m.role.permissions}), key=lambda a: a["name"].lower())

    def staff_reply(self, ticket: SupportTicket, body: str, *, internal: bool, file: tuple[bytes, str] | None, next_status: str | None) -> SupportMessage:
        body = _clean(body, field="message", low=1, high=MAX_BODY)
        if ticket.status == "closed" and not internal:
            raise ConflictError("This request is closed. The patient can start a new one.", code="ticket_closed")
        msg = self._add_message(ticket, body, kind="staff", internal=internal, file=file)
        now = utcnow()
        ticket.last_activity_at = now
        if not internal:
            ticket.last_staff_message_at = now
            ticket.first_response_at = ticket.first_response_at or now
            ticket.unread_by_customer = True
            ticket.status = "pending_customer"
            if ticket.assigned_to_user_id is None:
                ticket.assigned_to_user_id = self.actor.id  # whoever answers first owns it
        ticket.unread_by_staff = False
        if next_status:
            self._set_status(ticket, next_status)
        record_audit(self.db, action="helpdesk.note_added" if internal else "helpdesk.replied", actor=self.actor, organization_id=self.org.id,
                     entity_type="support_ticket", entity_id=ticket.public_id, after={"number": ticket.number, "status": ticket.status}, meta=self.meta)
        self.db.flush()
        if not internal:
            self._notify_customer(ticket)
        return msg

    def staff_update(self, ticket: SupportTicket, *, status: str | None, priority: str | None, assigned_to: str | None, unassign: bool,
                     category: str | None) -> SupportTicket:
        before = {"status": ticket.status, "priority": ticket.priority, "assigned_to": ticket.assigned_to_user_id, "category": ticket.category}
        if status:
            self._set_status(ticket, status)
        if priority:
            if priority not in PRIORITIES:
                raise ValidationFailed("Unknown priority.", code="invalid_priority")
            ticket.priority = priority
        if category:
            if category not in CATEGORIES:
                raise ValidationFailed("Unknown category.", code="invalid_category")
            ticket.category = category
        if unassign:
            ticket.assigned_to_user_id = None
        elif assigned_to:
            agent = self.db.scalar(select(User).where(User.public_id == assigned_to))
            if agent is None or assigned_to not in {a["id"] for a in self.agents()}:
                raise ValidationFailed("That person cannot answer requests at this clinic.", code="invalid_assignee")
            ticket.assigned_to_user_id = agent.id
        ticket.unread_by_staff = False
        after = {"status": ticket.status, "priority": ticket.priority, "assigned_to": ticket.assigned_to_user_id, "category": ticket.category}
        if after != before:
            ticket.last_activity_at = utcnow()
            record_audit(self.db, action="helpdesk.updated", actor=self.actor, organization_id=self.org.id, entity_type="support_ticket",
                         entity_id=ticket.public_id, before=before, after=after, meta=self.meta)
        self.db.flush()
        return ticket

    def _set_status(self, ticket: SupportTicket, status: str) -> None:
        if status not in STATUSES:
            raise ValidationFailed("Unknown status.", code="invalid_status")
        now = utcnow()
        ticket.status = status
        if status == "resolved":
            ticket.resolved_at = now
        elif status == "closed":
            ticket.closed_at, ticket.resolved_at = now, ticket.resolved_at or now
        else:
            ticket.resolved_at = ticket.closed_at = None

    # ====================================================================================================== shared
    def messages(self, ticket: SupportTicket, *, staff: bool) -> list[SupportMessage]:
        stmt = select(SupportMessage).where(SupportMessage.ticket_id == ticket.id)
        if not staff:
            stmt = stmt.where(SupportMessage.internal.is_(False))
        return list(self.db.scalars(stmt.order_by(SupportMessage.created_at, SupportMessage.id)).all())

    def open_attachment(self, ticket: SupportTicket, message_id: str, *, staff: bool):
        msg = self.db.scalar(select(SupportMessage).where(SupportMessage.public_id == message_id, SupportMessage.ticket_id == ticket.id))
        if msg is None or msg.attachment_key is None or (msg.internal and not staff):
            raise NotFoundError("Attachment not found.")
        record_audit(self.db, action="helpdesk.attachment_opened", actor=self.actor, organization_id=self.org.id, entity_type="support_ticket",
                     entity_id=ticket.public_id, after={"message": msg.public_id}, meta=self.meta)
        return msg, get_storage().open(msg.attachment_key)

    def mark_read(self, ticket: SupportTicket, *, staff: bool) -> None:
        if staff and ticket.unread_by_staff:
            ticket.unread_by_staff = False
        elif not staff and ticket.unread_by_customer:
            ticket.unread_by_customer = False
        self.db.flush()

    def read(self, ticket: SupportTicket, *, staff: bool) -> dict[str, Any]:
        appt = self.db.get(Appointment, ticket.appointment_id) if ticket.appointment_id else None
        out: dict[str, Any] = {
            "id": ticket.public_id, "number": ticket.number, "subject": ticket.subject, "category": ticket.category,
            "category_label": CATEGORIES.get(ticket.category, ticket.category), "status": ticket.status, "created_at": ticket.created_at,
            "last_activity_at": ticket.last_activity_at, "resolved_at": ticket.resolved_at, "closed_at": ticket.closed_at, "rating": ticket.rating,
            "unread": ticket.unread_by_staff if staff else ticket.unread_by_customer,
            "appointment": {"reference": appt.reference, "start_at": appt.start_at, "timezone": appt.timezone,
                            "service_name": (self.db.get(Service, appt.service_id).name if appt.service_id else "")} if appt else None,
        }
        if staff:
            # Plain columns (not the filtered patient record): staff answering a general question see who asked, even if
            # that patient's visits are at another branch.
            cols = Customer.__table__.c
            customer = self.db.execute(select(cols.public_id, cols.full_name).where(cols.id == ticket.customer_id)).first()
            agent = self.db.get(User, ticket.assigned_to_user_id) if ticket.assigned_to_user_id else None
            branch = self.db.get(Branch, ticket.branch_id) if ticket.branch_id else None
            out.update({
                "priority": ticket.priority, "customer": {"id": customer[0], "name": customer[1]} if customer else None,
                "assigned_to": {"id": agent.public_id, "name": agent.full_name} if agent else None, "branch_name": branch.name if branch else None,
                "first_response_due_at": ticket.first_response_due_at, "first_response_at": ticket.first_response_at,
                "overdue": bool(ticket.status == "open" and ticket.first_response_at is None and ticket.first_response_due_at and ticket.first_response_due_at < utcnow()),
            })
        return out

    def message_read(self, m: SupportMessage, *, staff: bool) -> dict[str, Any]:
        author = self.db.get(User, m.author_user_id) if m.author_user_id else None
        if m.author_kind == "staff":
            name = (author.full_name if staff else (author.full_name.split(" ")[0] if author else "Clinic")) if author else "Clinic"
        elif m.author_kind == "customer":
            name = author.full_name if author else "Patient"
        else:
            name = "Update"
        return {"id": m.public_id, "author_kind": m.author_kind, "author_name": name, "internal": m.internal, "body": m.body, "created_at": m.created_at,
                "attachment": {"name": m.attachment_name, "mime": m.attachment_mime, "size": m.attachment_size} if m.attachment_key else None}

    # ===================================================================================================== helpers
    def _insert_numbered(self, ticket: SupportTicket) -> None:
        """#1, #2 … per clinic. Two requests at the same moment: the unique index refuses one, which takes the next number."""
        for _ in range(5):
            ticket.number = (self.db.scalar(select(func.max(SupportTicket.number)).where(SupportTicket.organization_id == self.org.id)) or 0) + 1
            try:
                with self.db.begin_nested():
                    self.db.add(ticket)
                    self.db.flush()
                return
            except IntegrityError:
                continue
        raise ConflictError("Please try again.", code="ticket_number_busy")

    def _add_message(self, ticket: SupportTicket, body: str, *, kind: str, internal: bool, file: tuple[bytes, str] | None) -> SupportMessage:
        msg = SupportMessage(organization_id=self.org.id, ticket_id=ticket.id, author_user_id=self.actor.id if self.actor and kind != "system" else None,
                             author_kind=kind, internal=internal, body=body)
        if file is not None:
            data, name = file
            mime = validate_upload(data, allowed=ATTACHMENT_TYPES, max_mb=get_settings().max_upload_size_mb)
            stored = get_storage().save(scope=f"org/{self.org.public_id}/helpdesk/{ticket.public_id}", visibility="private", data=data, mime_type=mime)
            safe = "".join(ch for ch in (name or "attachment") if ch.isalnum() or ch in " ._-")[:120].strip() or "attachment"
            msg.attachment_key, msg.attachment_name, msg.attachment_mime, msg.attachment_size = stored.key, safe, mime, len(data)
        self.db.add(msg)
        self.db.flush()
        return msg

    def _help_link(self, ticket: SupportTicket) -> str:
        return f"{get_settings().frontend_url.rstrip('/')}/{self.org.slug}/bookings?tab=help&request={ticket.public_id}"

    def _notify_staff(self, ticket: SupportTicket, customer: Customer | None) -> None:
        from app.services.notification_service import NotificationService

        notifier = NotificationService(self.db, self.org, self.actor, self.meta)
        staff = None
        if ticket.assigned_to_user_id:
            agent = self.db.get(User, ticket.assigned_to_user_id)
            staff = [agent] if agent is not None else None
        if staff is None:
            appt = self.db.get(Appointment, ticket.appointment_id) if ticket.appointment_id else None
            staff = notifier.staff_recipients("staff.helpdesk_message", appt)
        notifier.emit("staff.helpdesk_message", staff=staff, link=f"/admin/helpdesk/{ticket.public_id}",
                      extra={"customer_name": customer.full_name if customer else "A patient", "ticket_number": str(ticket.number),
                             "ticket_subject": ticket.subject, "category": CATEGORIES.get(ticket.category, ticket.category)})

    def _notify_customer(self, ticket: SupportTicket) -> None:
        from app.services.notification_service import NotificationService

        customer = self.db.get(Customer, ticket.customer_id)
        if customer is None:
            return
        link = self._help_link(ticket)
        NotificationService(self.db, self.org, self.actor, self.meta).emit(
            "helpdesk.reply", customer=customer, link=link.split(get_settings().frontend_url.rstrip("/"), 1)[-1],
            extra={"customer_name": customer.full_name, "ticket_number": str(ticket.number), "ticket_subject": ticket.subject, "help_link": link})


def close_stale(db: Session, now=None) -> int:
    """Worker: requests left waiting for the patient are resolved, and resolved ones closed, after each clinic's
    ``auto_close_days``."""
    now = now or utcnow()
    changed = 0
    org_ids = db.scalars(select(SupportTicket.organization_id).where(SupportTicket.status.in_(("pending_customer", "resolved"))).distinct()).all()
    for org in db.scalars(select(Organization).where(Organization.id.in_(org_ids))).all():
        cutoff = now - timedelta(days=int(policy(db, org).get("auto_close_days", 7)))
        svc = HelpdeskService(db, org)
        for t in db.scalars(select(SupportTicket).where(SupportTicket.organization_id == org.id, SupportTicket.status == "pending_customer",
                                                        SupportTicket.last_activity_at < cutoff)).all():
            t.status, t.resolved_at, t.last_activity_at = "resolved", now, now
            svc._add_message(t, "Resolved automatically: no reply from the patient for a while. Reply to reopen it.", kind="system", internal=False, file=None)
            changed += 1
        for t in db.scalars(select(SupportTicket).where(SupportTicket.organization_id == org.id, SupportTicket.status == "resolved",
                                                        SupportTicket.resolved_at < cutoff)).all():
            t.status, t.closed_at = "closed", now
            changed += 1
    db.flush()
    return changed
