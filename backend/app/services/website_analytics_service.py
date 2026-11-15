"""Website traffic (cookie-free daily counters) combined with real holds and bookings into a simple funnel."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import Appointment, BookingHold, Organization
from app.models.analytics import WebsiteDailyStat

METRICS = ("page_view", "book_click", "booking_view")
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,79}$")


def clean_key(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if _TOKEN.fullmatch(v) else ("home" if not v else "other")


def clean_source(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v[:64] if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", v) else "direct"


class WebsiteAnalyticsService:
    def __init__(self, db: Session, org: Organization):
        self.db = db
        self.org = org
        self.tz = ZoneInfo(org.timezone or "Asia/Kolkata")

    def record(self, metric: str, key: str | None, source: str | None) -> None:
        if metric not in METRICS:
            return
        values = {"organization_id": self.org.id, "day": self.today(), "metric": metric, "key": clean_key(key), "source": clean_source(source), "count": 1}
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt = insert(WebsiteDailyStat).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["organization_id", "day", "metric", "key", "source"], set_={"count": WebsiteDailyStat.count + 1})
        self.db.execute(stmt)

    def today(self) -> date:
        return utcnow().astimezone(self.tz).date()

    def report(self, start: date, end: date) -> dict[str, Any]:
        rows = self.db.execute(select(WebsiteDailyStat.day, WebsiteDailyStat.metric, WebsiteDailyStat.key, WebsiteDailyStat.source, WebsiteDailyStat.count)
                               .where(WebsiteDailyStat.organization_id == self.org.id, WebsiteDailyStat.day >= start, WebsiteDailyStat.day <= end)).all()
        totals: Counter[str] = Counter()
        daily: dict[date, Counter[str]] = defaultdict(Counter)
        pages: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        for day, metric, key, source, count in rows:
            totals[metric] += count
            daily[day][metric] += count
            if metric == "page_view":
                pages[key] += count
                sources[source] += count
        lo = datetime.combine(start, time.min, self.tz)
        hi = datetime.combine(end + timedelta(days=1), time.min, self.tz)
        holds = self.db.scalar(select(func.count()).select_from(BookingHold).where(BookingHold.organization_id == self.org.id, BookingHold.created_at >= lo, BookingHold.created_at < hi)) or 0
        online = self.db.execute(select(Appointment.created_at, Appointment.metadata_).where(
            Appointment.organization_id == self.org.id, Appointment.source == "online", Appointment.created_at >= lo, Appointment.created_at < hi)).all()
        by_source: Counter[str] = Counter()
        by_campaign: Counter[str] = Counter()
        bookings_daily: Counter[date] = Counter()
        from_site = 0
        for created, meta in online:
            attr = (meta or {}).get("attribution") or {}
            from_site += attr.get("entry") in ("website", "embed")
            by_source[attr.get("utm_source") or ("embed" if attr.get("entry") == "embed" else "direct")] += 1
            if attr.get("utm_campaign"):
                by_campaign[attr["utm_campaign"]] += 1
            bookings_daily[created.astimezone(self.tz).date()] += 1
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        views = totals["page_view"]
        return {
            "from_date": start, "to_date": end,
            # Conversion uses only bookings made through the website or its embed (not API or older bookings).
            "totals": {"page_views": views, "book_clicks": totals["book_click"], "booking_views": totals["booking_view"], "holds": holds, "bookings": len(online),
                       "website_bookings": from_site, "conversion_percent": round(100 * from_site / views, 1) if views else None},
            "daily": [{"date": d, "page_views": daily[d]["page_view"], "book_clicks": daily[d]["book_click"], "booking_views": daily[d]["booking_view"],
                       "bookings": bookings_daily[d]} for d in days],
            "top_pages": [{"key": k, "views": v} for k, v in pages.most_common(10)],
            "traffic_sources": [{"source": k, "views": v} for k, v in sources.most_common(10)],
            "booking_sources": [{"source": k, "bookings": v} for k, v in by_source.most_common(10)],
            "campaigns": [{"campaign": k, "bookings": v} for k, v in by_campaign.most_common(10)],
        }
