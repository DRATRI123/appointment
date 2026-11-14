from __future__ import annotations

import csv
import io
from datetime import timedelta

from openpyxl import load_workbook
from sqlalchemy import select

from app.core.time import utcnow
from app.models import AuditLog, Professional, User
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login, register
from tests.test_payments import _verifier


def _act(c: Clinic, appt_id: str, action: str):
    r = c.client.post(f"/api/v1/appointments/{appt_id}/status", json={"action": action}, headers=c.h)
    assert r.status_code == 200, r.text


def _day_of_outcomes(c: Clinic):
    """Monday: 9:00 confirmed, 9:30 cancelled, 10:00 completed + cash paid, 10:30 no-show."""
    a1 = c.staff_book(ist(c.monday, 9), customer={"full_name": "Asha Patel", "mobile": "9800000001"})
    a2 = c.staff_book(ist(c.monday, 9, 30), customer={"full_name": "=HYPERLINK(\"x\")", "mobile": "9800000002"})
    a3 = c.staff_book(ist(c.monday, 10), customer={"full_name": "Ravi Kumar", "mobile": "9800000003"})
    a4 = c.staff_book(ist(c.monday, 10, 30), customer={"full_name": "Meera Shah", "mobile": "9800000004"})
    _act(c, a2["id"], "cancel")
    _act(c, a3["id"], "check_in")
    _act(c, a3["id"], "complete")
    r = c.client.post("/api/v1/payments", json={"appointment_id": a3["id"], "kind": "full", "method": "cash"}, headers=c.h)
    assert r.status_code == 201, r.text
    _act(c, a4["id"], "no_show")
    return a1, a2, a3, a4


def _scheduled_minutes(c: Clinic) -> int:
    """The test clinic works 09:00-12:00 Monday to Friday; count working days in the dashboard range."""
    from datetime import date
    from zoneinfo import ZoneInfo

    day = utcnow().astimezone(ZoneInfo("Asia/Kolkata")).date()
    total = 0
    while day <= c.monday:
        total += 180 if day.weekday() < 5 else 0
        day = date.fromordinal(day.toordinal() + 1)
    return total


def _range(c: Clinic):
    from zoneinfo import ZoneInfo

    today = utcnow().astimezone(ZoneInfo("Asia/Kolkata")).date()
    return {"from": today.isoformat(), "to": c.monday.isoformat()}


