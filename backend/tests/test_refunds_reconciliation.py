from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Payment, PaymentVerificationLog
from app.payments.reconciliation import PRESETS, ParserConfig, extract_utr, extract_vpa, parse_csv, to_paise
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login
from tests.test_payments import PNG, _account, _booked, _checkout, _storage, _submit, _verifier

IST = timezone(timedelta(hours=5, minutes=30))


def _verified(client, c: Clinic, hour=9, mobile="9777777777", utr="412345678901", amount=50000):
    appt = _booked(c, hour=hour, mobile=mobile)
    pid = _submit(client, c, appt, utr=utr)["payment"]["id"]
    r = client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": amount}, headers=c.h)
    assert r.status_code == 200, r.text
    return appt, pid


def _process(client, rid, headers, ref="RFD412345678901", expect=200, **extra):
    body = {"refund_method": "upi", "refund_reference": ref, "money_sent_confirmed": True, **extra}
    r = client.post(f"/api/v1/refunds/{rid}/process", json=body, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


# ------------------------------------------------------------------ parsers
def test_statement_parsers_handle_bank_layouts():
    hdfc = (b"HDFC BANK Ltd.,,,,,,\nAccount No : 50100123456789,,,,,,\n,,,,,,\n"
            b"Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
            b'13/11/26,UPI-ASHA PATEL-asha.p@okicici-ICIC0001234-412345678901-PAYMENT,0000412345678901,13/11/26,,"200.00","1,20,200.00"\n'
            b'13/11/26,NEFT CR-HDFC0000001-RAHUL VERMA-HDFCN52026111300012,HDFCN52026111300012,13/11/26,,"30,000.00","1,50,200.00"\n'
            b'13/11/26,ATM WDL,000000000000,13/11/26,"2,000.00",,"1,48,200.00"\n'
            b"31/02/26,BROKEN DATE,,,,10.00,\n********,,,,,,\n")
    res = parse_csv(hdfc, ParserConfig.from_dict({k: v for k, v in PRESETS["hdfc"].items() if k != "label"}))
    assert [(r.amount_paise, r.utr, r.payer_vpa) for r in res.rows] == [(20000, "412345678901", "asha.p@okicici"), (3000000, "HDFCN52026111300012", None)]
    assert len(res.skipped) == 1 and "Unrecognised date" in res.skipped[0]["error"]
    assert res.rows[0].fingerprint != res.rows[1].fingerprint and len(res.rows[0].fingerprint) == 64

    kotak = (b"Sl. No.,Transaction Date,Value Date,Description,Chq / Ref No.,Amount,Dr / Cr,Balance\n"
             b"1,13-11-2026,13-11-2026,UPI/312345678901/Payment from Ravi/ravi@ybl,UPI-312345678901,500.00,CR,10500.00\n"
             b"2,13-11-2026,13-11-2026,Rent,,2000.00,DR,8500.00\n")
    res = parse_csv(kotak, ParserConfig.from_dict({k: v for k, v in PRESETS["kotak"].items() if k != "label"}))
    assert [(r.amount_paise, r.direction, r.utr, r.payer_vpa) for r in res.rows] == [(50000, "credit", "312345678901", "ravi@ybl")]
    assert to_paise("1,20,200.00") == 12020000 and to_paise("(50.00)") == -5000 and to_paise("") is None
    assert extract_utr("UPI/CR/312345678901/RAHUL") == "312345678901" and extract_vpa("no vpa here") is None


# ------------------------------------------------------------------ refunds
def test_refund_lifecycle_requires_approval_reference_and_confirmation(client, db, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="rf-owner@example.com", name="Refund Clinic")
        _account(c)
        appt, pid = _verified(client, c)
        rec = _verifier(client, c, role="receptionist", mobile="9600000011")
        acc = _verifier(client, c, mobile="9600000012")

        # Refunds of unverified payments are refused (those are rejected, not refunded).
        appt2 = _booked(c, hour=10, mobile="9777777770")
        unverified = _submit(client, c, appt2, utr="512345678901")["payment"]["id"]
        r = client.post("/api/v1/refunds", json={"payment_id": unverified, "reason": "Duplicate booking"}, headers=rec)
        assert r.status_code == 409 and r.json()["code"] == "payment_not_verified"
        assert client.post("/api/v1/refunds", json={"payment_id": pid, "amount_paise": 60000, "reason": "Too much"}, headers=rec).json()["code"] == "refund_exceeds_paid"

        r = client.post("/api/v1/refunds", json={"payment_id": pid, "amount_paise": 20000, "reason": "Therapy shortened"}, headers=rec)
        assert r.status_code == 201, r.text
        refund = r.json()
        assert refund["status"] == "requested" and refund["reference"].startswith("RFD-") and refund["requested_by_name"] == "receptionist user"
        assert client.get(f"/api/v1/payments/{pid}", headers=acc).json()["status"] == "refund_requested"

        # Receptionists request; only approvers approve or process; processing needs approval first.
        assert client.post(f"/api/v1/refunds/{refund['id']}/approve", json={}, headers=rec).status_code == 403
        assert _process(client, refund["id"], acc, expect=409)["code"] == "invalid_transition"
        assert client.post(f"/api/v1/refunds/{refund['id']}/approve", json={"notes": "OK per doctor"}, headers=acc).json()["status"] == "approved"
        assert _process(client, refund["id"], acc, expect=422, money_sent_confirmed=False)["code"] == "refund_not_confirmed"
        assert client.post(f"/api/v1/refunds/{refund['id']}/process", json={"refund_method": "upi", "money_sent_confirmed": True}, headers=acc).status_code == 422
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        assert _process(client, refund["id"], acc, expect=422, processed_at=future)["code"] == "invalid_date"
        done = _process(client, refund["id"], acc, destination="pay.guest@okaxis")
        assert done["status"] == "processed" and done["refund_reference"] == "RFD412345678901" and done["processed_by_name"] == "accountant user"

        detail = client.get(f"/api/v1/payments/{pid}", headers=acc).json()
        assert detail["status"] == "verified" and detail["refund"]["refunded_paise"] == 20000 and detail["refund"]["refundable_paise"] == 30000
        assert c.get(f"/appointments/{appt['id']}")["paid_amount_paise"] == 30000
        assert [l["action"] for l in detail["logs"]][-3:] == ["refund_requested", "refund_approved", "refund_processed"]

        # Proof is private and audit-logged.
        r = client.post(f"/api/v1/refunds/{refund['id']}/proof", files={"file": ("p.png", io.BytesIO(PNG), "image/png")}, headers=acc)
        assert r.status_code == 200 and r.json()["has_proof"] is True
        proof = client.get(f"/api/v1/refunds/{refund['id']}/proof", headers=acc)
        assert proof.status_code == 200 and proof.content == PNG and proof.headers["cache-control"] == "private, no-store"

        # Refund the rest; the reference cannot be reused; the payment becomes fully refunded.
        rest = client.post("/api/v1/refunds", json={"payment_id": pid, "reason": "Appointment not needed"}, headers=acc).json()
        assert rest["amount_paise"] == 30000
        client.post(f"/api/v1/refunds/{rest['id']}/approve", json={}, headers=acc)
        assert _process(client, rest["id"], acc, expect=409)["code"] == "duplicate_refund_reference"
        _process(client, rest["id"], acc, ref="RFD512345678902")
        assert client.get(f"/api/v1/payments/{pid}", headers=acc).json()["status"] == "refund_processed"
        assert client.post("/api/v1/refunds", json={"payment_id": pid, "reason": "Again"}, headers=acc).json()["code"] in ("payment_not_verified", "nothing_refundable")

        stats = client.get("/api/v1/refunds/stats", headers=acc).json()
        assert stats["processed_this_month"] == 2 and stats["processed_amount_this_month_paise"] == 50000
        assert client.get("/api/v1/refunds", params={"search": "RFD512345678902"}, headers=acc).json()["meta"]["total"] == 1
        audit = c.get(f"/organizations/{c.org['id']}/audit-logs", {"action": "refund."})
        assert {"refund.requested", "refund.approved", "refund.processed", "refund.proof_viewed"} <= {row["action"] for row in audit["data"]}

        # Tenant isolation.
        other = Clinic(client, email="rf-other@example.com", name="Other Refund Clinic")
        assert client.get(f"/api/v1/refunds/{refund['id']}", headers=other.h).status_code == 404
        assert client.post(f"/api/v1/refunds/{rest['id']}/approve", json={}, headers=other.h).status_code == 404
        assert other.get("/refunds")["meta"]["total"] == 0
    finally:
        storage_module._storage = None


def test_cancellation_opens_refund_request_and_maker_checker(client, db):
    c = Clinic(client, email="rfc-owner@example.com", name="Cancel Refund Clinic")
    _account(c)
    appt, pid = _verified(client, c)
    client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel", "reason": "Patient travelling"}, headers=c.h)
    refunds = c.get("/refunds")["data"]
    assert len(refunds) == 1
    auto = refunds[0]
    assert auto["status"] == "requested" and auto["amount_paise"] == 50000 and auto["requested_by_name"] == "System (cancellation)"
    assert "Patient travelling" in auto["reason"] and auto["appointment_status"] == "cancelled"
    # Rejecting the request returns the payment to verified.
    r = client.post(f"/api/v1/refunds/{auto['id']}/reject", json={"reason": "Customer chose credit for the next visit"}, headers=c.h)
    assert r.json()["status"] == "rejected"
    summary = c.get(f"/refunds/for-payment/{pid}")
    assert summary["refundable_paise"] == 50000 and summary["suggested_paise"] == 50000 and "cancellation policy" in summary["suggestion_reason"]
    assert client.get(f"/api/v1/payments/{pid}", headers=c.h).json()["status"] == "verified"

    # Maker-checker: with the setting on, the requester cannot approve their own refund.
    c.put(f"/organizations/{c.org['id']}/settings/cancellation", {"values": {"refund_requires_second_approver": True}})
    mine = client.post("/api/v1/refunds", json={"payment_id": pid, "reason": "Goodwill refund"}, headers=c.h).json()
    r = client.post(f"/api/v1/refunds/{mine['id']}/approve", json={}, headers=c.h)
    assert r.status_code == 403 and r.json()["code"] == "second_approver_required"
    acc = _verifier(client, c, mobile="9600000013")
    assert client.post(f"/api/v1/refunds/{mine['id']}/approve", json={}, headers=acc).json()["status"] == "approved"
    # The requester can withdraw; a withdrawn refund cannot be processed.
    assert client.post(f"/api/v1/refunds/{mine['id']}/cancel", json={"notes": "Changed mind"}, headers=c.h).json()["status"] == "cancelled"
    assert _process(client, mine["id"], acc, expect=409)["code"] == "invalid_transition"

    # Cancelling inside the no-refund window opens no request.
    c.put(f"/organizations/{c.org['id']}/settings/cancellation", {"values": {"cancel_before_hours": 24 * 30}})
    appt2, _ = _verified(client, c, hour=10, mobile="9777777776", utr="612345678901")
    client.post(f"/api/v1/appointments/{appt2['id']}/status", json={"action": "cancel"}, headers=c.h)
    assert c.get("/refunds", {"search": appt2["reference"]})["meta"]["total"] == 0


def test_customer_sees_refund_outcome_only(client):
    c = Clinic(client, email="rfcu-owner@example.com", name="Customer Refund Clinic")
    _account(c)
    user = otp_login(client, "9888800001", "Meera Shah")
    client.cookies.clear()
    hold = c.public_hold(ist(c.monday, 9), session_key="cust")
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "cust", "customer": {"full_name": "Meera Shah"}}, headers=bearer(user))
    assert r.status_code == 201, r.text
    client.cookies.clear()
    appt = r.json()
    pid = _submit(client, c, appt, utr="712345678901")["payment"]["id"]
    client.post(f"/api/v1/admin/payments/{pid}/verify", json={"bank_credit_confirmed": True, "verified_amount_paise": 50000}, headers=c.h)
    rf = client.post("/api/v1/refunds", json={"payment_id": pid, "reason": "Internal: doctor unavailable"}, headers=c.h).json()
    mine = client.get("/api/v1/customer/refunds", headers=bearer(user)).json()
    assert len(mine) == 1 and mine[0]["status"] == "requested" and mine[0]["refund_reference"] is None and "notes" not in mine[0]
    client.post(f"/api/v1/refunds/{rf['id']}/approve", json={}, headers=c.h)
    _process(client, rf["id"], c.h, ref="RFD712345678901")
    mine = client.get("/api/v1/customer/refunds", headers=bearer(user)).json()
    assert mine[0]["status"] == "processed" and mine[0]["refund_reference"] == "RFD712345678901"
    assert client.get("/api/v1/refunds", headers=bearer(user)).status_code in (403, 404)


