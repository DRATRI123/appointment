"""Organization analytics. Definitions (shown in the UI too):

* Appointments: appointments whose start time falls in the range (clinic time zone), any status.
* Booked: not cancelled, expired or no-show. Completion rate = completed / (completed + no-show).
* Cancellation rate = cancelled / all appointments in range. No-show rate = no-show / (completed + no-show).
* Revenue received: payments verified by staff in the range (by verification time) minus refunds sent in the range.
  Never includes unverified UTR submissions. Booked value is reported separately.
* Utilization: booked minutes / scheduled working minutes of the professional in the range (capped at 92 days).

Grouping happens in Python on narrow row sets, so results are identical on SQLite and PostgreSQL.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import AppointmentStatus as A
from app.core.enums import PaymentStatus
from app.core.exceptions import ValidationFailed
from app.core.time import utcnow
from app.models import Appointment, Branch, Organization, Payment, PaymentRefund, Professional, ProfessionalBranch, Service
from app.schemas.analytics import AgendaCounts, Breakdown, Dashboard, DayPoint, HeatCell, Metric

NOT_BOOKED = {A.CANCELLED, A.EXPIRED, A.NO_SHOW, A.DRAFT, A.RESCHEDULED}
NEVER_HAPPENED = {A.CANCELLED, A.EXPIRED, A.DRAFT, A.RESCHEDULED}  # a no-show still made the customer a customer
VERIFIED_LIKE = (PaymentStatus.VERIFIED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED)
SOURCE_LABEL = {"online": "Online booking", "reception": "Reception", "walk_in": "Walk-in", "professional": "Professional", "api": "API", "recurring": "Recurring series"}
METHOD_LABEL = {"upi_qr": "UPI QR", "cash": "Cash", "bank_transfer": "Bank transfer", "pay_at_clinic": "Pay at clinic", "free": "Free"}
MAX_DAYS = 366


class Filters:
    def __init__(self, org: Organization, from_date: date, to_date: date, *, branch_id: int | None = None, professional_id: int | None = None, service_id: int | None = None):
        if to_date < from_date:
            raise ValidationFailed("The end date is before the start date.", code="invalid_range")
        if (to_date - from_date).days >= MAX_DAYS:
            raise ValidationFailed("Choose a range of at most one year.", code="range_too_long")
        self.tz = ZoneInfo(org.timezone or "Asia/Kolkata")
        self.from_date, self.to_date = from_date, to_date
        self.start = datetime.combine(from_date, time.min, tzinfo=self.tz)
        self.end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=self.tz)
        self.branch_id, self.professional_id, self.service_id = branch_id, professional_id, service_id

    def previous(self, org: Organization) -> Filters:
        days = (self.to_date - self.from_date).days + 1
        return Filters(org, self.from_date - timedelta(days=days), self.from_date - timedelta(days=1), branch_id=self.branch_id,
                       professional_id=self.professional_id, service_id=self.service_id)

    def local_date(self, dt: datetime) -> date:
        return dt.astimezone(self.tz).date()

    def days(self) -> list[date]:
        return [self.from_date + timedelta(days=i) for i in range((self.to_date - self.from_date).days + 1)]


class AnalyticsService:
    def __init__(self, db: Session, org: Organization):
        self.db = db
        self.org = org

    # ------------------------------------------------------------ queries
    def _appointments(self, f: Filters):
        stmt = select(Appointment.id, Appointment.start_at, Appointment.end_at, Appointment.status, Appointment.service_id, Appointment.professional_id,
                      Appointment.branch_id, Appointment.customer_id, Appointment.source, Appointment.total_amount_paise).where(
            Appointment.organization_id == self.org.id, Appointment.start_at >= f.start, Appointment.start_at < f.end)
        if f.branch_id:
            stmt = stmt.where(Appointment.branch_id == f.branch_id)
        if f.professional_id:
            stmt = stmt.where(Appointment.professional_id == f.professional_id)
        if f.service_id:
            stmt = stmt.where(Appointment.service_id == f.service_id)
        return self.db.execute(stmt).all()

    def _payments(self, f: Filters):
        stmt = select(Payment.id, Payment.verified_at, Payment.verified_amount_paise, Payment.method, Appointment.service_id, Appointment.professional_id, Payment.branch_id).join(
            Appointment, Appointment.id == Payment.appointment_id, isouter=True).where(
            Payment.organization_id == self.org.id, Payment.status.in_(VERIFIED_LIKE), Payment.verified_at >= f.start, Payment.verified_at < f.end)
        if f.branch_id:
            stmt = stmt.where(Payment.branch_id == f.branch_id)
        if f.professional_id:
            stmt = stmt.where(Appointment.professional_id == f.professional_id)
        if f.service_id:
            stmt = stmt.where(Appointment.service_id == f.service_id)
        return self.db.execute(stmt).all()

    def _refunds(self, f: Filters):
        stmt = select(PaymentRefund.processed_at, PaymentRefund.amount_paise).join(Payment, Payment.id == PaymentRefund.payment_id).join(
            Appointment, Appointment.id == Payment.appointment_id, isouter=True).where(
            PaymentRefund.organization_id == self.org.id, PaymentRefund.status == "processed", PaymentRefund.processed_at >= f.start, PaymentRefund.processed_at < f.end)
        if f.branch_id:
            stmt = stmt.where(Payment.branch_id == f.branch_id)
        if f.professional_id:
            stmt = stmt.where(Appointment.professional_id == f.professional_id)
        if f.service_id:
            stmt = stmt.where(Appointment.service_id == f.service_id)
        return self.db.execute(stmt).all()

    # ------------------------------------------------------------ kpis
    def _kpis(self, f: Filters) -> dict[str, float]:
        rows = self._appointments(f)
        statuses = Counter(r.status for r in rows)
        total = len(rows)
        completed, no_show, cancelled = statuses[A.COMPLETED], statuses[A.NO_SHOW], statuses[A.CANCELLED]
        booked = [r for r in rows if r.status not in NOT_BOOKED]
        revenue = sum(p.verified_amount_paise or 0 for p in self._payments(f))
        refunds = sum(r.amount_paise for r in self._refunds(f))
        customers = {r.customer_id for r in rows if r.status not in NOT_BOOKED or r.status == A.NO_SHOW}
        first_visit = dict(self.db.execute(select(Appointment.customer_id, func.min(Appointment.start_at)).where(
            Appointment.organization_id == self.org.id, Appointment.customer_id.in_(customers),
            Appointment.status.not_in(list(NEVER_HAPPENED))).group_by(Appointment.customer_id)).all()) if customers else {}
        new_customers = sum(1 for c in customers if c in first_visit and first_visit[c] is not None and _aware(first_visit[c]) >= f.start)
        return {
            "appointments": total, "booked": len(booked), "completed": completed, "cancelled": cancelled, "no_show": no_show,
            "cancellation_rate": round(cancelled / total, 4) if total else 0.0,
            "no_show_rate": round(no_show / (completed + no_show), 4) if (completed + no_show) else 0.0,
            "revenue_paise": revenue - refunds, "gross_receipts_paise": revenue, "refunds_paise": refunds,
            "booked_value_paise": sum(r.total_amount_paise or 0 for r in booked),
            "average_value_paise": round(sum(r.total_amount_paise or 0 for r in booked) / len(booked)) if booked else 0,
            "customers": len(customers), "new_customers": new_customers, "returning_customers": len(customers) - new_customers,
        }

    # ------------------------------------------------------------ utilization
    def available_minutes(self, f: Filters, pro: Professional, branch_ids: list[int]) -> int | None:
        if (f.to_date - f.from_date).days > 92:
            return None
        from app.services.availability_service import AvailabilityService, branch_tz

        avail = AvailabilityService(self.db, self.org)
        total = 0
        for bid in branch_ids:
            branch = self.db.get(Branch, bid)
            if branch is None or (f.branch_id and f.branch_id != bid):
                continue
            tz = branch_tz(self.org, branch)
            for day in f.days():
                for w in avail.windows_for(pro, branch, day, tz):
                    total += int((w.end - w.start).total_seconds() // 60)
        return total

    # ------------------------------------------------------------ dashboard
    def dashboard(self, f: Filters, *, scope: str = "organization") -> Dashboard:
        rows = self._appointments(f)
        payments = self._payments(f)
        refunds = self._refunds(f)
        now_kpis = self._kpis(f)
        prev_kpis = self._kpis(f.previous(self.org))
        kpis = {k: Metric(value=v, previous=prev_kpis.get(k)) for k, v in now_kpis.items()}

        series = {d: {"booked": 0, "cancelled": 0, "no_show": 0, "revenue_paise": 0, "refunds_paise": 0} for d in f.days()}
        for r in rows:
            d = f.local_date(_aware(r.start_at))
            if d not in series:
                continue
            key = "cancelled" if r.status in (A.CANCELLED, A.EXPIRED) else "no_show" if r.status == A.NO_SHOW else "booked" if r.status not in NOT_BOOKED else None
            if key:
                series[d][key] += 1
        for p in payments:
            d = f.local_date(_aware(p.verified_at))
            if d in series:
                series[d]["revenue_paise"] += p.verified_amount_paise or 0
        for rf in refunds:
            d = f.local_date(_aware(rf.processed_at))
            if d in series:
                series[d]["refunds_paise"] += rf.amount_paise

        def breakdown(key_fn, label_fn, revenue_key) -> list[Breakdown]:
            agg: dict[str, dict] = defaultdict(lambda: {"appointments": 0, "completed": 0, "cancelled": 0, "no_show": 0, "booked_minutes": 0, "revenue_paise": 0})
            for r in rows:
                k = key_fn(r)
                a = agg[k]
                a["appointments"] += 1
                a["completed"] += r.status == A.COMPLETED
                a["cancelled"] += r.status == A.CANCELLED
                a["no_show"] += r.status == A.NO_SHOW
                if r.status not in NOT_BOOKED:
                    a["booked_minutes"] += int((_aware(r.end_at) - _aware(r.start_at)).total_seconds() // 60)
            if revenue_key:
                for p in payments:
                    k = revenue_key(p)
                    if k is not None:
                        agg[k]["revenue_paise"] += p.verified_amount_paise or 0
            out = [Breakdown(key=str(k), label=label_fn(k), **v) for k, v in agg.items() if k is not None]
            return sorted(out, key=lambda b: (-b.appointments, -b.revenue_paise, b.label))

        names = self._names()
        by_pro = breakdown(lambda r: r.professional_id, lambda k: names["pro"].get(k, "—"), lambda p: p.professional_id)
        if (f.to_date - f.from_date).days <= 92:
            pro_branches: dict[int, list[int]] = defaultdict(list)
            for pid, bid in self.db.execute(select(ProfessionalBranch.professional_id, ProfessionalBranch.branch_id).join(
                    Professional, Professional.id == ProfessionalBranch.professional_id).where(Professional.organization_id == self.org.id)).all():
                pro_branches[pid].append(bid)
            for b in by_pro:
                pro = self.db.get(Professional, int(b.key))
                if pro is not None:
                    b.available_minutes = self.available_minutes(f, pro, pro_branches.get(pro.id, []))
                    b.utilization = round(min(1.0, b.booked_minutes / b.available_minutes), 4) if b.available_minutes else None
        for b in by_pro:
            b.key = names["pro_public"].get(int(b.key), b.key)

        methods: dict[str, dict] = defaultdict(lambda: {"appointments": 0, "revenue_paise": 0})
        for p in payments:
            methods[p.method]["appointments"] += 1
            methods[p.method]["revenue_paise"] += p.verified_amount_paise or 0
        heat = Counter()
        for r in rows:
            if r.status not in NOT_BOOKED or r.status == A.NO_SHOW:
                local = _aware(r.start_at).astimezone(f.tz)
                heat[(local.weekday(), local.hour)] += 1

        by_service = breakdown(lambda r: r.service_id, lambda k: names["service"].get(k, "—"), lambda p: p.service_id)
        for b in by_service:
            b.key = names["service_public"].get(int(b.key), b.key)
        by_branch = breakdown(lambda r: r.branch_id, lambda k: names["branch"].get(k, "—"), lambda p: p.branch_id)
        for b in by_branch:
            b.key = names["branch_public"].get(int(b.key), b.key)

        return Dashboard(
            from_date=f.from_date, to_date=f.to_date, timezone=str(f.tz), scope=scope, kpis=kpis,
            series=[DayPoint(date=d, **v) for d, v in series.items()], by_service=by_service, by_professional=by_pro, by_branch=by_branch,
            by_source=breakdown(lambda r: r.source or "online", lambda k: SOURCE_LABEL.get(k, k), None),
            payment_methods=sorted([Breakdown(key=k, label=METHOD_LABEL.get(k, k), **v) for k, v in methods.items()], key=lambda b: -b.revenue_paise),
            heatmap=[HeatCell(weekday=w, hour=h, appointments=n) for (w, h), n in sorted(heat.items())],
            today=self.today(f), attention=self.attention(f) if scope == "organization" else {},
        )

    def today(self, f: Filters) -> AgendaCounts:
        today = utcnow().astimezone(f.tz).date()
        start = datetime.combine(today, time.min, tzinfo=f.tz)
        stmt = select(Appointment.status, Appointment.start_at).where(Appointment.organization_id == self.org.id, Appointment.start_at >= start,
                                                                       Appointment.start_at < start + timedelta(days=1))
        if f.branch_id:
            stmt = stmt.where(Appointment.branch_id == f.branch_id)
        if f.professional_id:
            stmt = stmt.where(Appointment.professional_id == f.professional_id)
        rows = self.db.execute(stmt).all()
        now = utcnow()
        live = [r for r in rows if r.status not in (A.CANCELLED, A.EXPIRED, A.DRAFT)]
        return AgendaCounts(total=len(live), upcoming=sum(1 for r in live if r.status == A.CONFIRMED and _aware(r.start_at) > now),
                            checked_in=sum(1 for r in live if r.status in (A.CHECKED_IN, A.IN_PROGRESS)), completed=sum(1 for r in live if r.status == A.COMPLETED),
                            no_show=sum(1 for r in live if r.status == A.NO_SHOW), awaiting_payment=sum(1 for r in live if r.status in (A.PENDING_PAYMENT, A.PENDING_VERIFICATION)))

    def attention(self, f: Filters) -> dict[str, int]:
        from app.models import AppointmentExternalEvent, BankTransaction, Notification

        org = self.org.id

        def count(stmt) -> int:
            return int(self.db.scalar(stmt) or 0)

        return {
            "payments_to_verify": count(select(func.count()).select_from(Payment).where(Payment.organization_id == org, Payment.status.in_([PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW]))),
            "refunds_to_approve": count(select(func.count()).select_from(PaymentRefund).where(PaymentRefund.organization_id == org, PaymentRefund.status.in_(["requested", "approved"]))),
            "unmatched_bank_credits": count(select(func.count()).select_from(BankTransaction).where(BankTransaction.organization_id == org, BankTransaction.direction == "credit",
                                                                                                   BankTransaction.match_status.in_(["unmatched", "suggested"]))),
            "failed_notifications": count(select(func.count()).select_from(Notification).where(Notification.organization_id == org, Notification.status == "failed")),
            "calendar_sync_problems": count(select(func.count()).select_from(AppointmentExternalEvent).where(AppointmentExternalEvent.organization_id == org,
                                                                                                           AppointmentExternalEvent.status == "failed")),
        }

    def _names(self) -> dict[str, dict]:
        org = self.org.id
        pros = self.db.execute(select(Professional.id, Professional.display_name, Professional.public_id).where(Professional.organization_id == org)).all()
        svcs = self.db.execute(select(Service.id, Service.name, Service.public_id).where(Service.organization_id == org)).all()
        brs = self.db.execute(select(Branch.id, Branch.name, Branch.public_id).where(Branch.organization_id == org)).all()
        return {"pro": {i: n for i, n, _ in pros}, "pro_public": {i: p for i, _, p in pros}, "service": {i: n for i, n, _ in svcs},
                "service_public": {i: p for i, _, p in svcs}, "branch": {i: n for i, n, _ in brs}, "branch_public": {i: p for i, _, p in brs}}


def _aware(dt: datetime) -> datetime:
    from datetime import UTC

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

