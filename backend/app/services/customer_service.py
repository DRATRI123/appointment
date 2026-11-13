"""Minimal customer resolution needed for booking (full customer module arrives in Phase 5)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models import Customer, Organization, User
from app.schemas.appointment import CustomerInput
from app.security.identifiers import normalize_email, normalize_mobile


class CustomerService:
    def __init__(self, db: Session, org: Organization):
        self.db = db
        self.org = org

    def get(self, public_id: str) -> Customer:
        c = self.db.scalar(select(Customer).where(Customer.public_id == public_id, Customer.organization_id == self.org.id, Customer.deleted_at.is_(None)))
        if c is None:
            raise NotFoundError("Customer not found.")
        return c

    def for_user(self, user: User, full_name: str | None = None) -> Customer:
        c = self.db.scalar(select(Customer).where(Customer.organization_id == self.org.id, Customer.user_id == user.id, Customer.deleted_at.is_(None)))
        if c is None:
            c = Customer(
                organization_id=self.org.id, user_id=user.id, full_name=(full_name or user.full_name).strip(),
                mobile=user.mobile, email=user.email, is_guest=False, registered_at=utcnow(), source="online",
            )
            self.db.add(c)
            self.db.flush()
        else:
            if full_name and c.full_name != full_name.strip():
                c.full_name = full_name.strip()
            if not c.mobile and user.mobile:
                c.mobile = user.mobile
            if not c.email and user.email:
                c.email = user.email
        return c

    def resolve(self, payload: CustomerInput, *, user: User | None, allow_guest: bool, staff_booking: bool) -> Customer:
        if payload.customer_id:
            if not staff_booking:
                raise ValidationFailed("customer_id is only accepted for staff bookings.")
            return self.get(payload.customer_id)
        if user is not None and not staff_booking:
            return self.for_user(user, payload.full_name)
        # Guest or staff-entered customer: match by mobile (then email) within this organization.
        mobile = normalize_mobile(payload.mobile) if payload.mobile else None
        email = normalize_email(payload.email) if payload.email else None
        if not mobile and not email:
            raise ValidationFailed("A mobile number or email is required.", code="contact_required")
        if not staff_booking and not allow_guest:
            raise ValidationFailed("Please sign in to book.", code="login_required")
        stmt = select(Customer).where(Customer.organization_id == self.org.id, Customer.deleted_at.is_(None))
        existing = None
        if mobile:
            existing = self.db.scalar(stmt.where(Customer.mobile == mobile).order_by(Customer.user_id.desc().nullslast(), Customer.id))
        if existing is None and email:
            existing = self.db.scalar(stmt.where(Customer.email == email).order_by(Customer.id))
        if existing:
            if not existing.email and email:
                existing.email = email
            return existing
        c = Customer(
            organization_id=self.org.id, full_name=payload.full_name.strip(), mobile=mobile, email=email,
            is_guest=not staff_booking, registered_at=utcnow(), source="reception" if staff_booking else "online",
        )
        self.db.add(c)
        self.db.flush()
        return c
