"""Schema-level guarantees: tenant columns, unique constraints, partial unique indexes."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import AppointmentStatus, HoldStatus
from app.core.ids import new_reference
from app.models import (
    Appointment,
    Base,
    BookingHold,
    Branch,
    Customer,
    Organization,
    Payment,
    PaymentSubmission,
    Professional,
    Service,
    UPIAccount,
)

TENANT_EXEMPT = {
    "organizations", "organization_settings", "organization_domains", "organization_subscriptions",
    "branch_settings", "users", "user_sessions", "otp_verifications", "roles", "permissions",
    "role_permissions", "professional_branches", "professional_services", "service_pricing",
    "service_package_items", "appointment_status_history", "booking_form_fields",
    "notification_templates", "notifications", "notification_logs", "integration_logs",
    "webhook_events", "audit_logs", "system_settings",
}


def test_every_tenant_table_has_organization_id():
    missing = [
        name
        for name, table in Base.metadata.tables.items()
        if name not in TENANT_EXEMPT and "organization_id" not in table.columns
    ]
    assert missing == []


def test_expected_table_count():
    assert len(Base.metadata.tables) == 56


def _fixture_graph(db):
    org = Organization(slug="acme", code="ACME", name="Acme Clinic")
    db.add(org)
    db.flush()
    branch = Branch(organization_id=org.id, name="Main", code="MAIN", slug="main")
    prof = Professional(organization_id=org.id, display_name="Dr. A", slug="dr-a")
    svc = Service(organization_id=org.id, name="Consult", slug="consult", price_paise=50000)
    cust = Customer(organization_id=org.id, full_name="Pat")
    db.add_all([branch, prof, svc, cust])
    db.flush()
    return org, branch, prof, svc, cust


def _appt(org, branch, prof, svc, cust, start, status, seq=0):
    return Appointment(
        organization_id=org.id,
        reference=new_reference("APT", org.code),
        branch_id=branch.id,
        professional_id=prof.id,
        service_id=svc.id,
        customer_id=cust.id,
        start_at=start,
        end_at=start + timedelta(minutes=15),
        timezone="Asia/Kolkata",
        consultation_mode="in_person",
        status=status,
        slot_sequence=seq,
    )


def test_active_appointment_slot_is_unique(db):
    org, branch, prof, svc, cust = _fixture_graph(db)
    start = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)
    db.add(_appt(org, branch, prof, svc, cust, start, AppointmentStatus.CONFIRMED))
    db.flush()
    db.add(_appt(org, branch, prof, svc, cust, start, AppointmentStatus.PENDING_PAYMENT))
    with pytest.raises(IntegrityError):
        db.flush()


def test_cancelled_appointment_frees_slot(db):
    org, branch, prof, svc, cust = _fixture_graph(db)
    start = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)
    db.add(_appt(org, branch, prof, svc, cust, start, AppointmentStatus.CANCELLED))
    db.flush()
    db.add(_appt(org, branch, prof, svc, cust, start, AppointmentStatus.CONFIRMED))
    db.flush()  # no error: cancelled rows are outside the partial unique index


def test_active_hold_is_unique_per_slot(db):
    org, branch, prof, svc, cust = _fixture_graph(db)
    start = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)

    def hold(status):
        return BookingHold(
            organization_id=org.id,
            branch_id=branch.id,
            professional_id=prof.id,
            service_id=svc.id,
            session_key="s1",
            start_at=start,
            end_at=start + timedelta(minutes=15),
            status=status,
            expires_at=start,
        )

    db.add(hold(HoldStatus.EXPIRED))
    db.add(hold(HoldStatus.ACTIVE))
    db.flush()
    db.add(hold(HoldStatus.ACTIVE))
    with pytest.raises(IntegrityError):
        db.flush()


def test_duplicate_utr_rejected_within_organization(db):
    org, branch, prof, svc, cust = _fixture_graph(db)
    acct = UPIAccount(
        organization_id=org.id, display_name="Main", upi_id="acme@upi", merchant_name="Acme", is_default=True
    )
    db.add(acct)
    db.flush()

    def payment():
        return Payment(
            organization_id=org.id,
            reference=new_reference("PAY", org.code),
            customer_id=cust.id,
            upi_account_id=acct.id,
            amount_paise=50000,
        )

    p1, p2 = payment(), payment()
    db.add_all([p1, p2])
    db.flush()
    db.add(PaymentSubmission(organization_id=org.id, payment_id=p1.id, utr="123456789012", utr_normalized="123456789012"))
    db.flush()
    db.add(PaymentSubmission(organization_id=org.id, payment_id=p2.id, utr="123456789012", utr_normalized="123456789012"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_payment_amount_cannot_be_negative(db):
    org, *_ = _fixture_graph(db)
    db.add(Payment(organization_id=org.id, reference=new_reference("PAY", org.code), amount_paise=-1))
    with pytest.raises(IntegrityError):
        db.flush()


def test_upi_id_unique_per_organization(db):
    org, *_ = _fixture_graph(db)
    db.add(UPIAccount(organization_id=org.id, display_name="A", upi_id="acme@upi", merchant_name="Acme"))
    db.flush()
    db.add(UPIAccount(organization_id=org.id, display_name="B", upi_id="acme@upi", merchant_name="Acme"))
    with pytest.raises(IntegrityError):
        db.flush()
