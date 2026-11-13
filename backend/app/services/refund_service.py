"""Refunds of verified payments.

REQUESTED ──approve──▶ APPROVED ──staff records the refund they sent (reference / proof)──▶ PROCESSED
    │                      │
    └──reject / cancel─────┴──▶ REJECTED / CANCELLED

This system never moves money. ``process`` records a refund that staff already sent from the organization's
own bank or UPI app and requires the refund UTR/bank reference (or a cash note) plus an explicit
"money sent" confirmation. Until then the customer sees "refund requested" or "refund approved", never "refunded".
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AppointmentStatus, PaymentMethod, PaymentStatus, RefundStatus
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.ids import new_reference
from app.core.storage import get_storage, validate_upload
from app.core.time import utcnow
from app.models import (
    Appointment,
    AppointmentCancellation,
    Customer,
    Organization,
    Payment,
    PaymentRefund,
    User,
)
from app.schemas.refund import (
    RefundCreate,
    RefundProcess,
    RefundRead,
    RefundReject,
    RefundStats,
    RefundSummary,
)
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService

ACTIVE = (RefundStatus.REQUESTED, RefundStatus.APPROVED)
COUNTED = (RefundStatus.REQUESTED, RefundStatus.APPROVED, RefundStatus.PROCESSED)
REFUNDABLE_PAYMENT_STATUSES = (PaymentStatus.VERIFIED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED)
PROOF_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


class RefundService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    def _payments(self):
        from app.services.payment_service import PaymentService

        return PaymentService(self.db, self.org, self.actor, self.meta)

    def _rules(self) -> dict:
        return OrganizationService(self.db).get_settings(self.org, "cancellation")["cancellation"]

    def _audit(self, refund: PaymentRefund, action: str, before: str | None, after: str, details: dict | None = None, purpose: str | None = None) -> None:
        record_audit(self.db, action=f"refund.{action}", actor=self.actor, organization_id=self.org.id, entity_type="refund", entity_id=refund.reference,
                     before={"status": before} if before else None, after={"status": after, **(details or {})}, purpose=purpose, meta=self.meta)

    # ---------------------------------------------------------------- reads
    def get(self, public_id: str) -> PaymentRefund:
        r = self.db.scalar(select(PaymentRefund).where(PaymentRefund.public_id == public_id, PaymentRefund.organization_id == self.org.id))
        if r is None:
            raise NotFoundError("Refund not found.")
        return r

    def for_payment(self, payment: Payment) -> list[PaymentRefund]:
        return list(self.db.scalars(select(PaymentRefund).where(PaymentRefund.payment_id == payment.id).order_by(PaymentRefund.id)).all())

    def _sum(self, payment: Payment, statuses) -> int:
        return int(self.db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(
            PaymentRefund.payment_id == payment.id, PaymentRefund.status.in_(statuses))) or 0)

    def refundable(self, payment: Payment) -> int:
        if payment.status not in REFUNDABLE_PAYMENT_STATUSES or payment.method == PaymentMethod.FREE:
            return 0
        return max(0, (payment.verified_amount_paise or 0) - self._sum(payment, COUNTED))

    def suggestion(self, payment: Payment) -> tuple[int, str | None]:
        refundable = self.refundable(payment)
        if refundable <= 0:
            return 0, None
        appt = self.db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        if appt is not None and appt.status == AppointmentStatus.CANCELLED:
            c = self.db.scalar(select(AppointmentCancellation).where(AppointmentCancellation.appointment_id == appt.id))
            if c is not None:
                already = int(self.db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(
                    PaymentRefund.appointment_id == appt.id, PaymentRefund.status.in_(COUNTED))) or 0)
                eligible = max(0, c.refund_eligible_paise - already)
                if eligible <= 0:
                    return 0, "Cancelled after the free-cancellation window; the policy gives no refund. You can still refund at your discretion."
                return min(eligible, refundable), "Eligible under the cancellation policy."
        return refundable, "Full verified amount not yet refunded."

    def summary(self, payment: Payment) -> RefundSummary:
        amount, why = self.suggestion(payment)
        return RefundSummary(payment_id=payment.public_id, verified_amount_paise=payment.verified_amount_paise or 0, refunded_paise=self._sum(payment, (RefundStatus.PROCESSED,)),
                             pending_paise=self._sum(payment, ACTIVE), refundable_paise=self.refundable(payment), suggested_paise=amount, suggestion_reason=why,
                             refunds=[self.to_read(r) for r in self.for_payment(payment)])

    # ------------------------------------------------------------- lifecycle
    def request(self, payload: RefundCreate, *, system: bool = False) -> PaymentRefund:
        payment = self._payments().get(payload.payment_id)
        return self._request(payment, payload.amount_paise, payload.reason, destination=payload.destination, method=payload.refund_method, system=system)

    def _request(self, payment: Payment, amount: int | None, reason: str, *, destination: str | None = None, method: str | None = None, system: bool = False) -> PaymentRefund:
        if payment.status not in REFUNDABLE_PAYMENT_STATUSES:
            raise ConflictError("Only verified payments can be refunded. Unverified submissions should be rejected instead.", code="payment_not_verified")
        refundable = self.refundable(payment)
        if refundable <= 0:
            raise ConflictError("Nothing left to refund on this payment.", code="nothing_refundable")
        amount = amount or refundable
        if amount > refundable:
            raise ValidationFailed(f"At most {refundable / 100:.2f} can be refunded on this payment.", code="refund_exceeds_paid")
        now = utcnow()
        sub_vpa = None
        if destination is None and payment.method == PaymentMethod.UPI_QR:
            from app.models import PaymentSubmission

            sub_vpa = self.db.scalar(select(PaymentSubmission.payer_upi_id).where(PaymentSubmission.payment_id == payment.id, PaymentSubmission.is_superseded.is_(False)).order_by(PaymentSubmission.id.desc()))
            if not sub_vpa:  # fall back to the payer UPI ID printed on the matched bank statement line
                from app.models import BankTransaction

                sub_vpa = self.db.scalar(select(BankTransaction.payer_vpa).where(BankTransaction.matched_payment_id == payment.id, BankTransaction.match_status == "matched"))
        refund = PaymentRefund(
            organization_id=self.org.id, payment_id=payment.id, appointment_id=payment.appointment_id, reference=new_reference("RFD", self.org.code),
            amount_paise=amount, status=RefundStatus.REQUESTED, reason=reason.strip(), destination=(destination or sub_vpa or "").strip()[:255] or None,
            refund_method=method or ("cash" if payment.method == PaymentMethod.CASH else ("upi" if payment.method == PaymentMethod.UPI_QR else "bank_transfer")),
            requested_by_user_id=None if system else (self.actor.id if self.actor else None), requested_at=now,
        )
        self.db.add(refund)
        self.db.flush()
        self._audit(refund, "requested", None, RefundStatus.REQUESTED, {"amount_paise": amount, "payment": payment.reference, "by": "system" if system else "staff"}, purpose=reason)
        self._sync_payment(payment, "refund_requested", reason=f"{refund.reference}: {reason}", details={"refund": refund.reference, "amount_paise": amount})
        return refund

    def auto_request_for_cancellation(self, appt: Appointment, eligible_paise: int, reason: str | None) -> list[PaymentRefund]:
        """Open refund *requests* (not refunds) for what the cancellation policy says is refundable."""
        if eligible_paise <= 0 or not self._rules().get("auto_request_refund", True):
            return []
        out = []
        remaining = eligible_paise
        payments = self.db.scalars(select(Payment).where(Payment.appointment_id == appt.id, Payment.status.in_(REFUNDABLE_PAYMENT_STATUSES)).order_by(Payment.id)).all()
        for p in payments:
            amount = min(remaining, self.refundable(p))
            if amount <= 0:
                continue
            out.append(self._request(p, amount, f"Appointment {appt.reference} cancelled" + (f": {reason}" if reason else ""), system=True))
            remaining -= amount
            if remaining <= 0:
                break
        return out

    def _must_be(self, refund: PaymentRefund, *statuses: str, verb: str) -> None:
        if refund.status not in statuses:
            raise ConflictError(f"A {refund.status} refund cannot be {verb}.", code="invalid_transition")

    def approve(self, refund: PaymentRefund, notes: str | None = None) -> PaymentRefund:
        self._must_be(refund, RefundStatus.REQUESTED, verb="approved")
        if self._rules().get("refund_requires_second_approver") and self.actor and refund.requested_by_user_id == self.actor.id:
            raise PermissionDenied("Another staff member must approve a refund you requested.", code="second_approver_required")
        refund.status = RefundStatus.APPROVED
        refund.approved_by_user_id = self.actor.id if self.actor else None
        refund.approved_at = utcnow()
        if notes:
            refund.notes = self._append_note(refund.notes, notes)
        self._audit(refund, "approved", RefundStatus.REQUESTED, RefundStatus.APPROVED, purpose=notes)
        self._payments()._log(self._payment(refund), "refund_approved", self._payment(refund).status, self._payment(refund).status, reason=notes, details={"refund": refund.reference})
        return refund

    def reject(self, refund: PaymentRefund, payload: RefundReject) -> PaymentRefund:
        self._must_be(refund, RefundStatus.REQUESTED, RefundStatus.APPROVED, verb="rejected")
        before = refund.status
        refund.status = RefundStatus.REJECTED
        refund.rejection_reason = payload.reason.strip()
        refund.rejected_at = utcnow()
        self._audit(refund, "rejected", before, RefundStatus.REJECTED, purpose=payload.reason)
        self._sync_payment(self._payment(refund), "refund_rejected", reason=f"{refund.reference}: {payload.reason}", details={"refund": refund.reference})
        return refund

    def cancel(self, refund: PaymentRefund, reason: str | None = None) -> PaymentRefund:
        self._must_be(refund, RefundStatus.REQUESTED, RefundStatus.APPROVED, verb="withdrawn")
        before = refund.status
        refund.status = RefundStatus.CANCELLED
        if reason:
            refund.notes = self._append_note(refund.notes, f"Withdrawn: {reason}")
        self._audit(refund, "cancelled", before, RefundStatus.CANCELLED, purpose=reason)
        self._sync_payment(self._payment(refund), "refund_withdrawn", reason=reason, details={"refund": refund.reference})
        return refund

    def process(self, refund: PaymentRefund, payload: RefundProcess) -> PaymentRefund:
        self._must_be(refund, RefundStatus.APPROVED, verb="marked as processed (approve it first)")
        if not payload.money_sent_confirmed:
            raise ValidationFailed("Confirm that the refund was sent from your bank or UPI app before marking it processed.", code="refund_not_confirmed")
        ref = (payload.refund_reference or "").strip()
        if ref:
            dup = self.db.scalar(select(PaymentRefund).where(PaymentRefund.organization_id == self.org.id, PaymentRefund.id != refund.id,
                                                             func.upper(PaymentRefund.refund_reference) == ref.upper()))
            if dup is not None:
                raise ConflictError(f"This reference is already recorded on refund {dup.reference}.", code="duplicate_refund_reference")
        now = utcnow()
        processed_at = payload.processed_at or now
        if processed_at > now:
            raise ValidationFailed("The refund date cannot be in the future.", code="invalid_date")
        refund.status = RefundStatus.PROCESSED
        refund.refund_method = payload.refund_method
        refund.refund_reference = ref or None
        if payload.destination:
            refund.destination = payload.destination.strip()[:255]
        refund.processed_at = processed_at
        refund.processed_by_user_id = self.actor.id if self.actor else None
        if payload.notes:
            refund.notes = self._append_note(refund.notes, payload.notes)
        payment = self._payment(refund)
        appt = self.db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        if appt is not None:
            appt.paid_amount_paise = max(0, (appt.paid_amount_paise or 0) - refund.amount_paise)
        self._audit(refund, "processed", RefundStatus.APPROVED, RefundStatus.PROCESSED,
                    {"amount_paise": refund.amount_paise, "method": refund.refund_method, "refund_reference": refund.refund_reference})
        self._sync_payment(payment, "refund_processed", reason=payload.notes,
                           details={"refund": refund.reference, "amount_paise": refund.amount_paise, "refund_reference": refund.refund_reference})
        return refund

    def attach_proof(self, refund: PaymentRefund, data: bytes) -> PaymentRefund:
        if refund.status not in (RefundStatus.APPROVED, RefundStatus.PROCESSED):
            raise ConflictError("Attach proof to an approved or processed refund.", code="invalid_transition")
        mime = validate_upload(data, allowed=PROOF_TYPES, max_mb=get_settings().max_upload_size_mb)
        stored = get_storage().save(scope=f"org/{self.org.public_id}/refunds/{refund.public_id}", visibility="private", data=data, mime_type=mime)
        refund.refund_proof_path = stored.key
        self._audit(refund, "proof_attached", refund.status, refund.status, {"mime": mime})
        return refund

    def open_proof(self, refund: PaymentRefund):
        if not refund.refund_proof_path:
            raise NotFoundError("No proof attached.")
        record_audit(self.db, action="refund.proof_viewed", actor=self.actor, organization_id=self.org.id, entity_type="refund", entity_id=refund.reference, meta=self.meta)
        key = refund.refund_proof_path
        mime = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "pdf": "application/pdf"}.get(key.rsplit(".", 1)[-1], "application/octet-stream")
        return mime, get_storage().open(key)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _append_note(existing: str | None, note: str) -> str:
        note = note.strip()
        return f"{existing}\n{note}" if existing else note

    def _payment(self, refund: PaymentRefund) -> Payment:
        return self.db.get(Payment, refund.payment_id)

    def _sync_payment(self, payment: Payment, action: str, *, reason: str | None = None, details: dict | None = None) -> None:
        """Payment status mirrors its refunds: any open refund → refund_requested; fully refunded → refund_processed."""
        self.db.flush()
        if self._sum(payment, ACTIVE) > 0:
            target = PaymentStatus.REFUND_REQUESTED
        elif self._sum(payment, (RefundStatus.PROCESSED,)) >= (payment.verified_amount_paise or 0) > 0:
            target = PaymentStatus.REFUND_PROCESSED
        else:
            target = PaymentStatus.VERIFIED
        before = payment.status
        payment.status = target
        self._payments()._log(payment, action, before, target, reason=reason, details=details)

    # ----------------------------------------------------------------- output
    def to_read(self, r: PaymentRefund) -> RefundRead:
        p = self.db.get(Payment, r.payment_id)
        appt = self.db.get(Appointment, r.appointment_id) if r.appointment_id else None
        cust = self.db.get(Customer, p.customer_id) if p and p.customer_id else None
        ids = {i for i in (r.requested_by_user_id, r.approved_by_user_id, r.processed_by_user_id) if i}
        names = dict(self.db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}
        return RefundRead(
            id=r.public_id, reference=r.reference, status=r.status, amount_paise=r.amount_paise, reason=r.reason, rejection_reason=r.rejection_reason,
            refund_method=r.refund_method, refund_reference=r.refund_reference, destination=r.destination, has_proof=bool(r.refund_proof_path), notes=r.notes,
            payment_id=p.public_id, payment_reference=p.reference, payment_method=p.method, payment_verified_amount_paise=p.verified_amount_paise,
            appointment_id=appt.public_id if appt else None, appointment_reference=appt.reference if appt else None, appointment_status=appt.status if appt else None,
            customer_id=cust.public_id if cust else None, customer_name=cust.full_name if cust else None, customer_mobile=cust.mobile if cust else None,
            requested_by_name=names.get(r.requested_by_user_id) or (None if r.requested_by_user_id else "System (cancellation)"),
            approved_by_name=names.get(r.approved_by_user_id), processed_by_name=names.get(r.processed_by_user_id),
            requested_at=r.requested_at, approved_at=r.approved_at, processed_at=r.processed_at, rejected_at=r.rejected_at, created_at=r.created_at,
        )

    def list(self, *, status: str | None, search: str | None, from_at: datetime | None, to_at: datetime | None, page: int, page_size: int) -> tuple[list[PaymentRefund], int]:
        stmt = select(PaymentRefund).where(PaymentRefund.organization_id == self.org.id)
        if status:
            stmt = stmt.where(PaymentRefund.status.in_(status.split(",")))
        if from_at:
            stmt = stmt.where(PaymentRefund.created_at >= from_at)
        if to_at:
            stmt = stmt.where(PaymentRefund.created_at <= to_at)
        if search:
            like = f"%{search.strip().upper()}%"
            pay_ids = select(Payment.id).where(Payment.organization_id == self.org.id, func.upper(Payment.reference).like(like))
            cust_pay = select(Payment.id).join(Customer, Customer.id == Payment.customer_id).where(
                Payment.organization_id == self.org.id, (func.upper(Customer.full_name).like(like)) | (Customer.mobile.like(f"%{search.strip()}%")))
            stmt = stmt.where(func.upper(PaymentRefund.reference).like(like) | func.upper(func.coalesce(PaymentRefund.refund_reference, "")).like(like)
                              | PaymentRefund.payment_id.in_(pay_ids) | PaymentRefund.payment_id.in_(cust_pay))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(PaymentRefund.created_at.desc(), PaymentRefund.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    def stats(self) -> RefundStats:
        month = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        base = select(func.count()).select_from(PaymentRefund).where(PaymentRefund.organization_id == self.org.id)
        requested = self.db.scalar(base.where(PaymentRefund.status == RefundStatus.REQUESTED)) or 0
        approved = self.db.scalar(base.where(PaymentRefund.status == RefundStatus.APPROVED)) or 0
        processed = self.db.scalar(base.where(PaymentRefund.status == RefundStatus.PROCESSED, PaymentRefund.processed_at >= month)) or 0
        pending_amt = self.db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(PaymentRefund.organization_id == self.org.id, PaymentRefund.status.in_(ACTIVE))) or 0
        processed_amt = self.db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_paise), 0)).where(
            PaymentRefund.organization_id == self.org.id, PaymentRefund.status == RefundStatus.PROCESSED, PaymentRefund.processed_at >= month)) or 0
        return RefundStats(requested=int(requested), approved=int(approved), processed_this_month=int(processed), pending_amount_paise=int(pending_amt),
                           processed_amount_this_month_paise=int(processed_amt))