# ---------------------------------------------------------- reconciliation
def _statement(rows: list[tuple[str, str, str, str]]) -> bytes:
    today = datetime.now(IST).strftime("%d/%m/%y")
    lines = ["Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance"]
    for i, (narr, ref, debit, credit) in enumerate(rows):
        lines.append(f'{today},"{narr}",{ref},{today},{debit},{credit},{100000 + i}.00')
    return ("\n".join(lines) + "\n").encode()


def _import(client, headers, content: bytes, expect=201, **form):
    r = client.post("/api/v1/reconciliation/imports", files={"file": ("statement.csv", io.BytesIO(content), "text/csv")},
                    data={"parser_code": "hdfc", **form}, headers=headers)
    assert r.status_code == expect, r.text
    return r.json()


def test_statement_import_suggestions_matching_and_report(client, db, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="rec-owner@example.com", name="Recon Clinic")
        _account(c)
        a1 = _booked(c, hour=9, mobile="9711100001")
        p1 = _submit(client, c, a1, utr="412300000001")["payment"]["id"]           # UTR will appear in the statement
        a2 = _booked(c, hour=10, mobile="9711100002")
        p2_ref = _checkout(client, c, a2)["payment"]["reference"]                  # unpaid; reference appears in narration
        a3, p3 = _verified(client, c, hour=11, mobile="9711100003", utr="412300000003")  # verified, no bank line
        content = _statement([
            ("UPI-PAY GUEST-guest@okicici-ICIC0000001-412300000001-PAYMENT", "0000412300000001", "", "500.00"),
            (f"UPI-RAVI-ravi@ybl-UTIB0000001-512300000002-{p2_ref[:-6]}", "0000512300000002", "", "500.00"),
            ("=HYPERLINK(evil) NEFT CR SUPPLIER REFUND", "HDFCN52026111399999", "", "1234.00"),
            ("ATM WDL", "000000000000", "2000.00", ""),
        ])
        acc = _verifier(client, c, mobile="9600000021")
        rec = _verifier(client, c, role="receptionist", mobile="9600000022")
        assert client.get("/api/v1/reconciliation/imports", headers=rec).status_code == 403

        # Previewing detects the bank format; non-CSV uploads are refused.
        pv = client.post("/api/v1/reconciliation/preview", files={"file": ("s.csv", io.BytesIO(content), "text/csv")}, headers=acc).json()
        assert pv["detected_preset"] == "hdfc" and pv["rows"][0][0] == "Date"
        bad = client.post("/api/v1/reconciliation/imports", files={"file": ("s.pdf", io.BytesIO(b"%PDF-1.4 xx"), "application/pdf")}, data={"parser_code": "hdfc"}, headers=acc)
        assert bad.status_code == 422 and bad.json()["code"] == "unsupported_file"
        wrong = _import(client, acc, content, expect=422, parser_code="kotak")
        assert wrong["code"] == "statement_unreadable"

        imp = _import(client, acc, content)
        assert imp["total_rows"] == 3 and imp["duplicate_rows"] == 0 and imp["suggested_rows"] == 2 and imp["status"] == "parsed"
        again = _import(client, acc, content)
        assert again["total_rows"] == 0 and again["duplicate_rows"] == 3

        txns = {t["utr"]: t for t in client.get("/api/v1/reconciliation/transactions", params={"import_id": imp["id"]}, headers=acc).json()["data"]}
        t1, t2, t3 = txns["412300000001"], txns["512300000002"], txns["HDFCN52026111399999"]
        assert t1["match_status"] == "suggested" and t1["matched_payment_id"] == p1 and t1["match_confidence"] >= 90
        assert t2["match_status"] == "suggested" and t2["matched_payment_reference"] == p2_ref
        assert t3["match_status"] == "unmatched"
        cands = client.get(f"/api/v1/reconciliation/transactions/{t1['id']}/candidates", headers=acc).json()
        assert cands[0]["payment_id"] == p1 and "UTR matches the customer's submission" in cands[0]["reasons"]

        # Confirming a match is evidence only: the payment stays submitted until a verifier approves it.
        m = client.post(f"/api/v1/reconciliation/transactions/{t1['id']}/match", json={"payment_id": p1}, headers=acc).json()
        assert m["match_status"] == "matched" and m["matched_by_name"] == "accountant user"
        detail = client.get(f"/api/v1/payments/{p1}", headers=acc).json()
        assert detail["status"] == "submitted" and detail["bank_evidence"][0]["matched_to_this_payment"] is True
        assert detail["logs"][-1]["action"] == "bank_matched" and detail["logs"][-1]["to_status"] == "submitted"
        # One bank credit per payment; amount mismatches need a note.
        r = client.post(f"/api/v1/reconciliation/transactions/{t2['id']}/match", json={"payment_id": p1}, headers=acc)
        assert r.status_code == 409 and r.json()["code"] == "payment_already_matched"
        r = client.post(f"/api/v1/reconciliation/transactions/{t3['id']}/match", json={"payment_id": p3}, headers=acc)
        assert r.status_code == 422 and r.json()["code"] == "amount_mismatch"
        assert client.post(f"/api/v1/reconciliation/transactions/{t3['id']}/ignore", json={"reason": "Supplier refund"}, headers=acc).json()["match_status"] == "ignored"

        stats = client.get("/api/v1/reconciliation/stats", headers=acc).json()
        assert stats == {"unmatched": 0, "suggested": 1, "matched": 1, "ignored": 1, "unmatched_amount_paise": 50000, "verified_without_bank_match": 1}
        report = client.get("/api/v1/reconciliation/report", headers=acc).json()
        assert [t["utr"] for t in report["bank_credits"]] == ["512300000002"] and [p["payment_id"] for p in report["payments"]] == [p3]
        csv_body = client.get("/api/v1/reconciliation/report.csv", headers=acc)
        assert csv_body.status_code == 200 and "Verified payment without bank credit" in csv_body.text

        # Restoring an ignored line puts it back; the formula-looking narration is neutralised in the export.
        client.post(f"/api/v1/reconciliation/transactions/{t3['id']}/restore", headers=acc)
        assert "'=HYPERLINK" in client.get("/api/v1/reconciliation/report.csv", headers=acc).text

        # Dismissing a suggestion, unmatching, and deletion guards.
        assert client.post(f"/api/v1/reconciliation/transactions/{t2['id']}/unmatch", json={}, headers=acc).json()["match_status"] == "unmatched"
        r = client.delete(f"/api/v1/reconciliation/imports/{imp['id']}", headers=acc)
        assert r.status_code == 409 and r.json()["code"] == "import_has_matches"
        client.post(f"/api/v1/reconciliation/transactions/{t1['id']}/unmatch", json={"reason": "Wrong line"}, headers=acc)
        logs = db.scalars(select(PaymentVerificationLog.action).join(Payment, Payment.id == PaymentVerificationLog.payment_id).where(Payment.public_id == p1)).all()
        assert "bank_unmatched" in logs
        assert client.delete(f"/api/v1/reconciliation/imports/{imp['id']}", headers=acc).status_code == 200
        assert client.post("/api/v1/reconciliation/suggest", headers=acc).status_code == 200

        # Another organization sees none of it.
        other = Clinic(client, email="rec-other@example.com", name="Other Recon Clinic")
        assert other.get("/reconciliation/imports") == [] and other.get("/reconciliation/transactions")["meta"]["total"] == 0
        assert client.post(f"/api/v1/reconciliation/transactions/{t2['id']}/match", json={"payment_id": p1}, headers=other.h).status_code == 404
    finally:
        storage_module._storage = None


def test_custom_mapping_import(client, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="map-owner@example.com", name="Mapping Clinic")
        today = datetime.now(IST).strftime("%Y-%m-%d")
        content = f"When;Details;Money In;Money Out\n{today};UPI 812345678901 from ab@ybl;1.234,00;\n".replace("1.234,00", "1234.00").encode()
        mapping = '{"date_column": "When", "description_column": "Details", "credit_column": "Money In", "debit_column": "Money Out", "delimiter": ";", "date_formats": ["%Y-%m-%d"]}'
        imp = _import(client, c.h, content, parser_code="custom", mapping=mapping)
        assert imp["total_rows"] == 1 and imp["parser_code"] == "custom"
        t = c.get("/reconciliation/transactions")["data"][0]
        assert t["amount_paise"] == 123400 and t["utr"] == "812345678901" and t["payer_vpa"] == "ab@ybl"
        assert _import(client, c.h, content, expect=422, parser_code="custom", mapping='{"date_column": "When"}')["code"] == "invalid_mapping"
        assert _import(client, c.h, content, expect=422, parser_code="custom", mapping="not json")["code"] == "invalid_mapping"
    finally:
        storage_module._storage = None
