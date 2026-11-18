"""A patient's bookings follow their verified mobile number and email.

Patients often book without signing in (a guest booking keeps the mobile number and email on the clinic's customer
record, without an account). When the same person later signs in with a one-time code sent to that mobile number or
email, they must see those bookings, their status and payments in their account: they should not depend on keeping
the private link of each booking.

Only contacts the account has *proved* count (``mobile_verified_at`` / ``email_verified_at``: a one-time code to it,
Google with a verified email, or the email verification link). A typed but unproven number or address never shows
anyone else's bookings.

* ``owned_customer_ids``: the person's customer records at every clinic: linked to the account, or not linked to any
  account yet and carrying one of the account's verified contacts.
* ``link_verified_customers``: links such records to the account (one per clinic; a clinic where the account already
  has a record keeps that one, and the other record stays visible through ``owned_customer_ids``).
"""
from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Customer, User


def verified_contacts(user: User) -> tuple[str | None, str | None]:
    mobile = user.mobile if user.mobile and user.mobile_verified_at is not None else None
    email = user.email if user.email and user.email_verified_at is not None else None
    return mobile, email


def _unlinked_matches(user: User):
    mobile, email = verified_contacts(user)
    conditions = []
    if mobile:
        conditions.append(Customer.mobile == mobile)
    if email:
        conditions.append(Customer.email == email)
    if not conditions:
        return None
    return and_(Customer.user_id.is_(None), Customer.deleted_at.is_(None), or_(*conditions))


def owned_customer_ids(db: Session, user: User) -> list[int]:
    own = and_(Customer.user_id == user.id, Customer.deleted_at.is_(None))
    matches = _unlinked_matches(user)
    where = or_(own, matches) if matches is not None else own
    return list(db.scalars(select(Customer.id).where(where)).all())


def link_verified_customers(db: Session, user: User) -> int:
    """Link unclaimed customer records with the account's verified contacts. Returns how many were linked."""
    matches = _unlinked_matches(user)
    if matches is None:
        return 0
    candidates = list(db.scalars(select(Customer).where(matches).order_by(Customer.id)).all())
    if not candidates:
        return 0
    taken = set(db.scalars(select(Customer.organization_id).where(Customer.user_id == user.id)).all())
    linked = 0
    for customer in candidates:
        if customer.organization_id in taken:
            continue  # this clinic already knows the account: keep its record (both stay visible to the patient)
        customer.user_id = user.id
        taken.add(customer.organization_id)
        linked += 1
        from app.services.audit_service import record_audit

        record_audit(db, action="customer.linked_to_account", actor=user, organization_id=customer.organization_id,
                     entity_type="customer", entity_id=customer.public_id, after={"by": "verified_contact"})
    if linked:
        db.flush()
    return linked
