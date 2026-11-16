"""Own-UPI payment lifecycle.

INITIATED/AWAITING_PAYMENT ──customer submits UTR/screenshot──▶ SUBMITTED ──staff opens──▶ UNDER_REVIEW
        │                                                         │                            │
        │                                                         └──────────┬─────────────────┘
        │                                                     staff verifies bank credit │ staff rejects (reason)
        ▼                                                                    ▼           ▼
   EXPIRED / CANCELLED                                                   VERIFIED     REJECTED ──customer resubmits──▶ SUBMITTED

Hard rules enforced here:
* amounts are computed from the appointment, never taken from the client;
* a submission (UTR, screenshot) never changes money state – only ``verify`` does, and only for users
  holding ``payments:verify`` who confirm the bank credit;
* a UTR can back exactly one payment per organization (unique index + explicit duplicate handling);
* every transition writes an immutable ``payment_verification_logs`` row and an audit entry.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import lock_row
from app.core.enums import AppointmentStatus, PaymentKind, PaymentMethod, PaymentStatus
from app.core.exceptions import ConflictError, DuplicateUTR, NotFoundError, PermissionDenied, ValidationFailed
from app.core.ids import new_reference
from app.core.preload import preload
from app.core.storage import get_storage, validate_upload
from app.core.time import utcnow
from app.models import (
    Appointment,
    Branch,
    Customer,
    Organization,
    Payment,
    PaymentSubmission,
    PaymentVerificationLog,
    Service,
    UPIAccount,
    User,
)
from app.payments.upi import normalize_utr, qr_data_url
from app.schemas.payment import (
    Checkout,
    CheckoutUPI,
    PaymentCreate,
    PaymentDetail,
    PaymentRead,
    PaymentStats,
    RejectRequest,
    SubmissionRead,
    VerificationLogRead,
    VerifyRequest,
)
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService
from app.services.privacy_service import view_mobile
from app.services.upi_account_service import UPIAccountService

OPEN_STATUSES = (PaymentStatus.INITIATED, PaymentStatus.AWAITING_PAYMENT, PaymentStatus.REJECTED)
IN_REVIEW_STATUSES = (PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW)
SUBMITTABLE = (PaymentStatus.INITIATED, PaymentStatus.AWAITING_PAYMENT, PaymentStatus.REJECTED)
SCREENSHOT_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


class PaymentService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()
        self.accounts = UPIAccountService(db, org, actor, meta)

    # ------------------------------------------------------------- helpers
    def _settings(self, namespace: str) -> dict:
        return OrganizationService(self.db).get_settings(self.org, namespace)[namespace]

    def _window(self) -> timedelta:
        return timedelta(minutes=int(self._settings("booking").get("payment_window_minutes") or get_settings().payment_window_minutes))

    def _log(self, payment: Payment, action: str, from_status: str | None, to_status: str, *, reason: str | None = None,
             bank_credit_confirmed: bool | None = None, details: dict | None = None) -> None:
        self.db.add(PaymentVerificationLog(
            organization_id=self.org.id, payment_id=payment.id, actor_user_id=self.actor.id if self.actor else None, action=action,
            from_status=from_status, to_status=to_status, reason=reason, bank_credit_confirmed=bank_credit_confirmed, details=details, created_at=utcnow(),
        ))
        self.db.flush()
        record_audit(self.db, action=f"payment.{action}", actor=self.actor, organization_id=self.org.id, entity_type="payment", entity_id=payment.reference,
                     before={"status": from_status}, after={"status": to_status, **(details or {})}, purpose=reason, meta=self.meta)

    def _set_status(self, payment: Payment, to: str, action: str, **kwargs) -> None:
        before = payment.status
        payment.status = to
        self._log(payment, action, before, to, **kwargs)

    def _appointments(self):
        from app.services.appointment_service import AppointmentService

        return AppointmentService(self.db, self.org, self.actor, self.meta)

    def _notifications(self):
        from app.services.notification_service import NotificationService

        return NotificationService(self.db, self.org, self.actor, self.meta)

    def get(self, public_id: str) -> Payment:
        p = self.db.scalar(select(Payment).where(Payment.public_id == public_id, Payment.organization_id == self.org.id))
        if p is None:
            raise NotFoundError("Payment not found.")
        return p

    def for_appointment(self, appt: Appointment) -> list[Payment]:
        return list(self.db.scalars(select(Payment).where(Payment.appointment_id == appt.id).order_by(Payment.id)).all())

    def current_for_appointment(self, appt: Appointment) -> Payment | None:
        """The payment a customer should act on: open or in review first, otherwise the latest one."""
        rows = self.for_appointment(appt)
        for p in reversed(rows):
            if p.status in OPEN_STATUSES or p.status in IN_REVIEW_STATUSES:
                return p
        return rows[-1] if rows else None

    def outstanding(self, appt: Appointment, kind: str) -> int:
        paid = appt.paid_amount_paise or 0
        if kind == PaymentKind.ADVANCE:
            return max(0, appt.advance_due_paise - paid)
        return max(0, appt.total_amount_paise - paid)

    # ------------------------------------------------------------- create
    def create_request(self, appt: Appointment, *, kind: str = PaymentKind.ADVANCE, method: str = PaymentMethod.UPI_QR, action: str = "requested") -> Payment:
        amount = self.outstanding(appt, kind)
        if amount <= 0:
            raise ConflictError("Nothing is due for this appointment.", code="nothing_due")
        service = self.db.get(Service, appt.service_id)
        account = self.accounts.select_for(service, appt.branch_id) if method == PaymentMethod.UPI_QR else None
        payment = Payment(
            organization_id=self.org.id, reference=new_reference("PAY", self.org.code), appointment_id=appt.id, customer_id=appt.customer_id,
            upi_account_id=account.id if account else None, branch_id=appt.branch_id, kind=kind, method=method, status=PaymentStatus.INITIATED,
            currency=appt.currency, amount_paise=amount, expires_at=appt.payment_due_at or (utcnow() + self._window()),
            recorded_by_user_id=self.actor.id if self.actor else None,
        )
        if account is not None:
            payment.upi_uri = self.accounts.request_for(account, amount if account.use_dynamic_qr else None, payment.reference, note=f"{appt.reference}").uri()
        self.db.add(payment)
        self.db.flush()
        self._log(payment, "created", None, PaymentStatus.INITIATED, details={"amount_paise": amount, "kind": kind, "method": method,
                                                                               "upi_account": account.public_id if account else None})
        if method == PaymentMethod.UPI_QR:
            self._set_status(payment, PaymentStatus.AWAITING_PAYMENT, action)
        return payment

    def staff_create(self, payload: PaymentCreate) -> Payment:
        appt = lock_row(self.db, self._appointments().get(payload.appointment_id))  # one money record per appointment at a time
        if appt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.EXPIRED, AppointmentStatus.NO_SHOW):
            raise ConflictError("This appointment is closed.", code="appointment_closed")
        open_rows = [p for p in self.for_appointment(appt) if p.status in OPEN_STATUSES or p.status in IN_REVIEW_STATUSES]
        if any(p.status in IN_REVIEW_STATUSES for p in open_rows):
            raise ConflictError("A submitted payment is waiting for verification. Verify or reject it first.", code="payment_in_review")
        if payload.method == PaymentMethod.CASH:
            if not (self.actor and self._has("payments:record")):
                raise PermissionDenied("Missing permission: payments:record", code="permission_denied")
            for p in open_rows:  # a cash payment replaces any unpaid UPI request
                self._set_status(p, PaymentStatus.CANCELLED, "cancelled", reason="Replaced by cash payment")
            payment = self.create_request(appt, kind=payload.kind, method=PaymentMethod.CASH, action="cash_recorded")
            self._mark_verified(payment, payment.amount_paise, action="cash_recorded", reason=payload.notes, bank_credit_confirmed=None)
            return payment
        if open_rows:
            raise ConflictError("An unpaid payment request already exists for this appointment.", code="open_payment_exists")
        payment = self.create_request(appt, kind=payload.kind, method=payload.method)
        if payload.method == PaymentMethod.BANK_TRANSFER:
            self.submit(payment, utr=payload.utr or "", transaction_reference=None, paid_at=None, payer_upi_id=None, notes=payload.notes, screenshot=None, staff=True)
        return payment

    def _has(self, permission: str) -> bool:
        from app.repositories.organizations import MembershipRepository

        if self.actor is None:
            return False
        if self.actor.is_platform_admin:
            return True
        m = MembershipRepository(self.db).get_for_user_in_org(self.actor.id, self.org.id)
        return bool(m and any(p.code == permission for p in m.role.permissions))

    # ------------------------------------------------------------- submit
    def submit(self, payment: Payment, *, utr: str, transaction_reference: str | None, paid_at: datetime | None, payer_upi_id: str | None,
               notes: str | None, screenshot: bytes | None, staff: bool = False, submitted_ip: str | None = None) -> PaymentSubmission:
        lock_row(self.db, payment)
        if payment.status in IN_REVIEW_STATUSES:
            raise ConflictError("This payment is already submitted and waiting for verification.", code="already_submitted")
        if payment.status not in SUBMITTABLE:
            raise ConflictError(f"This payment is {payment.status.replace('_', ' ')} and cannot take a submission.", code="payment_closed")
        appt = self.db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        if appt is not None and appt.status in (AppointmentStatus.CANCELLED, AppointmentStatus.EXPIRED, AppointmentStatus.NO_SHOW):
            raise ConflictError("This appointment is no longer active. Contact the clinic if you have already paid.", code="appointment_closed")
        if payment.method == PaymentMethod.UPI_QR and payment.expires_at and payment.expires_at < utcnow() and not staff and payment.status != PaymentStatus.REJECTED:
            raise ConflictError("The payment window has closed. Contact the clinic if you have already paid.", code="payment_expired")
        try:
            utr_n = normalize_utr(utr)
        except ValueError as exc:
            raise ValidationFailed(str(exc), code="invalid_utr") from exc
        if self._settings("payment").get("require_screenshot") and not screenshot and not staff:
            raise ValidationFailed("Please attach a screenshot of the payment.", code="screenshot_required")

        existing = self.db.scalar(select(PaymentSubmission).where(PaymentSubmission.organization_id == self.org.id, PaymentSubmission.utr_normalized == utr_n))
        if existing is not None and existing.payment_id != payment.id:
            other = self.db.get(Payment, existing.payment_id)
            details = {"utr": utr_n, "other_payment": other.reference if other else None}
            self._log(payment, "duplicate_utr_attempt", payment.status, payment.status, reason="UTR already used for another payment", details=details)
            if other is not None:
                self._log(other, "duplicate_utr_attempt", other.status, other.status, reason="Same UTR submitted for another payment", details={"utr": utr_n, "other_payment": payment.reference})
            raise DuplicateUTR("This UTR has already been submitted for another payment. Check the reference in your UPI app or contact the clinic.", persist=True)

        stored = None
        if screenshot:
            mime = validate_upload(screenshot, allowed=SCREENSHOT_TYPES, max_mb=get_settings().max_upload_size_mb)
            stored = get_storage().save(scope=f"org/{self.org.public_id}/payments/{payment.public_id}", visibility="private", data=screenshot, mime_type=mime)

        for prev in self.db.scalars(select(PaymentSubmission).where(PaymentSubmission.payment_id == payment.id)).all():
            prev.is_superseded = True
        if existing is not None:  # resubmitting the same UTR for the same payment after a rejection
            sub = existing
            sub.is_superseded = False
        else:
            sub = PaymentSubmission(organization_id=self.org.id, payment_id=payment.id, utr_normalized=utr_n)
            self.db.add(sub)
        sub.utr = utr.strip()[:64]
        sub.transaction_reference = (transaction_reference or "").strip()[:128] or None
        sub.payer_upi_id = (payer_upi_id or "").strip()[:120] or None
        sub.paid_at = paid_at
        sub.claimed_amount_paise = payment.amount_paise
        sub.notes = (notes or "").strip()[:2000] or None
        sub.submitted_by_user_id = self.actor.id if self.actor else None
        sub.submitted_ip = submitted_ip or self.meta.ip_address
        if stored is not None:
            sub.screenshot_path = stored.key
            sub.screenshot_mime = stored.mime_type
        self.db.flush()

        payment.submitted_at = utcnow()
        payment.rejection_reason = None
        self._set_status(payment, PaymentStatus.SUBMITTED, "submitted", details={"utr": utr_n, "screenshot": stored is not None, "by": "staff" if staff else "customer"})
        if appt is not None and appt.status == AppointmentStatus.PENDING_PAYMENT:
            self._appointments().move(appt, AppointmentStatus.PENDING_VERIFICATION, reason="payment submitted for verification")
        from app.webhooks.hooks import on_payment

        on_payment(self.db, self.org, payment, "payment.submitted")
        notes = self._notifications()
        if not staff:
            notes.emit("payment.submitted", appointment=appt, payment=payment)
        notes.emit("staff.payment_to_verify", appointment=appt, payment=payment)
        return sub

    # ------------------------------------------------------------- review
    def start_review(self, payment: Payment) -> Payment:
        lock_row(self.db, payment)
        if payment.status != PaymentStatus.SUBMITTED:
            raise ConflictError("Only submitted payments can be taken for review.", code="invalid_transition")
        self._set_status(payment, PaymentStatus.UNDER_REVIEW, "review_started")
        return payment

    def verify(self, payment: Payment, req: VerifyRequest) -> Payment:
        lock_row(self.db, payment)  # two people approving at once: the second waits, then sees "verified" and is refused
        if payment.status not in IN_REVIEW_STATUSES:
            raise ConflictError("Only submitted payments can be verified.", code="invalid_transition")
        if not req.bank_credit_confirmed:
            raise ValidationFailed("Confirm that the amount was credited to the bank account before approving.", code="bank_credit_unconfirmed")
        if req.verified_amount_paise != payment.amount_paise and not (req.amount_mismatch_reason and req.amount_mismatch_reason.strip()):
            raise ValidationFailed("The credited amount differs from the amount due. Add a reason to approve a different amount.", code="amount_mismatch")
        self._mark_verified(payment, req.verified_amount_paise, action="verified", reason=req.notes, bank_credit_confirmed=True,
                            extra={"amount_mismatch_reason": req.amount_mismatch_reason} if req.verified_amount_paise != payment.amount_paise else None)
        return payment

    def _mark_verified(self, payment: Payment, amount: int, *, action: str, reason: str | None, bank_credit_confirmed: bool | None, extra: dict | None = None) -> None:
        now = utcnow()
        payment.verified_amount_paise = amount
        payment.verified_at = now
        payment.verified_by_user_id = self.actor.id if self.actor else None
        self._set_status(payment, PaymentStatus.VERIFIED, action, reason=reason, bank_credit_confirmed=bank_credit_confirmed,
                         details={"verified_amount_paise": amount, **(extra or {})})
        from app.webhooks.hooks import on_payment

        on_payment(self.db, self.org, payment, "payment.verified")
        appt = self.db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        if appt is None:
            return
        lock_row(self.db, appt)  # advance and balance verified at the same moment must both be added
        appt.paid_amount_paise = (appt.paid_amount_paise or 0) + amount
        self.db.flush()
        if appt.status in (AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING_VERIFICATION):
            if appt.paid_amount_paise >= appt.advance_due_paise:
                self._appointments().move(appt, AppointmentStatus.CONFIRMED, reason=f"payment {payment.reference} verified")  # sends the confirmation
            else:
                appt.payment_due_at = now + self._window()
                self._appointments().move(appt, AppointmentStatus.PENDING_PAYMENT, reason="verified amount is less than the advance due")
        else:
            self._notifications().emit("payment.verified", appointment=appt, payment=payment)

    def reject(self, payment: Payment, req: RejectRequest) -> Payment:
        from app.core.observability import security_event

        lock_row(self.db, payment)
        security_event("payment_rejected")
        if payment.status not in IN_REVIEW_STATUSES:
            raise ConflictError("Only submitted payments can be rejected.", code="invalid_transition")
        now = utcnow()
        payment.rejected_at = now
        payment.rejection_reason = req.reason.strip()
        payment.expires_at = now + self._window()
        self._set_status(payment, PaymentStatus.REJECTED, "rejected", reason=req.reason, bank_credit_confirmed=False, details={"notes": req.notes} if req.notes else None)
        appt = self.db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        if appt is not None and appt.status == AppointmentStatus.PENDING_VERIFICATION:
            appt.payment_due_at = payment.expires_at
            self._appointments().move(appt, AppointmentStatus.PENDING_PAYMENT, reason=f"payment rejected: {req.reason}")
        from app.services.notification_service import fmt_date, fmt_time
        from app.webhooks.hooks import on_payment

        on_payment(self.db, self.org, payment, "payment.rejected")
        tz = appt.timezone if appt is not None else None
        self._notifications().emit("payment.rejected", appointment=appt, payment=payment, extra={
            "reason": req.reason.strip(), "payment_deadline": f"{fmt_date(payment.expires_at, tz)}, {fmt_time(payment.expires_at, tz)}"})
        return payment

    def add_note(self, payment: Payment, notes: str) -> None:
        self._log(payment, "note", payment.status, payment.status, reason=notes)

    def close_open(self, appt: Appointment, to: str, reason: str) -> int:
        """Called when an appointment is cancelled or expires. Requests that were never paid are closed;
        payments already submitted stay for staff to verify and then refund, so money is never lost."""
        n = 0
        for p in self.for_appointment(appt):
            if p.status in OPEN_STATUSES:
                self._set_status(p, to, to, reason=reason)
                n += 1
        return n

    # ------------------------------------------------------------- output
    def checkout(self, payment: Payment) -> Checkout:
        account = self.db.get(UPIAccount, payment.upi_account_id) if payment.upi_account_id else None
        upi = None
        if account is not None and payment.method == PaymentMethod.UPI_QR:
            req = self.accounts.request_for(account, payment.amount_paise if account.use_dynamic_qr else None, payment.reference, note=self._appointment_ref(payment))
            uri = req.uri()
            upi = CheckoutUPI(
                account_name=account.display_name, upi_id=account.upi_id, merchant_name=account.merchant_name,
                instructions=account.payment_instructions if self._settings("payment").get("show_payment_instructions", True) else None,
                is_static=not account.use_dynamic_qr, upi_uri=uri, qr_data_url=qr_data_url(uri) if account.use_dynamic_qr else None,
                static_qr_url=account.static_qr_path if not account.use_dynamic_qr else None, app_links=req.app_links(),
            )
        subs = self.submissions(payment)
        latest = subs[0] if subs else None
        can_submit = payment.status in SUBMITTABLE and upi is not None
        message = None
        if payment.method == PaymentMethod.UPI_QR and upi is None:
            message = "This clinic has not set up UPI payments yet. Please contact them to pay."
        elif payment.status == PaymentStatus.REJECTED:
            message = f"Your last submission was not accepted: {payment.rejection_reason}. Check the details and submit again."
        elif payment.status in IN_REVIEW_STATUSES:
            message = "Thanks. The clinic is checking the payment with their bank. Your booking is confirmed once they verify it."
        elif payment.status == PaymentStatus.VERIFIED:
            message = "Payment verified by the clinic."
        return Checkout(payment=self.to_read(payment), upi=upi, can_submit=can_submit, latest_submission=latest, message=message)

    def _appointment_ref(self, payment: Payment) -> str | None:
        if not payment.appointment_id:
            return None
        appt = self.db.get(Appointment, payment.appointment_id)
        return appt.reference if appt else None

    def submissions(self, payment: Payment) -> list[SubmissionRead]:
        rows = self.db.scalars(select(PaymentSubmission).where(PaymentSubmission.payment_id == payment.id).order_by(PaymentSubmission.updated_at.desc(), PaymentSubmission.id.desc())).all()
        return [SubmissionRead(id=s.public_id, utr=s.utr, transaction_reference=s.transaction_reference, payer_upi_id=s.payer_upi_id, payer_name=s.payer_name, paid_at=s.paid_at,
                               claimed_amount_paise=s.claimed_amount_paise, has_screenshot=bool(s.screenshot_path), notes=s.notes, is_superseded=s.is_superseded, created_at=s.created_at) for s in rows]

    def logs(self, payment: Payment) -> list[VerificationLogRead]:
        rows = self.db.scalars(select(PaymentVerificationLog).where(PaymentVerificationLog.payment_id == payment.id).order_by(PaymentVerificationLog.id)).all()
        names = dict(self.db.execute(select(User.id, User.full_name).where(User.id.in_({r.actor_user_id for r in rows if r.actor_user_id}))).all()) if rows else {}
        return [VerificationLogRead(action=r.action, from_status=r.from_status, to_status=r.to_status, reason=r.reason, bank_credit_confirmed=r.bank_credit_confirmed,
                                    actor_name=names.get(r.actor_user_id), details=r.details, created_at=r.created_at) for r in rows]

    def prepare_reads(self, rows: list[Payment]) -> list[Payment]:
        """Batch everything to_read needs for a page of payments (a fixed number of queries, not several per row)."""
        appts = preload(self.db, Appointment, (p.appointment_id for p in rows))
        preload(self.db, Service, (a.service_id for a in appts.values()))
        preload(self.db, Branch, (p.branch_id for p in rows))
        preload(self.db, Customer, (p.customer_id for p in rows))
        preload(self.db, UPIAccount, (p.upi_account_id for p in rows))
        ids = [p.id for p in rows]
        self._latest_utr = {}
        self._dup_flags = set()
        if ids:
            for pid, utr in self.db.execute(select(PaymentSubmission.payment_id, PaymentSubmission.utr).where(
                    PaymentSubmission.payment_id.in_(ids), PaymentSubmission.is_superseded.is_(False)).order_by(PaymentSubmission.id)):
                self._latest_utr[pid] = utr  # ordered by id, so the newest wins
            self._dup_flags = set(self.db.scalars(select(PaymentVerificationLog.payment_id).where(
                PaymentVerificationLog.payment_id.in_(ids), PaymentVerificationLog.action == "duplicate_utr_attempt").distinct()))
        self._batched = set(ids)
        return rows

    def to_read(self, p: Payment) -> PaymentRead:
        appt = self.db.get(Appointment, p.appointment_id) if p.appointment_id else None
        svc = self.db.get(Service, appt.service_id) if appt else None
        branch = self.db.get(Branch, p.branch_id) if p.branch_id else None
        cust = self.db.get(Customer, p.customer_id) if p.customer_id else None
        acct = self.db.get(UPIAccount, p.upi_account_id) if p.upi_account_id else None
        if p.id in getattr(self, "_batched", ()):
            latest, dup = self._latest_utr.get(p.id), int(p.id in self._dup_flags)
        else:
            latest = self.db.scalar(select(PaymentSubmission.utr).where(PaymentSubmission.payment_id == p.id, PaymentSubmission.is_superseded.is_(False)).order_by(PaymentSubmission.id.desc()))
            dup = self.db.scalar(select(func.count()).select_from(PaymentVerificationLog).where(PaymentVerificationLog.payment_id == p.id, PaymentVerificationLog.action == "duplicate_utr_attempt")) or 0
        return PaymentRead(
            id=p.public_id, reference=p.reference, status=p.status, kind=p.kind, method=p.method, currency=p.currency, amount_paise=p.amount_paise,
            verified_amount_paise=p.verified_amount_paise, expires_at=p.expires_at, submitted_at=p.submitted_at, verified_at=p.verified_at, rejected_at=p.rejected_at,
            rejection_reason=p.rejection_reason, appointment_id=appt.public_id if appt else None, appointment_reference=appt.reference if appt else None,
            appointment_start_at=appt.start_at if appt else None, appointment_timezone=appt.timezone if appt else None, appointment_status=appt.status if appt else None, service_name=svc.name if svc else None,
            branch_name=branch.name if branch else None, customer_id=cust.public_id if cust else None, customer_name=cust.full_name if cust else None,
            customer_mobile=view_mobile(self.db, cust.mobile) if cust else None, upi_account_id=acct.public_id if acct else None, upi_account_name=acct.display_name if acct else None,
            upi_id=acct.upi_id if acct else None, latest_utr=latest, duplicate_utr_flag=dup > 0, created_at=p.created_at,
        )

    def to_detail(self, p: Payment) -> PaymentDetail:
        from app.services.reconciliation_service import ReconciliationService
        from app.services.refund_service import REFUNDABLE_PAYMENT_STATUSES, RefundService

        refund = RefundService(self.db, self.org, self.actor, self.meta).summary(p) if p.status in REFUNDABLE_PAYMENT_STATUSES else None
        return PaymentDetail(**self.to_read(p).model_dump(), submissions=self.submissions(p), logs=self.logs(p), notes=p.notes,
                             bank_evidence=ReconciliationService(self.db, self.org, self.actor, self.meta).evidence_for(p), refund=refund)

    # -------------------------------------------------------------- lists
    def list(self, *, status: str | None, method: str | None, from_at: datetime | None, to_at: datetime | None, search: str | None,
             appointment_id: str | None, customer_id: str | None, page: int, page_size: int) -> tuple[list[Payment], int]:
        stmt = select(Payment).where(Payment.organization_id == self.org.id)
        if status:
            stmt = stmt.where(Payment.status.in_(status.split(",")))
        if method:
            stmt = stmt.where(Payment.method == method)
        if from_at:
            stmt = stmt.where(Payment.created_at >= from_at)
        if to_at:
            stmt = stmt.where(Payment.created_at <= to_at)
        if appointment_id:
            stmt = stmt.where(Payment.appointment_id == self._appointments().get(appointment_id).id)
        if customer_id:
            cust = self.db.scalar(select(Customer).where(Customer.public_id == customer_id, Customer.organization_id == self.org.id))
            if cust is None:
                raise NotFoundError("Customer not found.")
            stmt = stmt.where(Payment.customer_id == cust.id)
        if search:
            like = f"%{search.strip().upper()}%"
            sub_ids = select(PaymentSubmission.payment_id).where(PaymentSubmission.organization_id == self.org.id, PaymentSubmission.utr_normalized.like(like))
            cust_ids = select(Customer.id).where(Customer.organization_id == self.org.id, or_(func.upper(Customer.full_name).like(like), Customer.mobile.like(f"%{search.strip()}%")))
            stmt = stmt.where(or_(func.upper(Payment.reference).like(like), Payment.id.in_(sub_ids), Payment.customer_id.in_(cust_ids)))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        order = Payment.submitted_at.asc().nullslast() if status and set(status.split(",")) <= {"submitted", "under_review"} else Payment.created_at.desc()
        rows = self.db.scalars(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    def stats(self) -> PaymentStats:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        def count(*statuses):
            return int(self.db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id == self.org.id, Payment.status.in_(statuses))) or 0)

        pending = self.db.scalar(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(Payment.organization_id == self.org.id, Payment.status.in_([PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW]))) or 0
        verified_today = self.db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id == self.org.id, Payment.status == PaymentStatus.VERIFIED, Payment.verified_at >= start)) or 0
        rejected_today = self.db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id == self.org.id, Payment.status == PaymentStatus.REJECTED, Payment.rejected_at >= start)) or 0
        amount_today = self.db.scalar(select(func.coalesce(func.sum(Payment.verified_amount_paise), 0)).where(Payment.organization_id == self.org.id, Payment.status == PaymentStatus.VERIFIED, Payment.verified_at >= start)) or 0
        return PaymentStats(awaiting_payment=count(PaymentStatus.AWAITING_PAYMENT, PaymentStatus.INITIATED), submitted=count(PaymentStatus.SUBMITTED),
                            under_review=count(PaymentStatus.UNDER_REVIEW), verified_today=int(verified_today), rejected_today=int(rejected_today),
                            pending_amount_paise=int(pending), verified_amount_today_paise=int(amount_today))

    # --------------------------------------------------------- screenshot
    def open_screenshot(self, payment: Payment, submission_id: str):
        sub = self.db.scalar(select(PaymentSubmission).where(PaymentSubmission.public_id == submission_id, PaymentSubmission.payment_id == payment.id))
        if sub is None or not sub.screenshot_path:
            raise NotFoundError("Screenshot not found.")
        record_audit(self.db, action="payment.screenshot_viewed", actor=self.actor, organization_id=self.org.id, entity_type="payment", entity_id=payment.reference, meta=self.meta)
        return sub, get_storage().open(sub.screenshot_path)
