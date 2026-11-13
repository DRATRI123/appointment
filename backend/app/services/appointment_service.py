"""Holds, booking, lifecycle, reschedule, recurring series and waitlist."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.enums import AppointmentSource, AppointmentStatus, HoldStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDenied,
    SlotUnavailable,
    ValidationFailed,
)
from app.core.ids import new_reference
from app.core.time import utcnow
from app.models import (
    Appointment,
    AppointmentCancellation,
    AppointmentReschedule,
    AppointmentStatusHistory,
    BookingHold,
    Branch,
    Customer,
    CustomerDependent,
    Organization,
    Professional,
    Service,
    User,
    Waitlist,
)
from app.schemas.appointment import (
    AppointmentCreate,
    HoldCreate,
    RecurringCreate,
    RescheduleRequest,
    WaitlistCreate,
)
from app.services.audit_service import RequestMeta, record_audit
from app.services.availability_service import AvailabilityService, appointment_length, branch_tz
from app.services.catalog_service import CatalogService
from app.services.customer_service import CustomerService
from app.services.organization_service import OrganizationService
from app.services.pricing_service import quote

TRANSITIONS: dict[str, dict[str, str]] = {
    "confirm": {AppointmentStatus.PENDING_PAYMENT: AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING_VERIFICATION: AppointmentStatus.CONFIRMED, AppointmentStatus.DRAFT: AppointmentStatus.CONFIRMED},
    "check_in": {AppointmentStatus.CONFIRMED: AppointmentStatus.CHECKED_IN, AppointmentStatus.PENDING_PAYMENT: AppointmentStatus.CHECKED_IN},
    "start": {AppointmentStatus.CHECKED_IN: AppointmentStatus.IN_PROGRESS, AppointmentStatus.CONFIRMED: AppointmentStatus.IN_PROGRESS},
    "complete": {AppointmentStatus.IN_PROGRESS: AppointmentStatus.COMPLETED, AppointmentStatus.CHECKED_IN: AppointmentStatus.COMPLETED, AppointmentStatus.CONFIRMED: AppointmentStatus.COMPLETED},
    "no_show": {AppointmentStatus.CONFIRMED: AppointmentStatus.NO_SHOW, AppointmentStatus.PENDING_PAYMENT: AppointmentStatus.NO_SHOW, AppointmentStatus.CHECKED_IN: AppointmentStatus.NO_SHOW},
    "cancel": {s: AppointmentStatus.CANCELLED for s in (AppointmentStatus.DRAFT, AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION, AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN)},
    "expire": {AppointmentStatus.PENDING_PAYMENT: AppointmentStatus.EXPIRED, AppointmentStatus.DRAFT: AppointmentStatus.EXPIRED},
}


def _insert_or_conflict(db: Session, row, message: str, code: str = "slot_unavailable") -> None:
    """Insert inside a SAVEPOINT so a unique-index collision only undoes this row, never the caller's work."""
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        if code == "already_waitlisted":
            raise ConflictError(message, code=code) from exc
        raise SlotUnavailable(message, code=code) from exc


