from __future__ import annotations

import io
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models import Appointment, Payment, PaymentVerificationLog
from app.payments.upi import UPIRequest, normalize_utr, qr_png
from app.services.appointment_service import expire_unpaid_appointments
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _storage(tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.EncryptingStorage(storage_module.LocalStorage(tmp_path))
    return storage_module


def _account(c: Clinic, **extra):
    body = {"display_name": "Main UPI", "upi_id": "Sunrise.Clinic@okhdfcbank", "merchant_name": "Sunrise Ayurveda", "payment_instructions": "Pay the exact amount.", **extra}
    return c.post("/upi-accounts", body)


def _booked(c: Clinic, hour=9, mobile="9777777777"):
    hold = c.public_hold(ist(c.monday, hour), session_key=f"s{hour}")
    return c.public_book(hold["id"], session_key=f"s{hour}", customer={"full_name": "Pay Guest", "mobile": mobile})


def _checkout(client, c: Clinic, appt):
    r = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment", params={"access_token": appt["access_token"]})
    assert r.status_code == 200, r.text
    return r.json()


def _submit(client, c: Clinic, appt, utr="412345678901", screenshot=None, expect=200):
    files = {"screenshot": ("pay.png", io.BytesIO(screenshot), "image/png")} if screenshot else None
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment/submit",
                    params={"access_token": appt["access_token"]}, data={"utr": utr, "notes": "Paid via GPay"}, files=files)
    assert r.status_code == expect, r.text
    return r.json()


def _verifier(client, c: Clinic, role="accountant", mobile="9600000001"):
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": mobile, "full_name": f"{role} user", "role_code": role})
    tokens = otp_login(client, mobile)
    client.cookies.clear()
    return {**bearer(tokens), "X-Organization-Id": c.org["id"]}


# --------------------------------------------------------------- UPI helpers
def test_upi_uri_encoding_and_qr():
    req = UPIRequest(payee_vpa="clinic@okhdfcbank", payee_name="Sunrise Ayurveda & Co", amount_paise=20050, reference="PAY-SUNR-01ABC", note="APT-1 #2")
    uri = req.uri()
    assert uri.startswith("upi://pay?pa=clinic@okhdfcbank&")
    q = parse_qs(urlparse(uri).query)
    assert q["pn"] == ["Sunrise Ayurveda & Co"] and q["am"] == ["200.50"] and q["cu"] == ["INR"] and q["tr"] == ["PAY-SUNR-01ABC"] and q["tn"] == ["APT-1 #2"]
    assert "%26" in uri and "%23" in uri  # '&' and '#' inside values never break the query
    assert req.app_links()["gpay"].startswith("tez://upi/pay?pa=clinic@okhdfcbank")
    assert qr_png(uri).startswith(b"\x89PNG\r\n\x1a\n")
    assert UPIRequest("a@b", "X", None, "R").uri().find("am=") == -1  # static amount-less request
    assert normalize_utr(" 4123-4567 8901 ") == "412345678901"


# ------------------------------------------------------------- UPI accounts
def test_upi_accounts_crud_defaults_selection_and_isolation(client):
    c = Clinic(client, email="upi-owner@example.com", name="UPI Clinic")
    a = _account(c)
    assert a["upi_id"] == "sunrise.clinic@okhdfcbank" and a["is_default"] is True
    assert client.post("/api/v1/upi-accounts", json={"display_name": "Dup", "upi_id": "sunrise.clinic@OKHDFCBANK", "merchant_name": "Xyz Co"}, headers=c.h).status_code == 409
    assert client.post("/api/v1/upi-accounts", json={"display_name": "Bad", "upi_id": "not-a-vpa", "merchant_name": "Xyz Co"}, headers=c.h).status_code == 422
    assert client.post("/api/v1/upi-accounts", json={"display_name": "Static", "upi_id": "s@ybl", "merchant_name": "X", "use_dynamic_qr": False}, headers=c.h).status_code == 422
    b = c.post("/upi-accounts", {"display_name": "Second", "upi_id": "second@ybl", "merchant_name": "Sunrise", "is_default": True})
    accounts = {x["id"]: x for x in c.get("/upi-accounts")}
    assert accounts[b["id"]]["is_default"] and not accounts[a["id"]]["is_default"]
    branch_acct = c.post("/upi-accounts", {"display_name": "Branch", "upi_id": "branch@okaxis", "merchant_name": "Sunrise Main", "branch_id": c.branch["id"]})
    assert branch_acct["is_default"] is True and branch_acct["branch_name"] == "Main"
    preview = c.get(f"/upi-accounts/{a['id']}/preview", {"amount_paise": 100})
    assert preview["upi_uri"].startswith("upi://pay?pa=sunrise.clinic@okhdfcbank") and preview["qr_data_url"].startswith("data:image/png;base64,")

    # Selection: branch account wins over organization default; a service-specific account wins over both.
    c.put(f"/organizations/{c.org['id']}/settings/booking", {"values": {"min_notice_minutes": 0}})
    appt = _booked(c)
    assert _checkout(client, c, appt)["upi"]["upi_id"] == "branch@okaxis"
    client.post("/api/v1/upi-accounts/assign", json={"service_id": c.service["id"], "upi_account_id": a["id"]}, headers=c.h)
    appt2 = _booked(c, hour=10, mobile="9777777778")
    assert _checkout(client, c, appt2)["upi"]["upi_id"] == "sunrise.clinic@okhdfcbank"

    # Another organization cannot see or use these accounts; receptionists cannot manage them.
    other = Clinic(client, email="upi-other@example.com", name="Other UPI Clinic")
    assert client.get(f"/api/v1/upi-accounts/{a['id']}", headers=other.h).status_code == 404
    assert other.get("/upi-accounts") == []
    hr = _verifier(client, c, role="receptionist", mobile="9600000009")
    assert client.get("/api/v1/upi-accounts", headers=hr).status_code == 200
    assert client.post("/api/v1/upi-accounts", json={"display_name": "Nope", "upi_id": "n@ybl", "merchant_name": "Nope Co"}, headers=hr).status_code == 403


