from __future__ import annotations

from datetime import date

from app.schemas.common import APIModel


class Metric(APIModel):
    value: float
    previous: float | None = None


class DayPoint(APIModel):
    date: date
    booked: int  # confirmed, checked in, in progress, completed, pending payment/verification
    cancelled: int
    no_show: int
    revenue_paise: int  # verified receipts that day
    refunds_paise: int


class Breakdown(APIModel):
    key: str
    label: str
    appointments: int
    completed: int = 0
    cancelled: int = 0
    no_show: int = 0
    revenue_paise: int = 0
    booked_minutes: int = 0
    available_minutes: int | None = None
    utilization: float | None = None


class HeatCell(APIModel):
    weekday: int  # 0 = Monday
    hour: int
    appointments: int


class AgendaCounts(APIModel):
    total: int
    upcoming: int
    checked_in: int
    completed: int
    no_show: int
    awaiting_payment: int


class Dashboard(APIModel):
    from_date: date
    to_date: date
    timezone: str
    scope: str  # organization | professional
    kpis: dict[str, Metric]
    series: list[DayPoint]
    by_service: list[Breakdown]
    by_professional: list[Breakdown]
    by_branch: list[Breakdown]
    by_source: list[Breakdown]
    payment_methods: list[Breakdown]
    heatmap: list[HeatCell]
    today: AgendaCounts
    attention: dict[str, int]