def test_dashboard_kpis_breakdowns_and_scoping(client, db):
    c = Clinic(client, email="an-owner@example.com", name="Analytics Clinic", payment_mode="pay_at_clinic")
    _day_of_outcomes(c)
    d = c.get("/analytics/dashboard", _range(c))
    k = {key: m["value"] for key, m in d["kpis"].items()}
    assert (k["appointments"], k["booked"], k["completed"], k["cancelled"], k["no_show"]) == (4, 2, 1, 1, 1)
    assert k["cancellation_rate"] == 0.25 and k["no_show_rate"] == 0.5 and k["revenue_paise"] == 50000 and k["gross_receipts_paise"] == 50000
    assert k["booked_value_paise"] == 100000 and k["average_value_paise"] == 50000 and k["customers"] == 3 and k["new_customers"] == 3
    assert d["kpis"]["appointments"]["previous"] == 0 and d["scope"] == "organization"
    monday = next(p for p in d["series"] if p["date"] == c.monday.isoformat())
    assert (monday["booked"], monday["cancelled"], monday["no_show"]) == (2, 1, 1)
    assert sum(p["revenue_paise"] for p in d["series"]) == 50000
    pro = d["by_professional"][0]
    assert pro["key"] == c.pro["id"] and pro["appointments"] == 4 and pro["booked_minutes"] == 60 and pro["available_minutes"] == _scheduled_minutes(c)
    assert abs(pro["utilization"] - 60 / _scheduled_minutes(c)) < 0.001
    assert pro["revenue_paise"] == 50000 and d["by_service"][0]["label"] == "Consultation" and d["by_source"][0]["label"] == "Reception"
    assert d["payment_methods"] == [{"key": "cash", "label": "Cash", "appointments": 1, "completed": 0, "cancelled": 0, "no_show": 0, "revenue_paise": 50000,
                                     "booked_minutes": 0, "available_minutes": None, "utilization": None}]
    assert {(h["weekday"], h["hour"]) for h in d["heatmap"]} == {(0, 9), (0, 10)}
    assert set(d["attention"]) >= {"payments_to_verify", "refunds_to_approve", "unmatched_bank_credits", "failed_notifications", "calendar_sync_problems"}

    # Filters narrow everything; bad ranges are refused.
    other_branch = c.post("/branches", {"name": "Second", "code": "SEC"})
    assert c.get("/analytics/dashboard", {**_range(c), "branch_id": other_branch["id"]})["kpis"]["appointments"]["value"] == 0
    assert client.get("/api/v1/analytics/dashboard", params={"from": "2026-12-10", "to": "2026-12-01"}, headers=c.h).json()["code"] == "invalid_range"
    assert client.get("/api/v1/analytics/dashboard", params={"from": "2024-01-01", "to": "2026-12-01"}, headers=c.h).json()["code"] == "range_too_long"

    # A professional (no reports:read) sees only their own numbers; receptionists see nothing.
    doc_h = _verifier(client, c, role="professional", mobile="9600000051")
    assert client.get("/api/v1/analytics/dashboard", headers=doc_h).status_code == 403  # not linked to a professional yet
    me = otp_login(client, "9600000051")
    client.cookies.clear()
    other_pro = c.post("/professionals", {"display_name": "Dr. Other", "branches": [{"branch_id": c.branch["id"]}], "services": [{"service_id": c.service["id"]}]})
    row = db.scalar(select(Professional).where(Professional.public_id == other_pro["id"]))
    row.user_id = db.scalar(select(User.id).where(User.public_id == me["user"]["id"]))
    db.flush()
    mine = client.get("/api/v1/analytics/dashboard", params={**_range(c), "professional_id": c.pro["id"]}, headers=doc_h).json()
    assert mine["scope"] == "professional" and mine["kpis"]["appointments"]["value"] == 0  # the professional filter is forced to their own
    rec = _verifier(client, c, role="receptionist", mobile="9600000052")
    assert client.get("/api/v1/analytics/dashboard", headers=rec).status_code == 403
    other = Clinic(client, email="an-other@example.com", name="Other Analytics")
    assert other.get("/analytics/dashboard", _range(c))["kpis"]["appointments"]["value"] == 0