# ------------------------------------------------------- end-to-end payment
def test_booking_creates_payment_request_and_checkout(client):
    c = Clinic(client, email="pay-owner@example.com", name="Pay Clinic")
    _account(c)
    appt = _booked(c)
    assert appt["status"] == "pending_payment"
    co = _checkout(client, c, appt)
    pay = co["payment"]
    assert pay["status"] == "awaiting_payment" and pay["amount_paise"] == 50000 and pay["reference"].startswith("PAY-")
    assert pay["expires_at"] is not None and co["can_submit"] is True
    q = parse_qs(urlparse(co["upi"]["upi_uri"]).query)
    assert q["am"] == ["500.00"] and q["tr"] == [pay["reference"]] and q["tn"] == [appt["reference"]] and q["pn"] == ["Sunrise Ayurveda"]
    assert co["upi"]["qr_data_url"].startswith("data:image/png;base64,") and set(co["upi"]["app_links"]) == {"any", "gpay", "phonepe", "paytm", "bhim"}
    assert co["upi"]["instructions"] == "Pay the exact amount."
    # Checkout needs the access token.
    assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment").status_code == 403

    # Pay-at-clinic and free services create no payment.
    client.patch(f"/api/v1/services/{c.service['id']}", json={"payment_mode": "pay_at_clinic"}, headers=c.h)
    appt2 = _booked(c, hour=10, mobile="9777777779")
    assert appt2["status"] == "confirmed" and _checkout(client, c, appt2) is None


def test_submission_never_confirms_and_only_verifiers_approve(client, db, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="ver-owner@example.com", name="Verify Clinic")
        _account(c)
        appt = _booked(c)
        co = _submit(client, c, appt, utr="4123 4567 8901", screenshot=PNG)
        assert co["payment"]["status"] == "submitted" and co["can_submit"] is False and co["latest_submission"]["has_screenshot"] is True
        status = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}", params={"access_token": appt["access_token"]}).json()
        assert status["status"] == "pending_verification" and status["paid_amount_paise"] == 0  # a screenshot is not money
        # Submitting twice is refused while in review.
        assert _submit(client, c, appt, utr="999999999999", expect=409)["code"] == "already_submitted"

        pid = co["payment"]["id"]
        rec = _verifier(client, c, role="receptionist", mobile="9600000002")
        assert client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000}, headers=rec).status_code == 403
        assert client.get("/api/v1/admin/payments/queue", headers=rec).status_code == 403

        acc = _verifier(client, c)
        queue = client.get("/api/v1/admin/payments/queue", headers=acc).json()
        assert queue["meta"]["total"] == 1 and queue["data"][0]["latest_utr"] == "4123 4567 8901"
        detail = client.get(f"/api/v1/payments/{pid}", headers=acc).json()
        sub = detail["submissions"][0]
        shot = client.get(f"/api/v1/payments/{pid}/submissions/{sub['id']}/screenshot", headers=acc)
        assert shot.status_code == 200 and shot.content == PNG and shot.headers["cache-control"] == "private, no-store"
        assert client.post(f"/api/v1/admin/payments/{pid}/review", headers=acc).json()["status"] == "under_review"

        r = client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": False, "verified_amount_paise": 50000}, headers=acc)
        assert r.status_code == 422 and r.json()["code"] == "bank_credit_unconfirmed"
        r = client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 40000}, headers=acc)
        assert r.status_code == 422 and r.json()["code"] == "amount_mismatch"
        r = client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000, "notes": "Seen in HDFC statement"}, headers=acc)
        assert r.status_code == 200, r.text
        done = r.json()
        assert done["status"] == "verified" and done["verified_amount_paise"] == 50000
        assert [log["action"] for log in done["logs"]] == ["created", "requested", "submitted", "review_started", "verified"]
        assert done["logs"][-1]["bank_credit_confirmed"] is True and done["logs"][-1]["actor_name"] == "accountant user"
        status = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}", params={"access_token": appt["access_token"]}).json()
        assert status["status"] == "confirmed" and status["paid_amount_paise"] == 50000
        # Verification is final.
        assert client.post(f"/api/v1/admin/payments/{pid}/reject", json={"reason": "late change"}, headers=acc).status_code == 409
        audit = c.get(f"/organizations/{c.org['id']}/audit-logs", {"action": "payment."})
        assert {"payment.verified", "payment.screenshot_viewed", "payment.submitted"} <= {row["action"] for row in audit["data"]}
    finally:
        storage_module._storage = None