class AppointmentService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()
        self.catalog = CatalogService(db, org, actor, meta)
        self.availability = AvailabilityService(db, org)
        self.customers = CustomerService(db, org)
        self.settings = get_settings()

    # ----------------------------------------------------------- settings
    def _setting(self, namespace: str, key: str, default=None):
        values = OrganizationService(self.db).get_settings(self.org, namespace)[namespace]
        return values.get(key, default)

    # -------------------------------------------------------------- holds
    def create_hold(self, payload: HoldCreate, *, session_key: str | None = None, customer: Customer | None = None, ignore_notice: bool = False) -> BookingHold:
        pro = self.catalog.get_professional(payload.professional_id)
        branch = self.catalog.get_branch(payload.branch_id)
        service = self.catalog.get_service(payload.service_id)
        start = _utc(payload.start_at)
        self._lock_professional(pro)
        self.availability.expire_stale_holds()
        self._assert_slot_open(service, pro, branch, start, ignore_notice=ignore_notice)
        duration, _ = appointment_length(service, pro, branch)
        tz_day = start.astimezone(branch_tz(self.org, branch)).date()
        busy, _ = self.availability.busy_for(pro, branch, start - timedelta(days=1), start + timedelta(days=1))
        hold = BookingHold(
            organization_id=self.org.id, branch_id=branch.id, professional_id=pro.id, service_id=service.id,
            customer_id=customer.id if customer else None, session_key=session_key or payload.session_key or secrets.token_urlsafe(16),
            start_at=start, end_at=start + timedelta(minutes=duration), slot_sequence=self.availability.next_sequence(start, busy),
            status=HoldStatus.ACTIVE, expires_at=utcnow() + timedelta(minutes=int(self._setting("booking", "hold_minutes", self.settings.booking_hold_minutes) or 10)),
        )
        _insert_or_conflict(self.db, hold, "This slot was just taken. Please pick another time.")
        _ = tz_day
        return hold

    def release_hold(self, public_id: str, *, session_key: str | None = None) -> None:
        hold = self.db.scalar(select(BookingHold).where(BookingHold.public_id == public_id, BookingHold.organization_id == self.org.id))
        if hold is None:
            raise NotFoundError("Hold not found.")
        if session_key is not None and hold.session_key != session_key:
            raise PermissionDenied("This hold belongs to another session.", code="hold_mismatch")
        if hold.status == HoldStatus.ACTIVE:
            hold.status = HoldStatus.RELEASED
            hold.released_at = utcnow()
            self.db.flush()

    def _get_hold(self, public_id: str, session_key: str | None) -> BookingHold:
        hold = self.db.scalar(select(BookingHold).where(BookingHold.public_id == public_id, BookingHold.organization_id == self.org.id))
        if hold is None:
            raise NotFoundError("Hold not found.")
        if session_key is not None and hold.session_key != session_key:
            raise PermissionDenied("This hold belongs to another session.", code="hold_mismatch")
        if hold.status != HoldStatus.ACTIVE or hold.expires_at < utcnow():
            raise SlotUnavailable("Your hold has expired. Please choose the time again.", code="hold_expired")
        return hold

    def _lock_professional(self, pro: Professional) -> None:
        # PostgreSQL: row lock serialises concurrent bookings for one professional. SQLite: BEGIN IMMEDIATE already does.
        self.db.execute(select(Professional.id).where(Professional.id == pro.id).with_for_update())

    def _assert_slot_open(self, service: Service, pro: Professional, branch: Branch, start: datetime, *, ignore_notice: bool, exclude_appointment_id: int | None = None) -> None:
        day = start.astimezone(branch_tz(self.org, branch)).date()
        slots = self.availability.slots_for_professional(service, pro, branch, day, ignore_notice=ignore_notice, exclude_appointment_id=exclude_appointment_id)
        if not any(s.start_at == start for s in slots):
            raise SlotUnavailable("That time is not available.")

    # ------------------------------------------------------------ booking
    def create(self, payload: AppointmentCreate, *, user: User | None, staff: bool, session_key: str | None = None) -> Appointment:
        allow_guest = bool(self._setting("booking", "allow_guest_booking", True))
        if payload.hold_id:
            hold = self._get_hold(payload.hold_id, None if staff else (session_key or payload.session_key))
            pro = self.db.get(Professional, hold.professional_id)
            branch = self.db.get(Branch, hold.branch_id)
            service = self.db.get(Service, hold.service_id)
            start, sequence = hold.start_at, hold.slot_sequence
        else:
            if not staff:
                raise ValidationFailed("Online bookings must reserve a slot first (hold_id).", code="hold_required")
            if not (payload.professional_id and payload.branch_id and payload.service_id and payload.start_at):
                raise ValidationFailed("professional_id, branch_id, service_id and start_at are required without a hold.")
            hold = None
            pro = self.catalog.get_professional(payload.professional_id)
            branch = self.catalog.get_branch(payload.branch_id)
            service = self.catalog.get_service(payload.service_id)
            start = _utc(payload.start_at)
            self._lock_professional(pro)
            self.availability.expire_stale_holds()
            self._assert_slot_open(service, pro, branch, start, ignore_notice=True)
            busy, _ = self.availability.busy_for(pro, branch, start - timedelta(days=1), start + timedelta(days=1))
            sequence = self.availability.next_sequence(start, busy)
        self.db.refresh(pro)
        if not service.is_active or (not staff and not service.is_bookable_online):
            raise ValidationFailed("This service cannot be booked online.", code="not_bookable")
        if not pro.is_active or (not staff and not pro.is_bookable_online):
            raise ValidationFailed("This professional cannot be booked online.", code="not_bookable")

        customer = self.customers.resolve(payload.customer, user=user, allow_guest=allow_guest, staff_booking=staff)
        from app.services.form_service import FormService

        forms = FormService(self.db, self.org, self.actor, self.meta)
        form = forms.resolve(service, branch)
        form_answers = forms.validate_answers(form, payload.form_answers) if form else None
        dependent_id = None
        if payload.dependent_id:
            dep = self.db.scalar(select(CustomerDependent).where(CustomerDependent.public_id == payload.dependent_id, CustomerDependent.customer_id == customer.id))
            if dep is None:
                raise NotFoundError("Family member not found.")
            dependent_id = dep.id

        duration, _ = appointment_length(service, pro, branch)
        coupon = None
        if payload.coupon_code:
            from app.services.coupon_service import CouponService

            base = quote(service, branch, pro)
            coupon = CouponService(self.db, self.org, self.actor, self.meta).validate(
                payload.coupon_code, service=service, price_paise=base.subtotal_paise - base.discount_paise, customer_id=customer.id
            )
        q = quote(service, branch, pro, coupon=coupon)
        now = utcnow()
        mode = payload.consultation_mode or ("online" if service.consultation_mode == "online" else "in_person")
        if service.consultation_mode == "in_person" and mode == "online":
            raise ValidationFailed("This service is in person only.")
        if service.consultation_mode == "online" and mode == "in_person":
            raise ValidationFailed("This service is online only.")

        if q.advance_due_paise == 0 or (staff and payload.confirm_without_payment):
            status, due_at = AppointmentStatus.CONFIRMED, None
        else:
            status = AppointmentStatus.PENDING_PAYMENT
            due_at = now + timedelta(minutes=int(self._setting("booking", "payment_window_minutes", self.settings.payment_window_minutes) or 30))

        appt = Appointment(
            organization_id=self.org.id, reference=new_reference("APT", self.org.code), branch_id=branch.id, professional_id=pro.id,
            service_id=service.id, customer_id=customer.id, dependent_id=dependent_id, hold_id=hold.id if hold else None,
            start_at=start, end_at=start + timedelta(minutes=duration), timezone=str(branch_tz(self.org, branch)), slot_sequence=sequence,
            consultation_mode=mode, status=status, source=payload.source if staff else AppointmentSource.ONLINE,
            booked_by_user_id=self.actor.id if self.actor else (user.id if user else None), is_walk_in=(payload.source == "walk_in"),
            is_follow_up=(service.kind == "follow_up"), currency=q.currency, subtotal_paise=q.subtotal_paise, discount_paise=q.discount_paise,
            tax_paise=q.tax_paise, total_amount_paise=q.total_amount_paise, advance_due_paise=q.advance_due_paise, paid_amount_paise=0,
            pricing_snapshot=q.as_snapshot(), customer_notes=payload.customer_notes, internal_notes=payload.internal_notes if staff else None,
            coupon_code=coupon.code if coupon is not None else None,
            payment_due_at=due_at, confirmed_at=now if status == AppointmentStatus.CONFIRMED else None,
            metadata_={"access_token": secrets.token_urlsafe(24)},
        )
        _insert_or_conflict(self.db, appt, "This slot was just taken. Please pick another time.")
        if hold:
            hold.status = HoldStatus.CONVERTED
            hold.customer_id = customer.id
        if form is not None and form_answers is not None:
            forms.record_response(form, form_answers, appointment=appt, customer=customer)
        self._history(appt, None, status, reason="created")
        if status == AppointmentStatus.PENDING_PAYMENT:
            from app.services.payment_service import PaymentService

            PaymentService(self.db, self.org, self.actor, self.meta).create_request(appt)
        record_audit(self.db, action="appointment.created", actor=self.actor, organization_id=self.org.id, entity_type="appointment",
                     entity_id=appt.reference, after={"status": status, "start_at": start.isoformat(), "total_paise": q.total_amount_paise}, meta=self.meta)
        return appt

    def create_recurring(self, payload: RecurringCreate, *, user: User | None, staff: bool) -> tuple[str, list[Appointment], list[dict]]:
        if not staff:
            raise PermissionDenied("Recurring bookings are created by staff.")
        if not (payload.professional_id and payload.branch_id and payload.service_id and payload.start_at):
            raise ValidationFailed("professional_id, branch_id, service_id and start_at are required.")
        group = str(uuid.uuid4())
        created: list[Appointment] = []
        skipped: list[dict] = []
        base = _utc(payload.start_at)
        for i in range(payload.occurrences):
            start = base + timedelta(days=payload.interval_days * i)
            single = AppointmentCreate(**{**payload.model_dump(exclude={"occurrences", "interval_days", "hold_id"}), "start_at": start, "hold_id": None})
            savepoint = self.db.begin_nested()
            try:
                appt = self.create(single, user=user, staff=True)
                appt.recurrence_group_id = group
                if created:
                    appt.parent_appointment_id = created[0].id
                savepoint.commit()
                created.append(appt)
            except (SlotUnavailable, ValidationFailed) as exc:
                if savepoint.is_active:
                    savepoint.rollback()
                skipped.append({"start_at": start.isoformat(), "reason": exc.detail})
        self.db.flush()
        return group, created, skipped

    # ----------------------------------------------------------- lifecycle
    def get(self, public_id: str) -> Appointment:
        appt = self.db.scalar(select(Appointment).options(selectinload(Appointment.status_history)).where(Appointment.public_id == public_id, Appointment.organization_id == self.org.id))
        if appt is None:
            raise NotFoundError("Appointment not found.")
        return appt

    def get_by_reference(self, reference: str, access_token: str | None = None, user: User | None = None) -> Appointment:
        appt = self.db.scalar(select(Appointment).options(selectinload(Appointment.status_history)).where(Appointment.reference == reference, Appointment.organization_id == self.org.id))
        if appt is None:
            raise NotFoundError("Appointment not found.")
        token = (appt.metadata_ or {}).get("access_token")
        customer = self.db.get(Customer, appt.customer_id)
        if user is not None and customer and customer.user_id == user.id:
            return appt
        if access_token and token and secrets.compare_digest(access_token, token):
            return appt
        raise PermissionDenied("Not allowed to view this appointment.", code="forbidden")

    def transition(self, appt: Appointment, action: str, *, reason: str | None = None, by_customer: bool = False) -> Appointment:
        allowed = TRANSITIONS.get(action)
        if allowed is None:
            raise ValidationFailed("Unknown action.")
        target = allowed.get(appt.status)
        if target is None:
            raise ConflictError(f"Cannot {action.replace('_', ' ')} an appointment that is {appt.status.replace('_', ' ')}.", code="invalid_transition")
        now = utcnow()
        if action == "cancel":
            self._cancel(appt, reason, by_customer, now)
        elif action == "confirm":
            appt.confirmed_at = now
        elif action == "check_in":
            appt.checked_in_at = now
        elif action == "start":
            appt.started_at = now
        elif action == "complete":
            appt.completed_at = now
        previous = appt.status
        appt.status = target
        self.db.flush()
        self._history(appt, previous, target, reason=reason or action, extra={"by_customer": True} if by_customer else None)
        record_audit(self.db, action=f"appointment.{action}", actor=self.actor, organization_id=self.org.id, entity_type="appointment", entity_id=appt.reference,
                     before={"status": previous}, after={"status": target}, purpose=reason, meta=self.meta)
        if action in ("cancel", "expire"):
            from app.core.enums import PaymentStatus
            from app.services.payment_service import PaymentService

            closed = PaymentStatus.CANCELLED if action == "cancel" else PaymentStatus.EXPIRED
            PaymentService(self.db, self.org, self.actor, self.meta).close_open(appt, closed, reason or action)
        return appt

    def move(self, appt: Appointment, target: str, *, reason: str) -> Appointment:
        """Internal status change driven by another module (payments). Writes history and audit like ``transition``."""
        previous = appt.status
        if previous == target:
            return appt
        if target == AppointmentStatus.CONFIRMED:
            appt.confirmed_at = utcnow()
            appt.payment_due_at = None
        appt.status = target
        self.db.flush()
        self._history(appt, previous, target, reason=reason)
        record_audit(self.db, action=f"appointment.{target}", actor=self.actor, organization_id=self.org.id, entity_type="appointment", entity_id=appt.reference,
                     before={"status": previous}, after={"status": target}, purpose=reason, meta=self.meta)
        return appt

    def cancellation_rules(self, appt: Appointment) -> dict:
        service = self.db.get(Service, appt.service_id)
        org_rules = OrganizationService(self.db).get_settings(self.org, "cancellation")["cancellation"]
        rules = {**org_rules, **(service.cancellation_policy or {})} if service else org_rules
        return rules

    def customer_can(self, appt: Appointment, what: str) -> bool:
        if appt.status not in (AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION, AppointmentStatus.CONFIRMED):
            return False
        rules = self.cancellation_rules(appt)
        hours = float(rules.get(f"{what}_before_hours", 0) or 0)
        enabled = bool(rules.get(f"customer_can_{what}", True))
        if what == "reschedule":
            count = self.db.scalar(select(func.count()).select_from(AppointmentReschedule).where(AppointmentReschedule.appointment_id == appt.id)) or 0
            if count >= int(rules.get("max_reschedules", 99) or 99):
                return False
        return enabled and appt.start_at - timedelta(hours=hours) > utcnow()

    def _cancel(self, appt: Appointment, reason: str | None, by_customer: bool, now: datetime) -> None:
        rules = self.cancellation_rules(appt)
        if by_customer and not self.customer_can(appt, "cancel"):
            raise PermissionDenied("This appointment can no longer be cancelled online. Please contact the clinic.", code="cancel_window_closed")
        hours = float(rules.get("cancel_before_hours", 0) or 0)
        refund_eligible = appt.paid_amount_paise if appt.start_at - timedelta(hours=hours) > now else 0
        appt.cancelled_at = now
        self.db.add(AppointmentCancellation(
            organization_id=self.org.id, appointment_id=appt.id, cancelled_by_user_id=self.actor.id if self.actor else None,
            cancelled_by_role="customer" if by_customer else ("staff" if self.actor else "system"), reason=reason, policy_snapshot=rules,
            refund_eligible_paise=refund_eligible, cancelled_at=now,
        ))
        self.db.flush()
        from app.services.refund_service import RefundService

        RefundService(self.db, self.org, self.actor, self.meta).auto_request_for_cancellation(appt, refund_eligible, reason)

    def reschedule(self, appt: Appointment, payload: RescheduleRequest, *, by_customer: bool = False, session_key: str | None = None) -> Appointment:
        if appt.status not in (AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION, AppointmentStatus.CONFIRMED):
            raise ConflictError("Only upcoming appointments can be rescheduled.", code="invalid_transition")
        if by_customer and not self.customer_can(appt, "reschedule"):
            raise PermissionDenied("This appointment can no longer be rescheduled online. Please contact the clinic.", code="reschedule_window_closed")
        service = self.db.get(Service, appt.service_id)
        branch = self.db.get(Branch, appt.branch_id)
        old = (appt.start_at, appt.end_at, appt.professional_id)
        if payload.hold_id:
            hold = self._get_hold(payload.hold_id, session_key if by_customer else None)
            if hold.service_id != appt.service_id or hold.branch_id != appt.branch_id:
                raise ValidationFailed("The hold must be for the same service and branch.")
            pro = self.db.get(Professional, hold.professional_id)
            new_start, sequence = hold.start_at, hold.slot_sequence
            hold.status = HoldStatus.CONVERTED
        else:
            if by_customer:
                raise ValidationFailed("Reserve the new slot first (hold_id).", code="hold_required")
            if payload.start_at is None:
                raise ValidationFailed("start_at is required.")
            pro = self.catalog.get_professional(payload.professional_id) if payload.professional_id else self.db.get(Professional, appt.professional_id)
            new_start = _utc(payload.start_at)
            self._lock_professional(pro)
            self.availability.expire_stale_holds()
            self.db.refresh(pro)
            self._assert_slot_open(service, pro, branch, new_start, ignore_notice=True, exclude_appointment_id=appt.id)
            busy, _ = self.availability.busy_for(pro, branch, new_start - timedelta(days=1), new_start + timedelta(days=1), exclude_appointment_id=appt.id)
            sequence = self.availability.next_sequence(new_start, busy)
        self.db.refresh(pro)
        duration, _ = appointment_length(service, pro, branch)
        appt.professional_id = pro.id
        appt.start_at = new_start
        appt.end_at = new_start + timedelta(minutes=duration)
        appt.slot_sequence = sequence
        try:
            with self.db.begin_nested():
                self.db.flush()
        except IntegrityError as exc:
            raise SlotUnavailable("This slot was just taken. Please pick another time.") from exc
        now = utcnow()
        self.db.add(AppointmentReschedule(
            organization_id=self.org.id, appointment_id=appt.id, old_start_at=old[0], old_end_at=old[1], new_start_at=appt.start_at, new_end_at=appt.end_at,
            old_professional_id=old[2], new_professional_id=pro.id, rescheduled_by_user_id=self.actor.id if self.actor else None, reason=payload.reason, rescheduled_at=now,
        ))
        self._history(appt, appt.status, appt.status, reason=f"rescheduled: {payload.reason or ''}".strip(), extra={"from": old[0].isoformat(), "to": appt.start_at.isoformat()})
        record_audit(self.db, action="appointment.rescheduled", actor=self.actor, organization_id=self.org.id, entity_type="appointment", entity_id=appt.reference,
                     before={"start_at": old[0].isoformat()}, after={"start_at": appt.start_at.isoformat()}, purpose=payload.reason, meta=self.meta)
        return appt

    def _history(self, appt: Appointment, from_status: str | None, to_status: str, *, reason: str | None, extra: dict | None = None) -> None:
        self.db.add(AppointmentStatusHistory(
            appointment_id=appt.id, from_status=from_status, to_status=to_status, changed_by_user_id=self.actor.id if self.actor else None,
            reason=reason, changed_at=utcnow(), metadata_=extra,
        ))
        self.db.flush()
        from app.services.notification_service import NotificationService

        NotificationService(self.db, self.org, self.actor, self.meta).on_appointment_status(appt, from_status, to_status, reason=reason, extra=extra)

    # -------------------------------------------------------------- lists
    def list(self, *, from_at: datetime | None, to_at: datetime | None, professional_id: str | None, branch_id: str | None, status: str | None, customer_id: str | None, search: str | None, restrict_professional_id: int | None = None) -> list[Appointment]:
        stmt = select(Appointment).where(Appointment.organization_id == self.org.id)
        if from_at:
            stmt = stmt.where(Appointment.end_at >= _utc(from_at))
        if to_at:
            stmt = stmt.where(Appointment.start_at <= _utc(to_at))
        if professional_id:
            stmt = stmt.where(Appointment.professional_id == self.catalog.get_professional(professional_id).id)
        if restrict_professional_id:
            stmt = stmt.where(Appointment.professional_id == restrict_professional_id)
        if branch_id:
            stmt = stmt.where(Appointment.branch_id == self.catalog.get_branch(branch_id).id)
        if status:
            stmt = stmt.where(Appointment.status.in_(status.split(",")))
        if customer_id:
            stmt = stmt.where(Appointment.customer_id == self.customers.get(customer_id).id)
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.join(Customer, Customer.id == Appointment.customer_id).where(
                func.lower(Customer.full_name).like(like) | Customer.mobile.like(like) | func.lower(Appointment.reference).like(like)
            )
        return list(self.db.scalars(stmt.order_by(Appointment.start_at)).all())

    def list_for_user(self, user: User) -> list[Appointment]:
        stmt = (
            select(Appointment).join(Customer, Customer.id == Appointment.customer_id)
            .where(Customer.user_id == user.id).order_by(Appointment.start_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    # ----------------------------------------------------------- waitlist
    def add_to_waitlist(self, payload: WaitlistCreate, *, user: User | None, staff: bool) -> Waitlist:
        allow_guest = bool(self._setting("booking", "allow_guest_booking", True))
        customer = self.customers.resolve(payload.customer, user=user, allow_guest=allow_guest, staff_booking=staff)
        row = Waitlist(
            organization_id=self.org.id, customer_id=customer.id,
            branch_id=self.catalog.get_branch(payload.branch_id).id if payload.branch_id else None,
            professional_id=self.catalog.get_professional(payload.professional_id).id if payload.professional_id else None,
            service_id=self.catalog.get_service(payload.service_id).id if payload.service_id else None,
            preferred_date=_utc(payload.preferred_date) if payload.preferred_date else None, notes=payload.notes,
        )
        _insert_or_conflict(self.db, row, "Already on the waitlist for this date.", code="already_waitlisted")
        return row

    def list_waitlist(self) -> list[Waitlist]:
        return list(self.db.scalars(select(Waitlist).where(Waitlist.organization_id == self.org.id, Waitlist.status == "waiting").order_by(Waitlist.created_at)).all())

    def remove_from_waitlist(self, public_id: str) -> None:
        row = self.db.scalar(select(Waitlist).where(Waitlist.public_id == public_id, Waitlist.organization_id == self.org.id))
        if row is None:
            raise NotFoundError("Waitlist entry not found.")
        row.status = "removed"
        self.db.flush()


def _utc(value: datetime) -> datetime:
    from datetime import UTC

    if value.tzinfo is None:
        raise ValidationFailed("Datetimes must include a timezone offset (e.g. 2026-01-05T09:30:00+05:30).", code="naive_datetime")
    return value.astimezone(UTC)


def expire_unpaid_appointments(db: Session, org: Organization | None = None) -> int:
    """Move PENDING_PAYMENT appointments past their payment window to EXPIRED (frees the slot)."""
    now = utcnow()
    stmt = select(Appointment).where(Appointment.status == AppointmentStatus.PENDING_PAYMENT, Appointment.payment_due_at.is_not(None), Appointment.payment_due_at < now)
    if org:
        stmt = stmt.where(Appointment.organization_id == org.id)
    count = 0
    for appt in db.scalars(stmt).all():
        org_row = org or db.get(Organization, appt.organization_id)
        AppointmentService(db, org_row).transition(appt, "expire", reason="payment window elapsed")
        count += 1
    return count