def test_reports_preview_csv_excel_permissions_and_audit(client, db):
    c = Clinic(client, email="rp-owner@example.com", name="Reports Clinic", payment_mode="pay_at_clinic")
    _day_of_outcomes(c)
    rng = _range(c)
    keys = {r["key"] for r in c.get("/reports")}
    assert {"appointments", "payments", "refunds", "daily_summary", "professionals", "services", "customers", "cancellations", "tax_summary", "coupons"} <= keys

    res = c.get("/reports/appointments", {**rng, "page_size": 2})
    assert res["total_rows"] == 4 and len(res["rows"]) == 2 and res["totals"] == {"total": 200000, "paid": 50000}
    assert res["rows"][0]["time"] == "09:00" and res["rows"][0]["date"] == c.monday.isoformat()
    cancels = c.get("/reports/cancellations", rng)
    assert cancels["total_rows"] == 1 and cancels["rows"][0]["cancelled_by"] == "staff"
    pros = c.get("/reports/professionals", rng)["rows"][0]
    assert pros["no_show_rate"] == 0.5 and pros["booked_hours"] == 1.0 and pros["available_hours"] == _scheduled_minutes(c) / 60
    custs = c.get("/reports/customers", rng)
    assert custs["total_rows"] == 3 and {r["new_in_range"] for r in custs["rows"]} == {"yes"}
    assert c.get("/reports/tax_summary", rng)["rows"][0]["total"] == 100000

    # CSV: UTF-8 BOM, rupees, formulas neutralised.
    r = client.get("/api/v1/reports/appointments/export", params={**rng, "format": "csv"}, headers=c.h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and r.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0][11] == "Total (INR)" and rows[1][11] == "500.00"
    assert any(row[4].startswith("'=HYPERLINK") for row in rows[1:])
    # Excel: typed cells, totals row, formulas stored as text, an About sheet.
    x = client.get("/api/v1/reports/appointments/export", params={**rng, "format": "xlsx"}, headers=c.h)
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    wb = load_workbook(io.BytesIO(x.content))
    ws = wb["Appointments"]
    assert ws["L1"].value == "Total (₹)" and ws["L2"].value == 500 and ws["L2"].number_format == "#,##0.00"
    assert ws.cell(row=ws.max_row, column=1).value == "Total" and ws.cell(row=ws.max_row, column=12).value == 2000
    cell = next(ws.cell(row=i, column=5) for i in range(2, ws.max_row) if str(ws.cell(row=i, column=5).value).startswith("=HYPERLINK"))
    assert cell.data_type == "s"
    assert wb["About"]["B1"].value == "Appointments" and wb["About"]["B2"].value == "Reports Clinic"
    exported = db.scalars(select(AuditLog).where(AuditLog.action == "report.exported")).all()
    assert len(exported) == 2 and exported[0].after["rows"] == 4 and exported[0].after["personal_data"] is True

    # Receptionists can't read reports; doctors (reports:read, no export) can preview but not export; other orgs see their own data only.
    rec = _verifier(client, c, role="receptionist", mobile="9600000061")
    assert client.get("/api/v1/reports", headers=rec).json() == []
    assert client.get("/api/v1/reports/daily_summary", headers=rec).status_code == 403
    doc = _verifier(client, c, role="doctor", mobile="9600000062")
    assert client.get("/api/v1/reports/daily_summary", params=rng, headers=doc).status_code == 200
    assert client.get("/api/v1/reports/daily_summary/export", params=rng, headers=doc).status_code == 403
    assert client.get("/api/v1/reports/payments", params=rng, headers=doc).status_code == 403  # needs payments:read too
    assert client.get("/api/v1/reports/nope", headers=c.h).status_code == 404
    other = Clinic(client, email="rp-other@example.com", name="Other Reports")
    assert other.get("/reports/appointments", rng)["total_rows"] == 0


def _root(client, db):
    tokens = register(client, "platform-root@example.com", "Root Admin")
    client.cookies.clear()
    user = db.scalar(select(User).where(User.email == "platform-root@example.com"))
    user.is_platform_admin = True
    db.flush()
    return bearer(tokens)


