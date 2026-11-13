"""Organization UPI accounts and the rule that picks which account collects a payment."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.time import utcnow
from app.models import Branch, Organization, Service, UPIAccount, User
from app.payments.upi import UPIRequest, qr_data_url
from app.schemas.payment import QRPreview, UPIAccountCreate, UPIAccountRead, UPIAccountUpdate
from app.services.audit_service import RequestMeta, record_audit
from app.services.catalog_service import ids_to_public


class UPIAccountService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    def _audit(self, action: str, account: UPIAccount, before=None, after=None) -> None:
        record_audit(self.db, action=action, actor=self.actor, organization_id=self.org.id, entity_type="upi_account", entity_id=account.public_id, before=before, after=after, meta=self.meta)

    def list(self, include_inactive: bool = True) -> list[UPIAccount]:
        stmt = select(UPIAccount).where(UPIAccount.organization_id == self.org.id, UPIAccount.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(UPIAccount.is_active.is_(True))
        return list(self.db.scalars(stmt.order_by(UPIAccount.branch_id.is_not(None), UPIAccount.sort_order, UPIAccount.display_name)).all())

    def get(self, public_id: str) -> UPIAccount:
        acct = self.db.scalar(select(UPIAccount).where(UPIAccount.public_id == public_id, UPIAccount.organization_id == self.org.id, UPIAccount.deleted_at.is_(None)))
        if acct is None:
            raise NotFoundError("UPI account not found.")
        return acct

    def _branch_id(self, public_id: str | None) -> int | None:
        if not public_id:
            return None
        b = self.db.scalar(select(Branch).where(Branch.public_id == public_id, Branch.organization_id == self.org.id, Branch.deleted_at.is_(None)))
        if b is None:
            raise NotFoundError("Branch not found.")
        return b.id

    def _assert_unique_vpa(self, upi_id: str, exclude_id: int | None = None) -> None:
        stmt = select(UPIAccount.id).where(UPIAccount.organization_id == self.org.id, UPIAccount.upi_id == upi_id, UPIAccount.deleted_at.is_(None))
        if exclude_id:
            stmt = stmt.where(UPIAccount.id != exclude_id)
        if self.db.scalar(stmt):
            raise ConflictError("This UPI ID is already added.", code="upi_id_taken")

    def _clear_other_defaults(self, acct: UPIAccount) -> None:
        """One default per scope: organization-wide (branch NULL) or per branch."""
        stmt = select(UPIAccount).where(UPIAccount.organization_id == self.org.id, UPIAccount.id != acct.id, UPIAccount.is_default.is_(True), UPIAccount.deleted_at.is_(None))
        stmt = stmt.where(UPIAccount.branch_id.is_(None)) if acct.branch_id is None else stmt.where(UPIAccount.branch_id == acct.branch_id)
        for other in self.db.scalars(stmt).all():
            other.is_default = False

    def create(self, payload: UPIAccountCreate) -> UPIAccount:
        self._assert_unique_vpa(payload.upi_id)
        acct = UPIAccount(organization_id=self.org.id, branch_id=self._branch_id(payload.branch_id), **payload.model_dump(exclude={"branch_id"}))
        scope_has_any = self.db.scalar(
            select(func.count()).select_from(UPIAccount).where(
                UPIAccount.organization_id == self.org.id, UPIAccount.deleted_at.is_(None),
                UPIAccount.branch_id.is_(None) if acct.branch_id is None else UPIAccount.branch_id == acct.branch_id,
            )
        )
        if not scope_has_any:
            acct.is_default = True
        self.db.add(acct)
        self.db.flush()
        if acct.is_default:
            self._clear_other_defaults(acct)
        self._audit("upi_account.created", acct, after={"upi_id": acct.upi_id, "branch_id": payload.branch_id, "default": acct.is_default})
        return acct

    def update(self, acct: UPIAccount, payload: UPIAccountUpdate) -> UPIAccount:
        data = payload.model_dump(exclude_unset=True, exclude={"branch_id", "clear_branch"})
        if "upi_id" in data:
            self._assert_unique_vpa(data["upi_id"], exclude_id=acct.id)
        before = {k: getattr(acct, k) for k in data}
        for k, v in data.items():
            setattr(acct, k, v)
        if payload.clear_branch:
            acct.branch_id = None
        elif payload.branch_id:
            acct.branch_id = self._branch_id(payload.branch_id)
        if not acct.use_dynamic_qr and not acct.static_qr_path:
            raise ConflictError("Upload a static QR image or enable dynamic QR.", code="qr_required")
        self.db.flush()
        if acct.is_default:
            self._clear_other_defaults(acct)
        self._audit("upi_account.updated", acct, before=before, after=data)
        return acct

    def delete(self, acct: UPIAccount) -> None:
        acct.deleted_at = utcnow()
        acct.is_active = False
        acct.is_default = False
        for svc in self.db.scalars(select(Service).where(Service.upi_account_id == acct.id)).all():
            svc.upi_account_id = None
        self.db.flush()
        self._audit("upi_account.deleted", acct)

    def assign_service(self, acct: UPIAccount | None, service_public_id: str) -> Service:
        svc = self.db.scalar(select(Service).where(Service.public_id == service_public_id, Service.organization_id == self.org.id, Service.deleted_at.is_(None)))
        if svc is None:
            raise NotFoundError("Service not found.")
        svc.upi_account_id = acct.id if acct else None
        self.db.flush()
        record_audit(self.db, action="upi_account.service_assigned", actor=self.actor, organization_id=self.org.id, entity_type="service", entity_id=svc.public_id,
                     after={"upi_account": acct.public_id if acct else None}, meta=self.meta)
        return svc

    # ----------------------------------------------------------- selection
    def select_for(self, service: Service | None, branch_id: int | None) -> UPIAccount | None:
        """Service-specific account → branch default → any active branch account → organization default →
        any active organization-wide account."""
        if service is not None and service.upi_account_id:
            acct = self.db.get(UPIAccount, service.upi_account_id)
            if acct and acct.is_active and acct.deleted_at is None:
                return acct
        base = select(UPIAccount).where(UPIAccount.organization_id == self.org.id, UPIAccount.is_active.is_(True), UPIAccount.deleted_at.is_(None))
        if branch_id is not None:
            acct = self.db.scalars(base.where(UPIAccount.branch_id == branch_id).order_by(UPIAccount.is_default.desc(), UPIAccount.sort_order, UPIAccount.id)).first()
            if acct:
                return acct
        return self.db.scalars(base.where(UPIAccount.branch_id.is_(None)).order_by(UPIAccount.is_default.desc(), UPIAccount.sort_order, UPIAccount.id)).first()

    # -------------------------------------------------------------- output
    def to_read(self, acct: UPIAccount) -> UPIAccountRead:
        branch = self.db.get(Branch, acct.branch_id) if acct.branch_id else None
        services = self.db.scalar(select(func.count()).select_from(Service).where(Service.upi_account_id == acct.id, Service.deleted_at.is_(None))) or 0
        return UPIAccountRead(
            id=acct.public_id, branch_id=branch.public_id if branch else None, branch_name=branch.name if branch else None, display_name=acct.display_name,
            upi_id=acct.upi_id, merchant_name=acct.merchant_name, merchant_code=acct.merchant_code, static_qr_path=acct.static_qr_path,
            use_dynamic_qr=acct.use_dynamic_qr, payment_instructions=acct.payment_instructions, bank_name=acct.bank_name, account_last4=acct.account_last4,
            is_default=acct.is_default, is_active=acct.is_active, sort_order=acct.sort_order, service_count=int(services), created_at=acct.created_at,
        )

    @staticmethod
    def request_for(acct: UPIAccount, amount_paise: int | None, reference: str, note: str | None = None) -> UPIRequest:
        return UPIRequest(payee_vpa=acct.upi_id, payee_name=acct.merchant_name, amount_paise=amount_paise, reference=reference, note=note, merchant_code=acct.merchant_code)

    def preview(self, acct: UPIAccount, amount_paise: int | None) -> QRPreview:
        if not acct.use_dynamic_qr:
            return QRPreview(upi_uri=None, qr_data_url=acct.static_qr_path or "", is_static=True, amount_paise=None)
        req = self.request_for(acct, amount_paise, reference=f"TEST-{self.org.code}", note="Test payment request")
        return QRPreview(upi_uri=req.uri(), qr_data_url=qr_data_url(req.uri()), is_static=False, amount_paise=amount_paise)


def upi_public_ids(db: Session, ids: set[int]) -> dict[int, str]:
    return ids_to_public(db, UPIAccount, ids)
