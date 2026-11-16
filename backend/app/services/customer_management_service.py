"""Customer records: profiles, search and segments, dependents, encrypted notes, private documents, export."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus, PaymentStatus, RefundStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.logging import get_logger
from app.core.storage import get_storage, validate_upload
from app.core.time import utcnow
from app.models import (
    Appointment,
    BookingFormResponse,
    Branch,
    Customer,
    CustomerDependent,
    CustomerDocument,
    CustomerNote,
    Notification,
    Organization,
    Payment,
    PaymentRefund,
    Professional,
    User,
)
from app.schemas.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerStats,
    CustomerUpdate,
    DependentCreate,
    DependentRead,
    DependentUpdate,
    DocumentRead,
    NoteCreate,
    NoteRead,
    SelfProfileUpdate,
)
from app.security.crypto import decrypt_text, encrypt_text
from app.security.identifiers import normalize_email, normalize_mobile
from app.services.audit_service import RequestMeta, record_audit
from app.services.catalog_service import ids_to_public
from app.services.organization_service import OrganizationService
from app.services.privacy_service import is_masked_echo, mask_email, mask_mobile, view_email, view_mobile

log = get_logger(__name__)

DOCUMENT_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}


class CustomerManagementService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # -------------------------------------------------------------- audit
    def _audit(self, action: str, entity_type: str, entity_id, before=None, after=None, purpose=None) -> None:
        record_audit(self.db, action=action, actor=self.actor, organization_id=self.org.id, entity_type=entity_type, entity_id=entity_id,
                     before=before, after=after, purpose=purpose, meta=self.meta)

    # ------------------------------------------------------------ lookups
    # Doctors and professionals who only see their own calendar also see only their own patients (clinic privacy
    # setting "doctors_see_own_patients_only"): set by the customers API, None for everyone else.
    care_professional_id: int | None = None

    def _care_filter(self, stmt):
        if self.care_professional_id is None:
            return stmt
        mine = select(Appointment.customer_id).where(Appointment.organization_id == self.org.id, Appointment.professional_id == self.care_professional_id)
        return stmt.where(Customer.id.in_(mine))

    def get(self, public_id: str) -> Customer:
        stmt = select(Customer).where(Customer.public_id == public_id, Customer.organization_id == self.org.id, Customer.deleted_at.is_(None))
        c = self.db.scalar(self._care_filter(stmt))
        if c is None:
            raise NotFoundError("Customer not found.")  # also when it exists but is not one of this doctor's patients
        return c

    def list(self, *, search: str | None, tag: str | None, segment: str | None, is_guest: bool | None, page: int, page_size: int) -> tuple[list[Customer], int]:
        stmt = self._care_filter(select(Customer).where(Customer.organization_id == self.org.id, Customer.deleted_at.is_(None)))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(or_(func.lower(Customer.full_name).like(like), Customer.mobile.like(like), func.lower(Customer.email).like(like), func.lower(Customer.customer_code).like(like)))
        if tag:
            stmt = stmt.where(func.lower(func.cast(Customer.tags, type_=__import__("sqlalchemy").String)).like(f'%"{tag.lower()}"%'))
        if is_guest is not None:
            stmt = stmt.where(Customer.is_guest.is_(is_guest))
        now = utcnow()
        if segment == "new_30d":
            stmt = stmt.where(Customer.created_at >= now - timedelta(days=30))
        elif segment == "upcoming":
            sub = select(Appointment.customer_id).where(Appointment.organization_id == self.org.id, Appointment.start_at >= now, Appointment.status.in_(["confirmed", "pending_payment", "pending_verification"]))
            stmt = stmt.where(Customer.id.in_(sub))
        elif segment == "inactive_90d":
            stmt = stmt.where(or_(Customer.last_visit_at.is_(None), Customer.last_visit_at < now - timedelta(days=90)))
        elif segment == "returning":
            sub = select(Appointment.customer_id).where(Appointment.organization_id == self.org.id, Appointment.status == AppointmentStatus.COMPLETED).group_by(Appointment.customer_id).having(func.count(Appointment.id) >= 2)
            stmt = stmt.where(Customer.id.in_(sub))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(Customer.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    # ------------------------------------------------------------- create
    def _next_code(self) -> str:
        count = self.db.scalar(select(func.count()).select_from(Customer).where(Customer.organization_id == self.org.id)) or 0
        return f"{self.org.code[:4]}-{count + 1:05d}"

    def _normalise(self, data: dict) -> dict:
        if data.get("mobile"):
            data["mobile"] = normalize_mobile(data["mobile"])
        if data.get("email"):
            data["email"] = normalize_email(data["email"])
        if data.get("tags") is not None:
            data["tags"] = sorted({t.strip().lower() for t in data["tags"] if t.strip()})
        return data

    def create(self, payload: CustomerCreate) -> Customer:
        data = self._normalise(payload.model_dump())
        if not data.get("mobile") and not data.get("email"):
            raise ValidationFailed("A mobile number or email is required.", code="contact_required")
        if data.get("mobile") and self.db.scalar(select(Customer.id).where(Customer.organization_id == self.org.id, Customer.mobile == data["mobile"], Customer.deleted_at.is_(None))):
            raise ConflictError("A customer with this mobile number already exists.", code="mobile_taken")
        customer = Customer(organization_id=self.org.id, is_guest=False, registered_at=utcnow(), source="reception", **data)
        for attempt in range(3):
            customer.customer_code = self._next_code()
            try:
                with self.db.begin_nested():
                    self.db.add(customer)
                    self.db.flush()
                break
            except IntegrityError as exc:
                if attempt == 2:
                    raise ConflictError("Could not allocate a customer code. Try again.") from exc
        self._audit("customer.created", "customer", customer.public_id, after={"name": customer.full_name})
        return customer

    def ensure_code(self, customer: Customer) -> None:
        if not customer.customer_code:
            customer.customer_code = self._next_code()
            self.db.flush()

    def update(self, customer: Customer, payload: CustomerUpdate) -> Customer:
        raw = payload.model_dump(exclude_unset=True)
        for field in ("mobile", "email"):  # a masked value sent back unchanged keeps the real one
            if field in raw and is_masked_echo(raw[field], getattr(customer, field)):
                raw.pop(field)
        data = self._normalise(raw)
        if "saved_professional_ids" in data and data["saved_professional_ids"] is not None:
            data["saved_professional_ids"] = self._validate_public_ids(Professional, data["saved_professional_ids"])
        if "saved_branch_ids" in data and data["saved_branch_ids"] is not None:
            data["saved_branch_ids"] = self._validate_public_ids(Branch, data["saved_branch_ids"])
        if data.get("mobile") and self.db.scalar(select(Customer.id).where(Customer.organization_id == self.org.id, Customer.mobile == data["mobile"], Customer.id != customer.id, Customer.deleted_at.is_(None))):
            raise ConflictError("Another customer already uses this mobile number.", code="mobile_taken")
        before = {k: getattr(customer, k) for k in data if k not in ("consent", "communication_preferences", "address")}
        for k, v in data.items():
            setattr(customer, k, v)
        if customer.is_guest and (customer.user_id or self.actor):
            customer.is_guest = False
        self.db.flush()
        after = {k: v for k, v in data.items() if k in before}
        for d in (before, after):  # the audit log needs to show that contact details changed, not what they are
            for k, fn in (("mobile", mask_mobile), ("email", mask_email)):
                if d.get(k):
                    d[k] = fn(d[k])
        self._audit("customer.updated", "customer", customer.public_id, before=before, after=after)
        return customer

    def update_self(self, customer: Customer, payload: SelfProfileUpdate) -> Customer:
        return self.update(customer, CustomerUpdate(**payload.model_dump(exclude_unset=True)))

    def _validate_public_ids(self, model, ids: list[str]) -> list[str]:
        rows = self.db.scalars(select(model.public_id).where(model.public_id.in_(ids), model.organization_id == self.org.id)).all()
        unknown = set(ids) - set(rows)
        if unknown:
            raise ValidationFailed(f"Unknown ids: {', '.join(sorted(unknown))}")
        return list(dict.fromkeys(ids))

    def delete(self, customer: Customer) -> None:
        upcoming = self.db.scalar(select(func.count()).select_from(Appointment).where(Appointment.customer_id == customer.id, Appointment.status.in_(["confirmed", "pending_payment", "pending_verification", "checked_in"])))
        if upcoming:
            raise ConflictError("Cancel the customer's upcoming appointments before deleting.", code="has_upcoming")
        customer.deleted_at = utcnow()
        self.db.flush()
        self._audit("customer.deleted", "customer", customer.public_id)

    def anonymize(self, customer: Customer, reason: str) -> None:
        """Erase a customer's personal and clinical data at their request.

        Removed: name, contact details, date of birth, address and other profile fields; family members; clinical notes;
        uploaded documents (files deleted from storage); booking-form answers; free-text appointment notes; the copies
        of their details held in notification records; and the link to their login account.
        Kept, because the clinic must be able to account for money: appointments (date, service, amount, status),
        payments, UTRs, verification logs and refunds - now attached to an anonymous record. The audit log records
        that an erasure happened, by whom and why, but not the erased values."""
        if self.db.scalar(select(func.count()).select_from(Appointment).where(Appointment.customer_id == customer.id, Appointment.status.in_(["confirmed", "pending_payment", "pending_verification", "checked_in"]))):
            raise ConflictError("Cancel the customer's upcoming appointments before erasing their data.", code="has_upcoming")
        open_money = self.db.scalar(
            select(func.count()).select_from(Payment).where(Payment.customer_id == customer.id, Payment.status.in_(
                [PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW, PaymentStatus.REFUND_REQUESTED]))
        ) or self.db.scalar(
            select(func.count()).select_from(PaymentRefund).join(Payment, Payment.id == PaymentRefund.payment_id)
            .where(Payment.customer_id == customer.id, PaymentRefund.status.in_([RefundStatus.REQUESTED, RefundStatus.APPROVED]))
        )
        if open_money:
            raise ConflictError("Finish verifying this customer's payments and refunds before erasing their data.", code="has_open_payments")

        now = utcnow()
        storage = get_storage()
        for doc in self.db.scalars(select(CustomerDocument).where(CustomerDocument.customer_id == customer.id)).all():
            try:
                storage.delete(doc.storage_path)
            except Exception as exc:  # pragma: no cover - the row is retired even if the file is already gone
                log.warning("customer.erase_file_failed", document_id=doc.public_id, error=type(exc).__name__)
            doc.title, doc.deleted_at = "Erased", doc.deleted_at or now
        for note in self.db.scalars(select(CustomerNote).where(CustomerNote.customer_id == customer.id)).all():
            self.db.delete(note)
        for dep in self.db.scalars(select(CustomerDependent).where(CustomerDependent.customer_id == customer.id)).all():
            dep.full_name, dep.mobile, dep.notes, dep.date_of_birth, dep.gender = "Erased", None, None, None, None
            dep.deleted_at = dep.deleted_at or now
        for resp in self.db.scalars(select(BookingFormResponse).where(BookingFormResponse.customer_id == customer.id)).all():
            resp.answers, resp.attachments = {}, None
        for appt in self.db.scalars(select(Appointment).where(Appointment.customer_id == customer.id)).all():
            appt.customer_notes = None
        for n in self.db.scalars(select(Notification).where(Notification.recipient_customer_id == customer.id)).all():
            n.recipient_address, n.subject, n.body, n.payload = None, None, "[erased]", None

        customer.full_name = "Erased customer"
        customer.mobile = customer.email = customer.date_of_birth = customer.gender = customer.address = None
        customer.profile_photo_url = customer.blood_group = customer.communication_preferences = customer.consent = None
        customer.tags = customer.saved_professional_ids = customer.saved_branch_ids = customer.metadata_ = None
        customer.user_id = None
        customer.deleted_at = now
        self.db.flush()
        self._audit("customer.anonymized", "customer", customer.public_id, purpose=reason)

    # -------------------------------------------------------------- stats
    def stats(self, customer: Customer) -> CustomerStats:
        rows = self.db.execute(select(Appointment.status, Appointment.start_at, Appointment.paid_amount_paise).where(Appointment.customer_id == customer.id)).all()
        now = utcnow()
        s = CustomerStats(total_appointments=len(rows))
        for status, start, paid in rows:
            if status == AppointmentStatus.COMPLETED:
                s.completed_appointments += 1
                if s.last_visit_at is None or start > s.last_visit_at:
                    s.last_visit_at = start
            elif status == AppointmentStatus.CANCELLED:
                s.cancelled_appointments += 1
            elif status == AppointmentStatus.NO_SHOW:
                s.no_shows += 1
            if status in ("confirmed", "pending_payment", "pending_verification") and start >= now:
                s.upcoming_appointments += 1
                if s.next_appointment_at is None or start < s.next_appointment_at:
                    s.next_appointment_at = start
            s.total_paid_paise += paid or 0
        return s

    def prepare_reads(self, rows: list[Customer]) -> list[Customer]:
        """One grouped count of family members and one user lookup for the whole page."""
        ids = [c.id for c in rows]
        self._dependent_counts = dict(self.db.execute(
            select(CustomerDependent.customer_id, func.count()).where(CustomerDependent.customer_id.in_(ids), CustomerDependent.deleted_at.is_(None))
            .group_by(CustomerDependent.customer_id)).all()) if ids else {}
        self._batched = set(ids)
        self._user_public = ids_to_public(self.db, User, {c.user_id for c in rows if c.user_id})
        return rows

    def to_read(self, customer: Customer, *, with_stats: bool = False) -> CustomerRead:
        if customer.id in getattr(self, "_batched", ()):
            dependents = self._dependent_counts.get(customer.id, 0)
            user_pub = self._user_public.get(customer.user_id) if customer.user_id else None
        else:
            dependents = self.db.scalar(select(func.count()).select_from(CustomerDependent).where(CustomerDependent.customer_id == customer.id, CustomerDependent.deleted_at.is_(None))) or 0
            user_pub = ids_to_public(self.db, User, {customer.user_id}).get(customer.user_id) if customer.user_id else None
        return CustomerRead(
            id=customer.public_id, customer_code=customer.customer_code, user_id=user_pub, full_name=customer.full_name, mobile=view_mobile(self.db, customer.mobile), email=view_email(self.db, customer.email),
            date_of_birth=customer.date_of_birth, gender=customer.gender, address=customer.address, profile_photo_url=customer.profile_photo_url, blood_group=customer.blood_group,
            communication_preferences=customer.communication_preferences, consent=customer.consent, tags=customer.tags or [], is_guest=customer.is_guest, source=customer.source,
            registered_at=customer.registered_at, last_visit_at=customer.last_visit_at, saved_professional_ids=customer.saved_professional_ids or [], saved_branch_ids=customer.saved_branch_ids or [],
            created_at=customer.created_at, stats=self.stats(customer) if with_stats else None, dependents_count=int(dependents),
        )

    # --------------------------------------------------------- dependents
    def list_dependents(self, customer: Customer) -> list[CustomerDependent]:
        return list(self.db.scalars(select(CustomerDependent).where(CustomerDependent.customer_id == customer.id, CustomerDependent.deleted_at.is_(None)).order_by(CustomerDependent.id)).all())

    def add_dependent(self, customer: Customer, payload: DependentCreate) -> CustomerDependent:
        data = payload.model_dump()
        if data.get("mobile"):
            data["mobile"] = normalize_mobile(data["mobile"])
        row = CustomerDependent(organization_id=self.org.id, customer_id=customer.id, **data)
        self.db.add(row)
        self.db.flush()
        self._audit("customer.dependent_added", "customer", customer.public_id, after={"dependent": row.full_name})
        return row

    def update_dependent(self, customer: Customer, dependent_id: str, payload: DependentUpdate) -> CustomerDependent:
        row = self._dependent(customer, dependent_id)
        data = payload.model_dump(exclude_unset=True)
        if "mobile" in data and is_masked_echo(data["mobile"], row.mobile):
            data.pop("mobile")
        if data.get("mobile"):
            data["mobile"] = normalize_mobile(data["mobile"])
        for k, v in data.items():
            setattr(row, k, v)
        self.db.flush()
        return row

    def delete_dependent(self, customer: Customer, dependent_id: str) -> None:
        row = self._dependent(customer, dependent_id)
        row.deleted_at = utcnow()
        self.db.flush()

    def _dependent(self, customer: Customer, dependent_id: str) -> CustomerDependent:
        row = self.db.scalar(select(CustomerDependent).where(CustomerDependent.public_id == dependent_id, CustomerDependent.customer_id == customer.id, CustomerDependent.deleted_at.is_(None)))
        if row is None:
            raise NotFoundError("Family member not found.")
        return row

    def dependent_read(self, row: CustomerDependent, customer: Customer) -> DependentRead:
        return DependentRead(id=row.public_id, customer_id=customer.public_id, full_name=row.full_name, relationship_label=row.relationship_label, date_of_birth=row.date_of_birth,
                             gender=row.gender, mobile=view_mobile(self.db, row.mobile), notes=row.notes, created_at=row.created_at)

    # -------------------------------------------------------------- notes
    def list_notes(self, customer: Customer, *, purpose: str | None = None) -> list[NoteRead]:
        rows = self.db.scalars(select(CustomerNote).where(CustomerNote.customer_id == customer.id).order_by(CustomerNote.id.desc())).all()
        if rows:
            self._audit("customer.notes_viewed", "customer", customer.public_id, purpose=purpose or "notes list")
        authors = dict(self.db.execute(select(User.id, User.full_name).where(User.id.in_({r.author_user_id for r in rows if r.author_user_id}))).all()) if rows else {}
        appts = ids_to_public(self.db, Appointment, {r.appointment_id for r in rows if r.appointment_id})
        return [
            NoteRead(id=r.public_id, note_type=r.note_type, body=decrypt_text(r.body_encrypted), is_sensitive=r.is_sensitive, appointment_id=appts.get(r.appointment_id) if r.appointment_id else None,
                     author_name=authors.get(r.author_user_id), created_at=r.created_at, updated_at=r.updated_at)
            for r in rows
        ]

    def add_note(self, customer: Customer, payload: NoteCreate) -> CustomerNote:
        appointment_id = None
        if payload.appointment_id:
            appt = self.db.scalar(select(Appointment).where(Appointment.public_id == payload.appointment_id, Appointment.customer_id == customer.id))
            if appt is None:
                raise NotFoundError("Appointment not found for this customer.")
            appointment_id = appt.id
        row = CustomerNote(organization_id=self.org.id, customer_id=customer.id, appointment_id=appointment_id, author_user_id=self.actor.id if self.actor else None,
                           note_type=payload.note_type, body_encrypted=encrypt_text(payload.body), is_sensitive=payload.is_sensitive)
        self.db.add(row)
        self.db.flush()
        self._audit("customer.note_added", "customer", customer.public_id, after={"note_type": payload.note_type, "note_id": row.public_id})
        return row

    def delete_note(self, customer: Customer, note_id: str) -> None:
        row = self.db.scalar(select(CustomerNote).where(CustomerNote.public_id == note_id, CustomerNote.customer_id == customer.id))
        if row is None:
            raise NotFoundError("Note not found.")
        self.db.delete(row)
        self.db.flush()
        self._audit("customer.note_deleted", "customer", customer.public_id, before={"note_id": note_id})

    # ---------------------------------------------------------- documents
    def list_documents(self, customer: Customer) -> list[CustomerDocument]:
        return list(self.db.scalars(select(CustomerDocument).where(CustomerDocument.customer_id == customer.id, CustomerDocument.deleted_at.is_(None)).order_by(CustomerDocument.id.desc())).all())

    def add_document(self, customer: Customer, *, data: bytes, title: str, document_type: str, appointment_id: str | None, max_mb: int) -> CustomerDocument:
        mime = validate_upload(data, allowed=DOCUMENT_TYPES, max_mb=max_mb)
        stored = get_storage().save(scope=f"org/{self.org.public_id}/customers/{customer.public_id}", visibility="private", data=data, mime_type=mime)
        appt_id = None
        if appointment_id:
            appt = self.db.scalar(select(Appointment).where(Appointment.public_id == appointment_id, Appointment.customer_id == customer.id))
            if appt is None:
                raise NotFoundError("Appointment not found for this customer.")
            appt_id = appt.id
        retention_days = int((OrganizationService(self.db).get_settings(self.org, "privacy")["privacy"]).get("document_retention_days") or 0)
        row = CustomerDocument(
            organization_id=self.org.id, customer_id=customer.id, appointment_id=appt_id, uploaded_by_user_id=self.actor.id if self.actor else None,
            title=title.strip()[:160] or "Document", document_type=document_type, storage_path=stored.key, mime_type=stored.mime_type, size_bytes=stored.size_bytes,
            checksum_sha256=stored.sha256, retention_until=(date.today() + timedelta(days=retention_days)) if retention_days else None,
        )
        self.db.add(row)
        self.db.flush()
        self._audit("customer.document_uploaded", "customer", customer.public_id, after={"document_id": row.public_id, "type": document_type})
        return row

    def get_document(self, customer: Customer, document_id: str) -> CustomerDocument:
        row = self.db.scalar(select(CustomerDocument).where(CustomerDocument.public_id == document_id, CustomerDocument.customer_id == customer.id, CustomerDocument.deleted_at.is_(None)))
        if row is None:
            raise NotFoundError("Document not found.")
        return row

    def open_document(self, customer: Customer, document_id: str, *, purpose: str | None = None):
        row = self.get_document(customer, document_id)
        self._audit("customer.document_downloaded", "customer", customer.public_id, after={"document_id": row.public_id}, purpose=purpose)
        return row, get_storage().open(row.storage_path)

    def delete_document(self, customer: Customer, document_id: str) -> None:
        row = self.get_document(customer, document_id)
        row.deleted_at = utcnow()
        self.db.flush()
        self._audit("customer.document_deleted", "customer", customer.public_id, before={"document_id": row.public_id})

    def document_read(self, row: CustomerDocument) -> DocumentRead:
        uploader = self.db.get(User, row.uploaded_by_user_id) if row.uploaded_by_user_id else None
        appt = ids_to_public(self.db, Appointment, {row.appointment_id}).get(row.appointment_id) if row.appointment_id else None
        return DocumentRead(id=row.public_id, title=row.title, document_type=row.document_type, mime_type=row.mime_type, size_bytes=row.size_bytes, is_sensitive=row.is_sensitive,
                            appointment_id=appt, uploaded_by_name=uploader.full_name if uploader else None, retention_until=row.retention_until, created_at=row.created_at)

    # ------------------------------------------------------------- export
    def export_csv(self) -> str:
        rows = self.db.scalars(select(Customer).where(Customer.organization_id == self.org.id, Customer.deleted_at.is_(None)).order_by(Customer.id)).all()
        counts = dict(self.db.execute(select(Appointment.customer_id, func.count(Appointment.id)).where(Appointment.organization_id == self.org.id).group_by(Appointment.customer_id)).all())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["customer_code", "full_name", "mobile", "email", "gender", "date_of_birth", "tags", "is_guest", "registered_at", "last_visit_at", "total_appointments"])
        for c in rows:
            writer.writerow([c.customer_code or "", c.full_name, c.mobile or "", c.email or "", c.gender or "", c.date_of_birth.isoformat() if c.date_of_birth else "",
                             "|".join(c.tags or []), "yes" if c.is_guest else "no", c.registered_at.isoformat() if c.registered_at else "", c.last_visit_at.isoformat() if c.last_visit_at else "",
                             counts.get(c.id, 0)])
        self._audit("customer.exported", "customer", "all", after={"rows": len(rows)}, purpose="CSV export")
        return buf.getvalue()


def purge_expired_documents(db: Session) -> int:
    """Retention job: soft-delete documents past ``retention_until`` and remove the stored file."""
    today = date.today()
    rows = db.scalars(select(CustomerDocument).where(CustomerDocument.deleted_at.is_(None), CustomerDocument.retention_until.is_not(None), CustomerDocument.retention_until < today)).all()
    storage = get_storage()
    for row in rows:
        try:
            storage.delete(row.storage_path)
        except Exception as exc:  # pragma: no cover - best effort file removal; the row is still retired
            log.warning("customer.document_purge_file_failed", document_id=row.public_id, error=type(exc).__name__)
        row.deleted_at = utcnow()
        record_audit(db, action="customer.document_purged", actor=None, organization_id=row.organization_id, entity_type="customer_document", entity_id=row.public_id, purpose="retention policy")
    db.flush()
    return len(rows)