def test_platform_dashboard_plans_subscriptions_limits_and_settings(client, db):
    root = _root(client, db)
    c = Clinic(client, email="plat-owner@example.com", name="Plan Clinic", payment_mode="pay_at_clinic")
    c.staff_book(ist(c.monday, 9))
    assert client.get("/api/v1/platform/dashboard", headers=c.h).status_code == 403
    dash = client.get("/api/v1/platform/dashboard", params={"days": 30}, headers=root).json()
    assert dash["totals"]["organizations"] >= 1 and dash["totals"]["appointments"] >= 1 and len(dash["series"]) == 31
    assert any(t["name"] == "Plan Clinic" for t in dash["top_organizations"])

    plans = [{"code": "starter", "name": "Starter", "price_paise": 99900, "limits": {"branches": 1, "professionals": 2, "staff": 3}},
             {"code": "clinic", "name": "Clinic", "price_paise": 249900, "billing_cycle": "monthly", "limits": {"branches": None, "professionals": 10}}]
    assert client.put("/api/v1/platform/plans", json=[*plans, plans[0]], headers=root).json()["code"] == "duplicate_plan"
    assert client.put("/api/v1/platform/plans", json=[{**plans[0], "limits": {"seats": 3}}], headers=root).status_code == 422
    assert len(client.put("/api/v1/platform/plans", json=plans, headers=root).json()) == 2

    r = client.put(f"/api/v1/platform/organizations/{c.org['id']}/subscription", json={"plan_code": "starter", "status": "active", "notes": "Paid by bank transfer"}, headers=root)
    assert r.status_code == 200 and r.json()["subscription"]["plan_name"] == "Starter" and r.json()["usage"]["branches"] == 1
    # Limits: second branch refused, third professional refused.
    resp = client.post("/api/v1/branches", json={"name": "Second", "code": "SEC"}, headers=c.h)
    assert resp.status_code == 409 and resp.json()["code"] == "plan_limit" and "Starter plan allows 1 branches" in resp.json()["detail"]
    c.post("/professionals", {"display_name": "Dr. Two"})
    resp = client.post("/api/v1/professionals", json={"display_name": "Dr. Three"}, headers=c.h)
    assert resp.json()["code"] == "plan_limit"
    client.put(f"/api/v1/platform/organizations/{c.org['id']}/subscription", json={"plan_code": "clinic", "status": "active"}, headers=root)
    c.post("/branches", {"name": "Second", "code": "SEC"})
    history = client.get(f"/api/v1/platform/organizations/{c.org['id']}/subscriptions", headers=root).json()
    assert [h["plan_code"] for h in history] == ["clinic", "starter"]
    ov = client.get(f"/api/v1/platform/organizations/{c.org['id']}/overview", headers=root).json()
    assert ov["owner_contact"] == "plat-owner@example.com" and ov["usage"]["appointments_30d"] == 1 and ov["recent_activity"]
    subs = client.get("/api/v1/platform/subscriptions", params={"plan": "clinic"}, headers=root).json()
    assert [s["name"] for s in subs] == ["Plan Clinic"]
    audit = db.scalars(select(AuditLog.action).where(AuditLog.action.like("platform.%"))).all()
    assert {"platform.plans_updated", "platform.subscription_changed"} <= set(audit)

    # Settings: sign-up switch, default trial plan, public announcement.
    assert client.put("/api/v1/platform/settings", json={"default_plan_code": "nope"}, headers=root).json()["code"] == "unknown_plan"
    s = client.put("/api/v1/platform/settings", json={"platform_name": "ClinicBook", "default_plan_code": "starter", "default_trial_days": 21,
                                                       "announcement": "Maintenance on Sunday 2 am", "allow_organization_signup": True}, headers=root).json()
    assert s["default_trial_days"] == 21
    assert client.get("/api/v1/meta/platform").json()["announcement"] == "Maintenance on Sunday 2 am"
    newbie = register(client, "newbie@example.com", "New Owner")
    client.cookies.clear()
    org = client.post("/api/v1/organizations", json={"name": "Fresh Clinic"}, headers=bearer(newbie)).json()
    sub = client.get(f"/api/v1/platform/organizations/{org['id']}/overview", headers=root).json()["subscription"]
    assert sub["plan_code"] == "starter" and sub["status"] == "trial" and sub["trial_ends_at"]
    assert client.put("/api/v1/platform/plans", json=[plans[1]], headers=root).json()["code"] == "default_plan_in_use"
    client.put("/api/v1/platform/settings", json={"allow_organization_signup": False}, headers=root)
    r = client.post("/api/v1/organizations", json={"name": "Blocked Clinic"}, headers=bearer(newbie))
    assert r.status_code == 403 and r.json()["code"] == "signup_closed"
    assert client.post("/api/v1/organizations", json={"name": "Root Clinic"}, headers=root).status_code == 201  # platform staff can still create

    # Organization export.
    x = client.get("/api/v1/platform/exports/organizations", params={"format": "xlsx"}, headers=root)
    wb = load_workbook(io.BytesIO(x.content))
    names = [wb.active.cell(row=i, column=1).value for i in range(2, wb.active.max_row + 1)]
    assert "Plan Clinic" in names and "Fresh Clinic" in names
    assert client.get("/api/v1/platform/exports/organizations", headers=c.h).status_code == 403
    _ = timedelta
