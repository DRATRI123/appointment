"""Tabular reports with identical preview, CSV and Excel output.

Each report declares its columns (with a type that drives formatting) and the permissions it needs; the
row generator receives the same ``Filters`` as the dashboard. Exports are audit-logged. Text that a
spreadsheet would execute (=, +, -, @) is neutralised in CSV and stored as plain text in Excel.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus as A
from app.core.exceptions import NotFoundError, PermissionDenied
from app.core.time import utcnow
from app.models import (
    Appointment,
    AppointmentCancellation,
    Branch,
    Customer,
    Organization,
    Payment,
    PaymentRefund,
    PaymentSubmission,
    Professional,
    Service,
    User,
)
from app.services.analytics_service import METHOD_LABEL, NEVER_HAPPENED, NOT_BOOKED, SOURCE_LABEL, VERIFIED_LIKE, AnalyticsService, Filters

MAX_ROWS = 50_000


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: str = "text"  # text | int | money | percent | date | datetime | time


@dataclass(frozen=True)
class ReportDef:
    key: str
    title: str
    description: str
    columns: list[Column]
    rows: Callable[[ReportContext], Iterable[dict[str, Any]]]
    permissions: tuple[str, ...] = ("reports:read",)
    totals: tuple[str, ...] = field(default_factory=tuple)
    contains_personal_data: bool = False


class ReportContext:
    def __init__(self, db: Session, org: Organization, f: Filters):
        self.db, self.org, self.f = db, org, f
        self._cache: dict[str, dict] = {}

    def names(self, model, attr: str = "name") -> dict[int, str]:
        key = f"{model.__tablename__}.{attr}"
        if key not in self._cache:
            self._cache[key] = dict(self.db.execute(select(model.id, getattr(model, attr)).where(model.organization_id == self.org.id)).all())
        return self._cache[key]

    def local(self, dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(self.f.tz)

    def appointments(self):
        f = self.f
        stmt = select(Appointment).where(Appointment.organization_id == self.org.id, Appointment.start_at >= f.start, Appointment.start_at < f.end)
        if f.branch_id:
            stmt = stmt.where(Appointment.branch_id == f.branch_id)
        if f.professional_id:
            stmt = stmt.where(Appointment.professional_id == f.professional_id)
        if f.service_id:
            stmt = stmt.where(Appointment.service_id == f.service_id)
        return self.db.scalars(stmt.order_by(Appointment.start_at).limit(MAX_ROWS + 1)).all()


# ----------------------------------------------------------------- reports
def _appointments(ctx: ReportContext):
    svc, pro, br = ctx.names(Service), ctx.names(Professional, "display_name"), ctx.names(Branch)
    custs = {c.id: c for c in ctx.db.scalars(select(Customer).where(Customer.organization_id == ctx.org.id)).all()}
    for a in ctx.appointments():
        c = custs.get(a.customer_id)
        start = ctx.local(a.start_at)
        yield {"date": start.date(), "time": start.strftime("%H:%M"), "reference": a.reference, "status": a.status.replace("_", " "),
               "customer": c.full_name if c else "", "mobile": c.mobile if c else "", "service": svc.get(a.service_id, ""), "professional": pro.get(a.professional_id, ""),
               "branch": br.get(a.branch_id, ""), "mode": a.consultation_mode.replace("_", " "), "source": SOURCE_LABEL.get(a.source or "", a.source or ""),
               "total": a.total_amount_paise, "paid": a.paid_amount_paise or 0, "coupon": a.coupon_code or ""}


def _payments(ctx: ReportContext):
    f = ctx.f
    stmt = select(Payment).where(Payment.organization_id == ctx.org.id, Payment.created_at >= f.start, Payment.created_at < f.end)
    if f.branch_id:
        stmt = stmt.where(Payment.branch_id == f.branch_id)
    pays = ctx.db.scalars(stmt.order_by(Payment.created_at).limit(MAX_ROWS + 1)).all()
    appts = {a.id: a for a in ctx.db.scalars(select(Appointment).where(Appointment.id.in_({p.appointment_id for p in pays if p.appointment_id}))).all()} if pays else {}
    custs = ctx.names(Customer, "full_name")
    users = dict(ctx.db.execute(select(User.id, User.full_name).where(User.id.in_({p.verified_by_user_id for p in pays if p.verified_by_user_id}))).all()) if pays else {}
    utrs = dict(ctx.db.execute(select(PaymentSubmission.payment_id, PaymentSubmission.utr).where(PaymentSubmission.payment_id.in_([p.id for p in pays]),
                                                                                                 PaymentSubmission.is_superseded.is_(False))).all()) if pays else {}
    for p in pays:
        a = appts.get(p.appointment_id)
        if ctx.f.professional_id and (a is None or a.professional_id != ctx.f.professional_id):
            continue
        if ctx.f.service_id and (a is None or a.service_id != ctx.f.service_id):
            continue
        yield {"created": ctx.local(p.created_at), "reference": p.reference, "appointment": a.reference if a else "", "customer": custs.get(p.customer_id, ""),
               "method": METHOD_LABEL.get(p.method, p.method), "kind": p.kind, "status": p.status.replace("_", " "), "amount": p.amount_paise,
               "verified_amount": p.verified_amount_paise, "utr": utrs.get(p.id, ""), "verified_at": ctx.local(p.verified_at), "verified_by": users.get(p.verified_by_user_id, "")}


def _refunds(ctx: ReportContext):
    f = ctx.f
    rows = ctx.db.scalars(select(PaymentRefund).where(PaymentRefund.organization_id == ctx.org.id, PaymentRefund.created_at >= f.start, PaymentRefund.created_at < f.end)
                          .order_by(PaymentRefund.created_at)).all()
    pays = {p.id: p for p in ctx.db.scalars(select(Payment).where(Payment.id.in_({r.payment_id for r in rows}))).all()} if rows else {}
    custs = ctx.names(Customer, "full_name")
    for r in rows:
        p = pays.get(r.payment_id)
        yield {"requested": ctx.local(r.requested_at or r.created_at), "reference": r.reference, "payment": p.reference if p else "", "customer": custs.get(p.customer_id, "") if p else "",
               "status": r.status, "amount": r.amount_paise, "reason": r.reason or "", "method": r.refund_method or "", "refund_reference": r.refund_reference or "",
               "processed": ctx.local(r.processed_at)}


def _daily(ctx: ReportContext):
    dash = AnalyticsService(ctx.db, ctx.org).dashboard(ctx.f)
    for p in dash.series:
        yield {"date": p.date, "booked": p.booked, "cancelled": p.cancelled, "no_show": p.no_show, "receipts": p.revenue_paise, "refunds": p.refunds_paise,
               "net": p.revenue_paise - p.refunds_paise}


def _professionals(ctx: ReportContext):
    dash = AnalyticsService(ctx.db, ctx.org).dashboard(ctx.f)
    for b in dash.by_professional:
        attended = b.completed + b.no_show
        yield {"professional": b.label, "appointments": b.appointments, "completed": b.completed, "cancelled": b.cancelled, "no_show": b.no_show,
               "no_show_rate": (b.no_show / attended) if attended else None, "booked_hours": round(b.booked_minutes / 60, 2),
               "available_hours": round(b.available_minutes / 60, 2) if b.available_minutes is not None else None, "utilization": b.utilization, "receipts": b.revenue_paise}


def _services(ctx: ReportContext):
    dash = AnalyticsService(ctx.db, ctx.org).dashboard(ctx.f)
    for b in dash.by_service:
        yield {"service": b.label, "appointments": b.appointments, "completed": b.completed, "cancelled": b.cancelled, "no_show": b.no_show,
               "booked_hours": round(b.booked_minutes / 60, 2), "receipts": b.revenue_paise}


def _customers(ctx: ReportContext):
    appts = [a for a in ctx.appointments() if a.status not in NOT_BOOKED or a.status == A.NO_SHOW]
    by_cust: dict[int, list[Appointment]] = defaultdict(list)
    for a in appts:
        by_cust[a.customer_id].append(a)
    if not by_cust:
        return
    custs = {c.id: c for c in ctx.db.scalars(select(Customer).where(Customer.id.in_(by_cust))).all()}
    from sqlalchemy import func

    first = dict(ctx.db.execute(select(Appointment.customer_id, func.min(Appointment.start_at)).where(Appointment.customer_id.in_(by_cust),
                                                                                                    Appointment.status.not_in(list(NEVER_HAPPENED))).group_by(Appointment.customer_id)).all())
    paid = defaultdict(int)
    for cid, amount in ctx.db.execute(select(Payment.customer_id, Payment.verified_amount_paise).where(Payment.customer_id.in_(by_cust), Payment.status.in_(VERIFIED_LIKE))).all():
        paid[cid] += amount or 0
    for cid, rows in sorted(by_cust.items(), key=lambda kv: -len(kv[1])):
        c = custs.get(cid)
        if c is None:
            continue
        first_visit = ctx.local(first.get(cid))
        yield {"customer": c.full_name, "code": c.customer_code or "", "mobile": c.mobile or "", "email": c.email or "", "visits_in_range": len(rows),
               "no_shows_in_range": sum(1 for a in rows if a.status == A.NO_SHOW), "first_visit": first_visit.date() if first_visit else None,
               "new_in_range": "yes" if first_visit and ctx.f.from_date <= first_visit.date() <= ctx.f.to_date else "no",
               "last_visit": ctx.local(max(a.start_at for a in rows)).date(), "paid_all_time": paid.get(cid, 0)}


def _cancellations(ctx: ReportContext):
    svc, pro = ctx.names(Service), ctx.names(Professional, "display_name")
    custs = ctx.names(Customer, "full_name")
    appts = {a.id: a for a in ctx.appointments() if a.status == A.CANCELLED}
    if not appts:
        return
    rows = ctx.db.scalars(select(AppointmentCancellation).where(AppointmentCancellation.appointment_id.in_(appts))).all()
    for c in sorted(rows, key=lambda r: r.cancelled_at):
        a = appts[c.appointment_id]
        yield {"appointment_date": ctx.local(a.start_at).date(), "reference": a.reference, "customer": custs.get(a.customer_id, ""), "service": svc.get(a.service_id, ""),
               "professional": pro.get(a.professional_id, ""), "cancelled_at": ctx.local(c.cancelled_at), "cancelled_by": c.cancelled_by_role or "",
               "hours_notice": round((a.start_at - c.cancelled_at).total_seconds() / 3600, 1), "reason": c.reason or "", "refund_eligible": c.refund_eligible_paise}


def _tax(ctx: ReportContext):
    months: dict[str, dict[str, int]] = defaultdict(lambda: {"appointments": 0, "subtotal": 0, "discount": 0, "tax": 0, "total": 0})
    for a in ctx.appointments():
        if a.status in NOT_BOOKED:
            continue
        m = months[ctx.local(a.start_at).strftime("%Y-%m")]
        m["appointments"] += 1
        m["subtotal"] += a.subtotal_paise or 0
        m["discount"] += a.discount_paise or 0
        m["tax"] += a.tax_paise or 0
        m["total"] += a.total_amount_paise or 0
    for month, v in sorted(months.items()):
        yield {"month": month, **v}


def _coupons(ctx: ReportContext):
    usage: dict[str, dict[str, int]] = defaultdict(lambda: {"bookings": 0, "discount": 0, "booked_value": 0})
    for a in ctx.appointments():
        if a.coupon_code and a.status not in NOT_BOOKED:
            u = usage[a.coupon_code]
            u["bookings"] += 1
            u["discount"] += int(((a.pricing_snapshot or {}).get("coupon_discount_paise")) or 0)
            u["booked_value"] += a.total_amount_paise or 0
    for code, v in sorted(usage.items(), key=lambda kv: -kv[1]["bookings"]):
        yield {"coupon": code, **v}


M = "money"
REPORTS: dict[str, ReportDef] = {r.key: r for r in [
    ReportDef("appointments", "Appointments", "Every appointment starting in the range, with customer, service, professional and amounts.",
              [Column("date", "Date", "date"), Column("time", "Time", "time"), Column("reference", "Reference"), Column("status", "Status"), Column("customer", "Customer"),
               Column("mobile", "Mobile"), Column("service", "Service"), Column("professional", "Professional"), Column("branch", "Branch"), Column("mode", "Mode"),
               Column("source", "Source"), Column("total", "Total", M), Column("paid", "Paid", M), Column("coupon", "Coupon")],
              _appointments, ("reports:read", "appointments:read"), ("total", "paid"), True),
    ReportDef("payments", "Payments", "Payment requests and receipts created in the range, with UTR, verification and verifier.",
              [Column("created", "Created", "datetime"), Column("reference", "Payment"), Column("appointment", "Appointment"), Column("customer", "Customer"),
               Column("method", "Method"), Column("kind", "Kind"), Column("status", "Status"), Column("amount", "Amount due", M), Column("verified_amount", "Verified", M),
               Column("utr", "UTR"), Column("verified_at", "Verified at", "datetime"), Column("verified_by", "Verified by")],
              _payments, ("reports:read", "payments:read"), ("amount", "verified_amount"), True),
    ReportDef("refunds", "Refunds", "Refund requests in the range with status, transfer reference and dates.",
              [Column("requested", "Requested", "datetime"), Column("reference", "Refund"), Column("payment", "Payment"), Column("customer", "Customer"), Column("status", "Status"),
               Column("amount", "Amount", M), Column("reason", "Reason"), Column("method", "Sent via"), Column("refund_reference", "Transfer reference"), Column("processed", "Sent at", "datetime")],
              _refunds, ("reports:read", "payments:read"), ("amount",), True),
    ReportDef("daily_summary", "Daily summary", "Per day: appointments booked, cancelled and no-shows; payments verified, refunds sent and net received.",
              [Column("date", "Date", "date"), Column("booked", "Booked", "int"), Column("cancelled", "Cancelled", "int"), Column("no_show", "No-shows", "int"),
               Column("receipts", "Verified receipts", M), Column("refunds", "Refunds sent", M), Column("net", "Net received", M)],
              _daily, ("reports:read",), ("booked", "cancelled", "no_show", "receipts", "refunds", "net")),
    ReportDef("professionals", "Professional performance", "Appointments, no-shows, booked versus scheduled hours (utilization) and verified receipts per professional.",
              [Column("professional", "Professional"), Column("appointments", "Appointments", "int"), Column("completed", "Completed", "int"), Column("cancelled", "Cancelled", "int"),
               Column("no_show", "No-shows", "int"), Column("no_show_rate", "No-show rate", "percent"), Column("booked_hours", "Booked hours", "int"),
               Column("available_hours", "Scheduled hours", "int"), Column("utilization", "Utilization", "percent"), Column("receipts", "Verified receipts", M)],
              _professionals, ("reports:read",), ("appointments", "completed", "cancelled", "no_show", "receipts")),
    ReportDef("services", "Service performance", "Bookings, outcomes, hours and verified receipts per service.",
              [Column("service", "Service"), Column("appointments", "Appointments", "int"), Column("completed", "Completed", "int"), Column("cancelled", "Cancelled", "int"),
               Column("no_show", "No-shows", "int"), Column("booked_hours", "Booked hours", "int"), Column("receipts", "Verified receipts", M)],
              _services, ("reports:read",), ("appointments", "completed", "cancelled", "no_show", "receipts")),
    ReportDef("customers", "Customers seen", "Customers with appointments in the range: visits, no-shows, first and last visit, and total paid.",
              [Column("customer", "Customer"), Column("code", "Code"), Column("mobile", "Mobile"), Column("email", "Email"), Column("visits_in_range", "Visits", "int"),
               Column("no_shows_in_range", "No-shows", "int"), Column("first_visit", "First visit", "date"), Column("new_in_range", "New"), Column("last_visit", "Last visit", "date"),
               Column("paid_all_time", "Paid (all time)", M)],
              _customers, ("reports:read", "customers:read"), ("visits_in_range", "no_shows_in_range", "paid_all_time"), True),
    ReportDef("cancellations", "Cancellations", "Cancelled appointments with who cancelled, how much notice was given and the refund the policy allowed.",
              [Column("appointment_date", "Appointment date", "date"), Column("reference", "Reference"), Column("customer", "Customer"), Column("service", "Service"),
               Column("professional", "Professional"), Column("cancelled_at", "Cancelled at", "datetime"), Column("cancelled_by", "By"), Column("hours_notice", "Hours notice", "int"),
               Column("reason", "Reason"), Column("refund_eligible", "Refund eligible", M)],
              _cancellations, ("reports:read", "appointments:read"), ("refund_eligible",), True),
    ReportDef("tax_summary", "Billing summary by month", "Subtotal, discounts, tax and totals of booked appointments per month, as priced at booking. "
              "A working summary for your accountant, not a tax filing.",
              [Column("month", "Month"), Column("appointments", "Appointments", "int"), Column("subtotal", "Subtotal", M), Column("discount", "Discount", M),
               Column("tax", "Tax", M), Column("total", "Total", M)],
              _tax, ("reports:read",), ("appointments", "subtotal", "discount", "tax", "total")),
    ReportDef("coupons", "Coupon usage", "Bookings and discount given per coupon code.",
              [Column("coupon", "Coupon"), Column("bookings", "Bookings", "int"), Column("discount", "Discount given", M), Column("booked_value", "Booked value", M)],
              _coupons, ("reports:read",), ("bookings", "discount", "booked_value")),
]}


def get_report(key: str, has: Callable[[str], bool]) -> ReportDef:
    report = REPORTS.get(key)
    if report is None:
        raise NotFoundError("Report not found.")
    missing = [p for p in report.permissions if not has(p)]
    if missing:
        raise PermissionDenied(f"Missing permission: {', '.join(missing)}", code="permission_denied")
    return report


def run(report: ReportDef, ctx: ReportContext) -> tuple[list[dict[str, Any]], bool]:
    rows = []
    for row in report.rows(ctx):
        rows.append(row)
        if len(rows) > MAX_ROWS:
            return rows[:MAX_ROWS], True
    return rows, False


def totals(report: ReportDef, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {k: sum((r.get(k) or 0) for r in rows) for k in report.totals}


# ------------------------------------------------------------------ output
def _safe(text: str) -> str:
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def display(value: Any, kind: str) -> Any:
    """CSV/preview value: rupees for money, ISO for dates, ratio as percent string."""
    if value is None or value == "":
        return ""
    if kind == "money":
        return f"{value / 100:.2f}"
    if kind == "percent":
        return f"{value * 100:.1f}%"
    if kind == "datetime":
        return value.strftime("%Y-%m-%d %H:%M")
    if kind == "date":
        return value.isoformat()
    if kind == "text":
        return _safe(str(value))
    return value


def to_csv(report: ReportDef, rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.label + (" (INR)" if c.type == "money" else "") for c in report.columns])
    for r in rows:
        w.writerow([display(r.get(c.key), c.type) for c in report.columns])
    return "﻿" + buf.getvalue()


def to_xlsx(report: ReportDef, rows: list[dict[str, Any]], *, owner: str, period: str, filters_label: str, truncated: bool, tz=None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = report.title[:31]
    header_fill = PatternFill("solid", fgColor="E7F2EF")
    ws.append([c.label + (" (₹)" if c.type == "money" else "") for c in report.columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    formats = {"money": "#,##0.00", "percent": "0.0%", "date": "dd-mmm-yyyy", "datetime": "dd-mmm-yyyy hh:mm", "int": "#,##0.##"}
    for r in rows:
        values = []
        for c in report.columns:
            v = r.get(c.key)
            if v is None or v == "":
                values.append(None)
            elif c.type == "money":
                values.append(v / 100)
            elif c.type == "datetime":
                values.append(v.replace(tzinfo=None))  # already in the clinic's time zone; Excel has no zones
            else:
                values.append(v if c.type != "text" else str(v))
        ws.append(values)
        row_idx = ws.max_row
        for i, c in enumerate(report.columns, start=1):
            cell = ws.cell(row=row_idx, column=i)
            if c.type == "text" and cell.value is not None:
                cell.data_type = "s"  # never let "=..." become a formula
            elif c.type in formats:
                cell.number_format = formats[c.type]
    if report.totals and rows:
        ws.append([("Total" if i == 0 else None) for i in range(len(report.columns))])
        tr = ws.max_row
        sums = totals(report, rows)
        for i, c in enumerate(report.columns, start=1):
            if c.key in sums:
                cell = ws.cell(row=tr, column=i, value=sums[c.key] / 100 if c.type == "money" else sums[c.key])
                cell.number_format = formats.get(c.type, "General")
            ws.cell(row=tr, column=i).font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(report.columns))}{max(1, len(rows) + 1)}"
    for i, c in enumerate(report.columns, start=1):
        longest = max([len(str(c.label))] + [len(str(display(r.get(c.key), c.type))) for r in rows[:500]])
        ws.column_dimensions[get_column_letter(i)].width = min(48, max(10, longest + 2))
    about = wb.create_sheet("About")
    for line in [("Report", report.title), ("Organization", owner), ("Period", period),
                 ("Filters", filters_label or "None"), ("Rows", len(rows)), ("Generated", utcnow().astimezone(tz or UTC).strftime("%Y-%m-%d %H:%M")),
                 ("Definition", report.description), ("Note", "Rows truncated at 50,000." if truncated else "Complete.")]:
        about.append(list(line))
        about.cell(row=about.max_row, column=2).data_type = "s" if isinstance(line[1], str) else about.cell(row=about.max_row, column=2).data_type
    about.column_dimensions["A"].width = 14
    about.column_dimensions["B"].width = 90
    for cell in about["A"]:
        cell.font = Font(bold=True)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def preview_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value
