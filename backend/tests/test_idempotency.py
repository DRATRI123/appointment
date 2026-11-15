"""Idempotency-Key: a retried booking or payment submission returns the first response and does nothing twice."""
from __future__ import annotations

from sqlalchemy import func, select

from app.models import Appointment, IdempotencyKey, PaymentSubmission
from app.security.crypto import is_encrypted
from tests.booking_helpers import Clinic, iso, ist
from tests.test_payments import _account


def _public_book(c: Clinic, hold_id: str, key: str | None, name="Asha Patel", session="s9"):
    headers = {"Idempotency-Key": key} if key else {}
    return c.client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", headers=headers,
                         json={"hold_id": hold_id, "session_key": session, "customer": {"full_name": name, "mobile": "9777777777"}})


def test_a_retried_public_booking_returns_the_first_booking(client, db):
    c = Clinic(client)
    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    first = _public_book(c, hold["id"], "book-7f3a9c21")
    assert first.status_code == 201, first.text
    again = _public_book(c, hold["id"], "book-7f3a9c21")
    assert again.status_code == 201
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["reference"] == first.json()["reference"]
    assert again.json()["access_token"] == first.json()["access_token"]
    assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.reference == first.json()["reference"])) == 1
    # The stored response holds the booking's access token, so it is encrypted at rest.
    stored = db.scalar(select(IdempotencyKey).where(IdempotencyKey.key == "book-7f3a9c21"))
    assert is_encrypted(stored.response_body) and first.json()["access_token"] not in stored.response_body


def test_without_a_key_a_retry_is_refused_instead_of_booking_twice(client):
    c = Clinic(client)
    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    assert _public_book(c, hold["id"], None).status_code == 201
    assert _public_book(c, hold["id"], None).status_code in (404, 409, 422)


def test_the_same_key_with_a_different_request_is_rejected(client):
    c = Clinic(client)
    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    assert _public_book(c, hold["id"], "book-key-0001").status_code == 201
    r = _public_book(c, hold["id"], "book-key-0001", name="Someone Else")
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_reused"


def test_keys_belong_to_their_caller(client):
    """Another visitor reusing a key they saw cannot read the first visitor's booking."""
    c = Clinic(client)
    h1 = c.public_hold(ist(c.monday, 9), session_key="s9")
    h2 = c.public_hold(ist(c.monday, 10), session_key="s10")
    first = _public_book(c, h1["id"], "shared-key-123")
    other = _public_book(c, h2["id"], "shared-key-123", session="s10")
    assert first.status_code == other.status_code == 201
    assert other.json()["reference"] != first.json()["reference"] and "Idempotent-Replayed" not in other.headers


def test_a_failed_request_stores_nothing_and_can_be_retried(client):
    c = Clinic(client)
    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    bad = c.client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", headers={"Idempotency-Key": "retry-after-fix"},
                        json={"hold_id": hold["id"], "session_key": "wrong", "customer": {"full_name": "Asha Patel", "mobile": "9777777777"}})
    assert bad.status_code >= 400
    assert _public_book(c, hold["id"], "retry-after-fix").status_code == 201


def test_invalid_keys_are_rejected(client):
    c = Clinic(client)
    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    r = _public_book(c, hold["id"], "short")
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_invalid"


def test_staff_booking_and_payment_submission_are_idempotent(client, db):
    c = Clinic(client)
    _account(c)
    body = {"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 10)),
            "customer": {"full_name": "Walk In", "mobile": "9888888888"}, "source": "reception"}
    h = {**c.h, "Idempotency-Key": "desk-booking-42"}
    first = client.post("/api/v1/appointments", json=body, headers=h)
    again = client.post("/api/v1/appointments", json=body, headers=h)
    assert first.status_code == again.status_code == 201
    assert again.json()["id"] == first.json()["id"] and again.headers["Idempotent-Replayed"] == "true"

    hold = c.public_hold(ist(c.monday, 9), session_key="s9")
    appt = _public_book(c, hold["id"], None).json()
    url = f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment/submit"
    client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment", params={"access_token": appt["access_token"]})
    sub = {"params": {"access_token": appt["access_token"]}, "data": {"utr": "412345678901"}, "headers": {"Idempotency-Key": "utr-submit-1"}}
    one, two = client.post(url, **sub), client.post(url, **sub)
    assert one.status_code == two.status_code == 200, (one.text, two.text)
    assert two.headers["Idempotent-Replayed"] == "true"
    assert db.scalar(select(func.count()).select_from(PaymentSubmission).where(PaymentSubmission.utr == "412345678901")) == 1
