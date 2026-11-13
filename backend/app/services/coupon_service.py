"""Coupons: management and validation at booking time."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import Appointment, Coupon, Organization, Service, User
from app.schemas.payment import CouponCreate, CouponRead, CouponUpdate
from app.services.audit_service import RequestMeta, record_audit

RELEASED_STATUSES = (AppointmentStatus.CANCELLED, AppointmentStatus.EXPIRED)


class CouponInvalid(ValidationFailed):
    code = "coupon_invalid"


class CouponService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    def list(self) -> list[Coupon]:
        return list(self.db.scalars(select(Coupon).where(Coupon.organization_id == self.org.id, Coupon.deleted_at.is_(None)).order_by(Coupon.created_at.desc())).all())

    def get(self, public_id: str) -> Coupon:
        c = self.db.scalar(select(Coupon).where(Coupon.public_id == public_id, Coupon.organization_id == self.org.id, Coupon.deleted_at.is_(None)))
        if c is None:
            raise NotFoundError("Coupon not found.")
        return c

    def _check_services(self, ids: list[str] | None) -> list[str] | None:
        if not ids:
            return None
        found = set(self.db.scalars(select(Service.public_id).where(Service.public_id.in_(ids), Service.organization_id == self.org.id)).all())
        missing = set(ids) - found
        if missing:
            raise ValidationFailed(f"Unknown services: {', '.join(sorted(missing))}")
        return list(dict.fromkeys(ids))

    def create(self, payload: CouponCreate) -> Coupon:
        code = payload.code.upper()
        if self.db.scalar(select(Coupon.id).where(Coupon.organization_id == self.org.id, Coupon.code == code, Coupon.deleted_at.is_(None))):
            raise ConflictError("A coupon with this code already exists.", code="coupon_code_taken")
        data = payload.model_dump(exclude={"code", "service_ids"})
        c = Coupon(organization_id=self.org.id, code=code, service_ids=self._check_services(payload.service_ids), created_by_user_id=self.actor.id if self.actor else None, **data)
        self.db.add(c)
        self.db.flush()
        record_audit(self.db, action="coupon.created", actor=self.actor, organization_id=self.org.id, entity_type="coupon", entity_id=c.code, after=payload.model_dump(mode="json"), meta=self.meta)
        return c

    def update(self, c: Coupon, payload: CouponUpdate) -> Coupon:
        data = payload.model_dump(exclude_unset=True)
        if "service_ids" in data:
            data["service_ids"] = self._check_services(data["service_ids"])
        for k, v in data.items():
            setattr(c, k, v)
        if c.valid_from and c.valid_to and c.valid_from >= c.valid_to:
            raise ValidationFailed("valid_from must be before valid_to")
        self.db.flush()
        record_audit(self.db, action="coupon.updated", actor=self.actor, organization_id=self.org.id, entity_type="coupon", entity_id=c.code, after=payload.model_dump(mode="json", exclude_unset=True), meta=self.meta)
        return c

    def delete(self, c: Coupon) -> None:
        c.deleted_at = utcnow()
        c.is_active = False
        self.db.flush()
        record_audit(self.db, action="coupon.deleted", actor=self.actor, organization_id=self.org.id, entity_type="coupon", entity_id=c.code, meta=self.meta)

    def redemptions(self, c: Coupon, customer_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Appointment).where(Appointment.organization_id == self.org.id, Appointment.coupon_code == c.code, Appointment.status.not_in(RELEASED_STATUSES))
        if customer_id is not None:
            stmt = stmt.where(Appointment.customer_id == customer_id)
        return int(self.db.scalar(stmt) or 0)

    def validate(self, code: str, *, service: Service, price_paise: int, customer_id: int | None) -> Coupon:
        c = self.db.scalar(select(Coupon).where(Coupon.organization_id == self.org.id, Coupon.code == code.strip().upper(), Coupon.deleted_at.is_(None)))
        if c is None or not c.is_active:
            raise CouponInvalid("This coupon code is not valid.")
        now = utcnow()
        if c.valid_from and now < c.valid_from:
            raise CouponInvalid("This coupon is not active yet.")
        if c.valid_to and now > c.valid_to:
            raise CouponInvalid("This coupon has expired.")
        if c.service_ids and service.public_id not in c.service_ids:
            raise CouponInvalid("This coupon does not apply to the selected service.")
        if c.min_amount_paise and price_paise < c.min_amount_paise:
            raise CouponInvalid("The booking amount is below this coupon's minimum.")
        if c.max_redemptions is not None and self.redemptions(c) >= c.max_redemptions:
            raise CouponInvalid("This coupon has been fully used.")
        if customer_id is not None and c.per_customer_limit is not None and self.redemptions(c, customer_id) >= c.per_customer_limit:
            raise CouponInvalid("You have already used this coupon.")
        return c

    def to_read(self, c: Coupon) -> CouponRead:
        return CouponRead(
            id=c.public_id, code=c.code, description=c.description, discount_type=c.discount_type, discount_value=c.discount_value,
            max_discount_paise=c.max_discount_paise, min_amount_paise=c.min_amount_paise, valid_from=c.valid_from, valid_to=c.valid_to,
            max_redemptions=c.max_redemptions, per_customer_limit=c.per_customer_limit, service_ids=c.service_ids, is_active=c.is_active,
            redemptions=self.redemptions(c), created_at=c.created_at,
        )


def coupon_discount(c: Coupon, amount_paise: int) -> int:
    if c.discount_type == "percent":
        d = round(amount_paise * c.discount_value / 100)
    else:
        d = c.discount_value
    if c.max_discount_paise is not None:
        d = min(d, c.max_discount_paise)
    return max(0, min(d, amount_paise))
