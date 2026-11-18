"""A patient sees every booking made with their mobile number or email after signing in with a one-time code, without
keeping each booking's private link; nobody sees bookings through a number or address they have not proved."""
from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, Customer
from app.services.customer_link import owned_customer_ids
from tests.booking_helpers import Clinic, ist
from tests.helpers import otp_login


def _guest_booking(clinic: Clinic, hour: int, customer: dict, session="s1") -> dict:
    hold = clinic.public_hold(ist(clinic.monday, hour), session_key=session)
    clinic.client.cookies.clear()
    return clinic.public_book(hold["id"], session_key=session, customer=customer)


def _me(client, tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_guest_bookings_appear_after_signing_in_with_a_code_to_that_mobile(client, db):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    other = Clinic(client, email="other-owner@example.com", name="Other Clinic", payment_mode="pay_at_clinic")
    first = _guest_booking(clinic, 9, {"full_name": "Asha Patel", "mobile": "9811100001"})
    second = _guest_booking(other, 10, {"full_name": "Asha Patel", "mobile": "+91 98111 00001"}, session="s2")
    _guest_booking(clinic, 11, {"full_name": "Someone Else", "mobile": "9811100002"}, session="s3")
    client.cookies.clear()

    me = _me(client, otp_login(client, "9811100001"))
    client.cookies.clear()
    mine = client.get("/api/v1/customer/appointments", headers=me).json()
    assert sorted(a["reference"] for a in mine) == sorted([first["reference"], second["reference"]])  # both clinics, nobody else's
    assert {a["status"] for a in mine} == {"confirmed"}
    # The booking page opens without the private link for the signed-in owner.
    r = client.get(f"/api/v1/public/organizations/{clinic.org['slug']}/appointments/{first['reference']}", headers=me)
    assert r.status_code == 200 and r.json()["reference"] == first["reference"]
    assert {o["slug"] for o in client.get("/api/v1/customer/organizations", headers=me).json()} == {clinic.org["slug"], other.org["slug"]}
    # The records are now linked to the account (one per clinic) and the link is audit-logged.
    linked = db.scalars(select(Customer).where(Customer.mobile == "+919811100001")).all()
    assert {c.user_id for c in linked} != {None}
    assert db.scalar(select(AuditLog).where(AuditLog.action == "customer.linked_to_account")) is not None

    # Booking again while signed in uses the same patient record (no duplicate in the clinic's list).
    hold = clinic.public_hold(ist(clinic.monday, 10, 30), session_key="s4")
    r = client.post(f"/api/v1/public/organizations/{clinic.org['slug']}/appointments", headers=me,
                    json={"hold_id": hold["id"], "session_key": "s4", "customer": {"full_name": "Asha Patel", "mobile": "9811100001"}})
    assert r.status_code == 201, r.text
    assert db.scalar(select(Customer).where(Customer.organization_id == linked[0].organization_id, Customer.mobile == "+919811100001")) is not None
    assert len(db.scalars(select(Customer).where(Customer.organization_id == linked[0].organization_id, Customer.mobile == "+919811100001")).all()) == 1
    assert len(client.get("/api/v1/customer/appointments", headers=me).json()) == 3


def test_email_bookings_follow_a_code_sent_to_that_email(client):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    booked = _guest_booking(clinic, 9, {"full_name": "Ravi", "mobile": "9811100003", "email": "Ravi@Example.com"})
    client.cookies.clear()
    me = _me(client, otp_login(client, "ravi@example.com"))
    client.cookies.clear()
    assert [a["reference"] for a in client.get("/api/v1/customer/appointments", headers=me).json()] == [booked["reference"]]


def test_an_unproven_mobile_number_shows_nothing(client):
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    booked = _guest_booking(clinic, 9, {"full_name": "Meena", "mobile": "9811100004"})
    client.cookies.clear()
    # Someone registers with a password and types Meena's number: not proved, so not hers to see.
    r = client.post("/api/v1/auth/register", json={"full_name": "Not Meena", "email": "not-meena@example.com", "password": "Str0ngPass123", "mobile": "9811100004"})
    assert r.status_code == 201, r.text
    client.cookies.clear()
    h = _me(client, r.json())
    assert client.get("/api/v1/customer/appointments", headers=h).json() == []
    r = client.get(f"/api/v1/public/organizations/{clinic.org['slug']}/appointments/{booked['reference']}", headers=h)
    assert r.status_code == 403


def test_a_second_record_at_the_same_clinic_stays_visible(client, db):
    """The clinic already has an account-linked record and also an older guest record with the same verified mobile:
    the guest record is not merged (staff decide), but its bookings are still the patient's to see."""
    clinic = Clinic(client, payment_mode="pay_at_clinic")
    _guest_booking(clinic, 9, {"full_name": "Kiran", "mobile": "9811100005"})
    client.cookies.clear()
    tokens = otp_login(client, "9811100005")
    client.cookies.clear()
    from app.models import User

    user = db.scalar(select(User).where(User.mobile == "+919811100005"))
    linked = db.scalar(select(Customer).where(Customer.user_id == user.id))
    extra = Customer(organization_id=linked.organization_id, full_name="Kiran (old)", mobile="+919811100005", is_guest=True, source="reception")
    db.add(extra)
    db.commit()
    assert set(owned_customer_ids(db, user)) == {linked.id, extra.id}
    assert client.get("/api/v1/customer/appointments", headers=_me(client, tokens)).status_code == 200