def test_rejection_resubmission_and_duplicate_utr(client, db):
    c = Clinic(client, email="dup-owner@example.com", name="Dup Clinic")
    _account(c)
    a1 = _booked(c, hour=9, mobile="9711111111")
    a2 = _booked(c, hour=10, mobile="9722222222")
    p1 = _submit(client, c, a1, utr="111122223333")["payment"]["id"]
    # Same UTR for a different payment is refused and flagged on both payments.
    err = _submit(client, c, a2, utr="1111-2222-3333", expect=409)
    assert err["code"] == "duplicate_utr"
    acc = _verifier(client, c)
    assert client.get(f"/api/v1/payments/{p1}", headers=acc).json()["duplicate_utr_flag"] is True
    p2 = _checkout(client, c, a2)["payment"]
    assert p2["status"] == "awaiting_payment" and p2["duplicate_utr_flag"] is True

    # Reject needs a reason; it reopens the payment and returns the appointment to pending payment with a fresh window.
    assert client.post(f"/api/v1/admin/payments/{p1}/reject", json={"reason": ""}, headers=acc).status_code == 422
    r = client.post(f"/api/v1/admin/payments/{p1}/reject", json={"reason": "No credit found for this UTR"}, headers=acc)
    assert r.json()["status"] == "rejected"
    co = _checkout(client, c, a1)
    assert co["can_submit"] is True and "No credit found" in co["message"]
    status = client.get(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{a1['reference']}", params={"access_token": a1["access_token"]}).json()
    assert status["status"] == "pending_payment"
    # The customer may resubmit the same UTR for the same payment.
    assert _submit(client, c, a1, utr="111122223333")["payment"]["status"] == "submitted"
    assert len(client.get(f"/api/v1/payments/{p1}", headers=acc).json()["submissions"]) == 1
    logs = db.scalars(select(PaymentVerificationLog.action).join(Payment, Payment.id == PaymentVerificationLog.payment_id).where(Payment.public_id == p1)).all()
    assert logs.count("submitted") == 2 and "rejected" in logs and "duplicate_utr_attempt" in logs


def test_cash_bank_transfer_balance_and_closing_rules(client, db):
    c = Clinic(client, email="cash-owner@example.com", name="Cash Clinic")
    client.patch(f"/api/v1/services/{c.service['id']}", json={"payment_mode": "partial_advance", "advance_amount_paise": 20000}, headers=c.h)
    _account(c)
    appt = _booked(c)
    assert appt["advance_due_paise"] == 20000 and _checkout(client, c, appt)["payment"]["amount_paise"] == 20000

    # Receptionist records cash for the advance: the UPI request is cancelled and the appointment confirmed.
    rec = _verifier(client, c, role="receptionist", mobile="9600000003")
    r = client.post("/api/v1/payments", json={"appointment_id": appt["id"], "kind": "advance", "method": "cash"}, headers=rec)
    assert r.status_code == 201, r.text
    cash = r.json()
    assert cash["status"] == "verified" and cash["amount_paise"] == 20000 and cash["method"] == "cash"
    pays = c.get("/payments", {"appointment_id": appt["id"]})["data"]
    assert sorted(p["status"] for p in pays) == ["cancelled", "verified"]
    assert c.get(f"/appointments/{appt['id']}")["status"] == "confirmed"

    # Balance is computed by the server: total - paid.
    r = client.post("/api/v1/payments", json={"appointment_id": appt["id"], "kind": "balance", "method": "bank_transfer", "utr": "HDFCN52026111300012"}, headers=c.h)
    assert r.status_code == 201, r.text
    bal = r.json()
    assert bal["amount_paise"] == 30000 and bal["status"] == "submitted"
    assert client.post("/api/v1/payments", json={"appointment_id": appt["id"], "kind": "advance", "method": "upi_qr"}, headers=c.h).json()["code"] == "payment_in_review"
    client.post(f"/api/v1/admin/payments/{bal['id']}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 30000}, headers=c.h)
    assert c.get(f"/appointments/{appt['id']}")["paid_amount_paise"] == 50000
    assert client.post("/api/v1/payments", json={"appointment_id": appt["id"], "kind": "balance", "method": "upi_qr"}, headers=c.h).json()["code"] == "nothing_due"

    # Cancelling closes unpaid requests; expiry closes them as expired.
    a2 = _booked(c, hour=10, mobile="9733333333")
    client.post(f"/api/v1/appointments/{a2['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert _checkout(client, c, a2)["payment"]["status"] == "cancelled"
    a3 = _booked(c, hour=11, mobile="9744444444")
    row = db.scalar(select(Appointment).where(Appointment.public_id == a3["id"]))
    row.payment_due_at = row.payment_due_at - timedelta(hours=2)
    db.flush()
    assert expire_unpaid_appointments(db) == 1
    co = _checkout(client, c, a3)
    assert co["payment"]["status"] == "expired" and co["can_submit"] is False
    assert _submit(client, c, a3, expect=409)["code"] in ("payment_closed", "appointment_closed")

    stats = c.get("/admin/payments/stats")
    assert stats["verified_today"] == 2 and stats["verified_amount_today_paise"] == 50000


def test_no_upi_account_and_payment_isolation(client):
    c = Clinic(client, email="noupi-owner@example.com", name="No UPI Clinic")
    appt = _booked(c)
    co = _checkout(client, c, appt)
    assert co["upi"] is None and co["can_submit"] is False and "not set up UPI" in co["message"]
    other = Clinic(client, email="noupi-other@example.com", name="Other No UPI")
    assert client.get(f"/api/v1/payments/{co['payment']['id']}", headers=other.h).status_code == 404
    assert client.post(f"/api/v1/admin/payments/{co['payment']['id']}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 1}, headers=other.h).status_code == 404


# ------------------------------------------------------------------ coupons
def test_coupons_validation_quote_and_booking(client):
    c = Clinic(client, email="coupon-owner@example.com", name="Coupon Clinic")
    _account(c)
    assert client.post("/api/v1/coupons", json={"code": "BAD", "discount_type": "percent", "discount_value": 150}, headers=c.h).status_code == 422
    c.post("/coupons", {"code": "welcome10", "discount_type": "percent", "discount_value": 10, "max_discount_paise": 3000})
    c.post("/coupons", {"code": "FLAT100", "discount_type": "flat", "discount_value": 10000, "min_amount_paise": 60000})
    c.post("/coupons", {"code": "FREE", "discount_type": "percent", "discount_value": 100, "max_redemptions": 1})
    assert client.post("/api/v1/coupons", json={"code": "WELCOME10", "discount_type": "flat", "discount_value": 1}, headers=c.h).status_code == 409

    def quote(code):
        return client.get(f"/api/v1/public/organizations/{c.org['slug']}/quote", params={"service_id": c.service["id"], "branch_id": c.branch["id"], "coupon_code": code})

    q = quote("welcome10").json()
    assert q["discount_paise"] == 3000 and q["total_amount_paise"] == 47000 and q["breakdown"]["coupon_code"] == "WELCOME10"  # 10% capped at ₹30
    r = quote("FLAT100")
    assert r.status_code == 422 and r.json()["code"] == "coupon_invalid"
    assert quote("NOPE").status_code == 422

    hold = c.public_hold(ist(c.monday, 9), session_key="cp")
    appt = c.public_book(hold["id"], session_key="cp", customer={"full_name": "Free Guest", "mobile": "9755555555"}, coupon_code="free")
    assert appt["total_amount_paise"] == 0 and appt["status"] == "confirmed"
    assert c.get(f"/appointments/{appt['id']}")["pricing_snapshot"]["coupon_discount_paise"] == 50000
    # Fully used now; cancelling gives the redemption back.
    assert quote("FREE").json()["code"] == "coupon_invalid"
    client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert quote("FREE").status_code == 200
    assert [x["redemptions"] for x in c.get("/coupons") if x["code"] == "FREE"] == [0]
