"""Schedules, exceptions, holidays, leaves and availability (tenant routes)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.models import Branch, Professional
from app.schemas.common import Message
from app.schemas.scheduling import (
    AvailabilitySummary,
    DayAvailability,
    ExceptionCreate,
    ExceptionRead,
    HolidayCreate,
    HolidayRead,
    LeaveCreate,
    LeaveRead,
    LeaveUpdate,
    ScheduleRead,
    ScheduleSet,
)
from app.services.availability_service import AvailabilityService
from app.services.catalog_service import CatalogService, ids_to_public
from app.services.schedule_service import ScheduleService

router = APIRouter(tags=["scheduling"])
ReadSched = Annotated[TenantContext, Depends(require_permission("professionals:read"))]
WriteSched = Annotated[TenantContext, Depends(require_permission("professionals:schedule"))]


def _schedule_read(db, rows) -> list[ScheduleRead]:
    pros = ids_to_public(db, Professional, {r.professional_id for r in rows})
    branches = ids_to_public(db, Branch, {r.branch_id for r in rows})
    return [
        ScheduleRead(id=r.id, professional_id=pros[r.professional_id], branch_id=branches[r.branch_id], weekday=r.weekday, start_time=r.start_time,
                     end_time=r.end_time, slot_minutes=r.slot_minutes, capacity=r.capacity, consultation_mode=r.consultation_mode,
                     valid_from=r.valid_from, valid_to=r.valid_to, is_active=r.is_active)
        for r in rows
    ]


def _exception_read(db, rows) -> list[ExceptionRead]:
    pros = ids_to_public(db, Professional, {r.professional_id for r in rows})
    branches = ids_to_public(db, Branch, {r.branch_id for r in rows if r.branch_id})
    return [
        ExceptionRead(id=r.id, professional_id=pros[r.professional_id], branch_id=branches.get(r.branch_id) if r.branch_id else None, date=r.date,
                      is_available=r.is_available, start_time=r.start_time, end_time=r.end_time, capacity=r.capacity, reason=r.reason)
        for r in rows
    ]


def _holiday_read(db, rows) -> list[HolidayRead]:
    branches = ids_to_public(db, Branch, {r.branch_id for r in rows if r.branch_id})
    return [HolidayRead(id=r.id, branch_id=branches.get(r.branch_id) if r.branch_id else None, date=r.date, name=r.name, is_recurring_yearly=r.is_recurring_yearly) for r in rows]


def _leave_read(db, rows) -> list[LeaveRead]:
    pros = ids_to_public(db, Professional, {r.professional_id for r in rows})
    branches = ids_to_public(db, Branch, {r.branch_id for r in rows if r.branch_id})
    return [
        LeaveRead(id=r.public_id, professional_id=pros[r.professional_id], branch_id=branches.get(r.branch_id) if r.branch_id else None, leave_type=r.leave_type,
                  start_at=r.start_at, end_at=r.end_at, reason=r.reason, status=r.status)
        for r in rows
    ]


@router.get("/schedules", response_model=list[ScheduleRead])
def list_schedules(db: DB, ctx: ReadSched, meta: Meta, professional_id: str | None = None, branch_id: str | None = None):
    return _schedule_read(db, ScheduleService(db, ctx.organization, ctx.user, meta).list_schedules(professional_id, branch_id))


@router.put("/schedules", response_model=list[ScheduleRead], summary="Replace the weekly schedule for a professional at a branch")
def set_schedule(payload: ScheduleSet, db: DB, ctx: WriteSched, meta: Meta):
    return _schedule_read(db, ScheduleService(db, ctx.organization, ctx.user, meta).set_schedule(payload))


@router.get("/schedules/exceptions", response_model=list[ExceptionRead])
def list_exceptions(db: DB, ctx: ReadSched, meta: Meta, professional_id: str | None = None, from_date: date | None = None, to_date: date | None = None):
    return _exception_read(db, ScheduleService(db, ctx.organization, ctx.user, meta).list_exceptions(professional_id, from_date, to_date))


@router.post("/schedules/exceptions", response_model=ExceptionRead, status_code=status.HTTP_201_CREATED)
def add_exception(payload: ExceptionCreate, db: DB, ctx: WriteSched, meta: Meta):
    return _exception_read(db, [ScheduleService(db, ctx.organization, ctx.user, meta).add_exception(payload)])[0]


@router.delete("/schedules/exceptions/{exception_id}", response_model=Message)
def delete_exception(exception_id: int, db: DB, ctx: WriteSched, meta: Meta):
    ScheduleService(db, ctx.organization, ctx.user, meta).delete_exception(exception_id)
    return Message(detail="Exception removed.")


@router.get("/schedules/holidays", response_model=list[HolidayRead])
def list_holidays(db: DB, ctx: ReadSched, meta: Meta, from_date: date | None = None, to_date: date | None = None):
    return _holiday_read(db, ScheduleService(db, ctx.organization, ctx.user, meta).list_holidays(from_date, to_date))


@router.post("/schedules/holidays", response_model=HolidayRead, status_code=status.HTTP_201_CREATED)
def add_holiday(payload: HolidayCreate, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("branches:write"))], meta: Meta):
    return _holiday_read(db, [ScheduleService(db, ctx.organization, ctx.user, meta).add_holiday(payload)])[0]


@router.delete("/schedules/holidays/{holiday_id}", response_model=Message)
def delete_holiday(holiday_id: int, db: DB, ctx: Annotated[TenantContext, Depends(require_permission("branches:write"))], meta: Meta):
    ScheduleService(db, ctx.organization, ctx.user, meta).delete_holiday(holiday_id)
    return Message(detail="Holiday removed.")


@router.get("/schedules/leaves", response_model=list[LeaveRead])
def list_leaves(db: DB, ctx: ReadSched, meta: Meta, professional_id: str | None = None, from_at: datetime | None = None, to_at: datetime | None = None):
    return _leave_read(db, ScheduleService(db, ctx.organization, ctx.user, meta).list_leaves(professional_id, from_at, to_at))


@router.post("/schedules/leaves", response_model=LeaveRead, status_code=status.HTTP_201_CREATED)
def add_leave(payload: LeaveCreate, db: DB, ctx: WriteSched, meta: Meta):
    return _leave_read(db, [ScheduleService(db, ctx.organization, ctx.user, meta).add_leave(payload)])[0]


@router.patch("/schedules/leaves/{leave_id}", response_model=LeaveRead)
def update_leave(leave_id: str, payload: LeaveUpdate, db: DB, ctx: WriteSched, meta: Meta):
    return _leave_read(db, [ScheduleService(db, ctx.organization, ctx.user, meta).update_leave(leave_id, payload)])[0]


@router.delete("/schedules/leaves/{leave_id}", response_model=Message)
def delete_leave(leave_id: str, db: DB, ctx: WriteSched, meta: Meta):
    ScheduleService(db, ctx.organization, ctx.user, meta).delete_leave(leave_id)
    return Message(detail="Leave removed.")


# ----------------------------------------------------------- availability
def compute_day(db, org, *, service_id: str, branch_id: str, professional_id: str | None, day: date) -> DayAvailability:
    catalog = CatalogService(db, org)
    service = catalog.get_service(service_id)
    branch = catalog.get_branch(branch_id)
    pro = catalog.get_professional(professional_id) if professional_id else None
    engine = AvailabilityService(db, org)
    engine.expire_stale_holds()
    return engine.day(service, branch, day, engine.candidates(service, branch, pro))


def compute_summary(db, org, *, service_id: str, branch_id: str, professional_id: str | None, from_date: date, to_date: date) -> list[AvailabilitySummary]:
    engine = AvailabilityService(db, org)
    engine.validate_range(from_date, to_date)
    catalog = CatalogService(db, org)
    service = catalog.get_service(service_id)
    branch = catalog.get_branch(branch_id)
    pro = catalog.get_professional(professional_id) if professional_id else None
    engine.expire_stale_holds()
    pros = engine.candidates(service, branch, pro)
    out = []
    d = from_date
    while d <= to_date:
        count = sum(len(engine.slots_for_professional(service, p, branch, d)) for p in pros)
        out.append(AvailabilitySummary(date=d, available=count > 0, slot_count=count))
        d += timedelta(days=1)
    return out


@router.get("/availability", response_model=DayAvailability, summary="Bookable slots for one day")
def availability(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("appointments:read"))], service_id: str, branch_id: str, day: date = Query(alias="date"), professional_id: str | None = None):
    return compute_day(db, ctx.organization, service_id=service_id, branch_id=branch_id, professional_id=professional_id, day=day)


@router.get("/availability/summary", response_model=list[AvailabilitySummary], summary="Which days in a range have any slot")
def availability_summary(db: DB, ctx: Annotated[TenantContext, Depends(require_permission("appointments:read"))], service_id: str, branch_id: str, from_date: date, to_date: date, professional_id: str | None = None):
    return compute_summary(db, ctx.organization, service_id=service_id, branch_id=branch_id, professional_id=professional_id, from_date=from_date, to_date=to_date)
