"""Availability engine.

For a professional at a branch on a date (branch timezone):
  windows   = weekly schedules (valid on that date) overridden by date exceptions
  minus     = organization/branch holidays, approved leaves
  slots     = windows stepped by the slot grid (schedule.slot_minutes → branch assignment → professional default)
  a slot is bookable when the appointment interval [start, start+duration+buffer) fits the window and does
  not collide with active appointments or unexpired holds (capacity 1), or when fewer than `capacity`
  bookings start at the same time (capacity > 1); min notice and max advance days are honoured.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ACTIVE_APPOINTMENT_STATUSES, HoldStatus
from app.core.exceptions import ValidationFailed
from app.core.time import utcnow
from app.models import (
    Appointment,
    BookingHold,
    Branch,
    Holiday,
    Organization,
    Professional,
    ProfessionalLeave,
    Schedule,
    ScheduleException,
    Service,
)
from app.schemas.scheduling import DayAvailability, ProfessionalAvailability, SlotRead
from app.services.organization_service import OrganizationService

MAX_RANGE_DAYS = 31


@dataclass
class Window:
    start: datetime  # aware UTC
    end: datetime
    capacity: int
    slot_minutes: int | None


@dataclass
class Busy:
    start: datetime
    end: datetime
    sequence: int


def branch_tz(org: Organization, branch: Branch) -> ZoneInfo:
    return ZoneInfo(branch.timezone or org.timezone or "UTC")


def appointment_length(service: Service, professional: Professional, branch: Branch) -> tuple[int, int]:
    """(duration_minutes, buffer_minutes) for this combination."""
    duration = service.duration_minutes
    override = next((ps for ps in professional.services if ps.service_id == service.id and ps.branch_id in (None, branch.id) and ps.duration_override_minutes), None)
    if override:
        duration = override.duration_override_minutes
    pb = next((x for x in professional.branches if x.branch_id == branch.id), None)
    buffer = max(service.buffer_minutes, pb.buffer_minutes if (pb and pb.buffer_minutes is not None) else professional.buffer_minutes)
    return duration, buffer


def slot_grid_minutes(service: Service, professional: Professional, branch: Branch, schedule_slot: int | None) -> int:
    if schedule_slot:
        return schedule_slot
    pb = next((x for x in professional.branches if x.branch_id == branch.id), None)
    if pb and pb.duration_minutes:
        return pb.duration_minutes
    return professional.default_duration_minutes or service.duration_minutes


class AvailabilityService:
    def __init__(self, db: Session, org: Organization):
        self.db = db
        self.org = org
        self._booking_settings = None

    @property
    def booking_settings(self) -> dict:
        if self._booking_settings is None:
            self._booking_settings = OrganizationService(self.db).get_settings(self.org, "booking")["booking"]
        return self._booking_settings

    # ------------------------------------------------------------ lookups
    def expire_stale_holds(self) -> int:
        now = utcnow()
        rows = self.db.scalars(select(BookingHold).where(BookingHold.organization_id == self.org.id, BookingHold.status == HoldStatus.ACTIVE, BookingHold.expires_at < now)).all()
        for h in rows:
            h.status = HoldStatus.EXPIRED
            h.released_at = now
        if rows:
            self.db.flush()
        return len(rows)

    def windows_for(self, professional: Professional, branch: Branch, day: date, tz: ZoneInfo) -> list[Window]:
        # Holidays (organization-wide or this branch; yearly recurring by month/day)
        for h in self.db.scalars(select(Holiday).where(Holiday.organization_id == self.org.id, Holiday.branch_id.in_([None, branch.id]) if False else (Holiday.branch_id.is_(None) | (Holiday.branch_id == branch.id)))).all():
            if h.date == day or (h.is_recurring_yearly and (h.date.month, h.date.day) == (day.month, day.day)):
                return []
        exceptions = self.db.scalars(
            select(ScheduleException).where(
                ScheduleException.professional_id == professional.id, ScheduleException.date == day,
                ScheduleException.branch_id.is_(None) | (ScheduleException.branch_id == branch.id),
            )
        ).all()
        if any(not e.is_available for e in exceptions):
            return []
        windows: list[Window] = []
        available_exceptions = [e for e in exceptions if e.is_available]
        if available_exceptions:
            for e in available_exceptions:
                windows.append(Window(_at(day, e.start_time, tz), _at(day, e.end_time, tz), e.capacity or professional.slot_capacity, None))
            return windows
        schedules = self.db.scalars(
            select(Schedule).where(
                Schedule.professional_id == professional.id, Schedule.branch_id == branch.id, Schedule.weekday == day.weekday(), Schedule.is_active.is_(True),
            )
        ).all()
        for s in schedules:
            if s.valid_from and day < s.valid_from:
                continue
            if s.valid_to and day > s.valid_to:
                continue
            windows.append(Window(_at(day, s.start_time, tz), _at(day, s.end_time, tz), s.capacity or professional.slot_capacity, s.slot_minutes))
        return windows

    def busy_for(self, professional: Professional, branch: Branch, day_start: datetime, day_end: datetime, *, exclude_appointment_id: int | None = None, exclude_hold_id: int | None = None) -> tuple[list[Busy], list[tuple[datetime, datetime]]]:
        appts = self.db.execute(
            select(Appointment.start_at, Appointment.end_at, Appointment.slot_sequence, Appointment.id).where(
                Appointment.professional_id == professional.id, Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                Appointment.end_at > day_start, Appointment.start_at < day_end,
            )
        ).all()
        holds = self.db.execute(
            select(BookingHold.start_at, BookingHold.end_at, BookingHold.slot_sequence, BookingHold.id).where(
                BookingHold.professional_id == professional.id, BookingHold.status == HoldStatus.ACTIVE, BookingHold.expires_at > utcnow(),
                BookingHold.end_at > day_start, BookingHold.start_at < day_end,
            )
        ).all()
        busy = [Busy(s, e, seq) for s, e, seq, aid in appts if aid != exclude_appointment_id]
        busy += [Busy(s, e, seq) for s, e, seq, hid in holds if hid != exclude_hold_id]
        leaves = self.db.execute(
            select(ProfessionalLeave.start_at, ProfessionalLeave.end_at).where(
                ProfessionalLeave.professional_id == professional.id, ProfessionalLeave.status == "approved",
                ProfessionalLeave.branch_id.is_(None) | (ProfessionalLeave.branch_id == branch.id),
                ProfessionalLeave.end_at > day_start, ProfessionalLeave.start_at < day_end,
            )
        ).all()
        from app.models import ExternalBusyBlock

        external = self.db.execute(
            select(ExternalBusyBlock.start_at, ExternalBusyBlock.end_at).where(
                ExternalBusyBlock.professional_id == professional.id, ExternalBusyBlock.end_at > day_start, ExternalBusyBlock.start_at < day_end,
            )
        ).all()
        return busy, [(s, e) for s, e in leaves] + [(s, e) for s, e in external]

    # ------------------------------------------------------------- engine
    def slots_for_professional(self, service: Service, professional: Professional, branch: Branch, day: date, *, now: datetime | None = None, ignore_notice: bool = False, exclude_appointment_id: int | None = None) -> list[SlotRead]:
        tz = branch_tz(self.org, branch)
        now = now or utcnow()
        duration, buffer = appointment_length(service, professional, branch)
        windows = self.windows_for(professional, branch, day, tz)
        if not windows:
            return []
        day_start = _at(day, time(0, 0), tz)
        day_end = day_start + timedelta(days=1)
        busy, leaves = self.busy_for(professional, branch, day_start, day_end, exclude_appointment_id=exclude_appointment_id)
        min_notice = service.min_notice_minutes if service.min_notice_minutes is not None else int(self.booking_settings.get("min_notice_minutes", 0) or 0)
        max_days = service.max_advance_days if service.max_advance_days is not None else int(self.booking_settings.get("max_advance_days", 365) or 365)
        earliest = now + timedelta(minutes=min_notice)
        latest = now + timedelta(days=max_days)
        out: list[SlotRead] = []
        for w in windows:
            step = slot_grid_minutes(service, professional, branch, w.slot_minutes)
            cursor = w.start
            while cursor + timedelta(minutes=duration) <= w.end:
                start, end = cursor, cursor + timedelta(minutes=duration)
                block_end = end + timedelta(minutes=buffer)
                cursor += timedelta(minutes=step)
                if not ignore_notice and (start < earliest or start > latest):
                    continue
                if any(ls < block_end and le > start for ls, le in leaves):
                    continue
                remaining = self._remaining(start, block_end, busy, w.capacity)
                if remaining > 0:
                    out.append(SlotRead(start_at=start, end_at=end, remaining=remaining, professional_id=professional.public_id))
        return out

    @staticmethod
    def _remaining(start: datetime, block_end: datetime, busy: list[Busy], capacity: int) -> int:
        same_start = [b for b in busy if b.start == start]
        overlapping = [b for b in busy if b.start < block_end and b.end > start and b.start != start]
        if capacity <= 1:
            return 0 if (same_start or overlapping) else 1
        # capacity > 1: identical start times share the slot; a differently-timed overlap blocks it entirely
        if overlapping:
            return 0
        return max(0, capacity - len(same_start))

    def next_sequence(self, start: datetime, busy: list[Busy]) -> int:
        used = {b.sequence for b in busy if b.start == start}
        seq = 0
        while seq in used:
            seq += 1
        return seq

    def day(self, service: Service, branch: Branch, day: date, professionals: list[Professional], *, now: datetime | None = None) -> DayAvailability:
        tz = branch_tz(self.org, branch)
        result = []
        for pro in professionals:
            slots = self.slots_for_professional(service, pro, branch, day, now=now)
            result.append(ProfessionalAvailability(professional_id=pro.public_id, display_name=pro.display_name, slots=slots))
        duration = min((appointment_length(service, p, branch)[0] for p in professionals), default=service.duration_minutes)
        return DayAvailability(date=day, timezone=str(tz), service_id=service.public_id, branch_id=branch.public_id, duration_minutes=duration, professionals=result)

    def candidates(self, service: Service, branch: Branch, professional: Professional | None) -> list[Professional]:
        stmt = (
            select(Professional).options(selectinload(Professional.branches), selectinload(Professional.services))
            .where(Professional.organization_id == self.org.id, Professional.deleted_at.is_(None), Professional.is_active.is_(True))
        )
        if professional is not None:
            stmt = stmt.where(Professional.id == professional.id)
        pros = []
        for p in self.db.scalars(stmt.order_by(Professional.sort_order, Professional.display_name)).all():
            if not any(pb.branch_id == branch.id and pb.is_active for pb in p.branches):
                continue
            if not any(ps.service_id == service.id and ps.is_active and ps.branch_id in (None, branch.id) for ps in p.services):
                continue
            pros.append(p)
        return pros

    def validate_range(self, from_date: date, to_date: date) -> None:
        if to_date < from_date:
            raise ValidationFailed("to_date must be after from_date.")
        if (to_date - from_date).days > MAX_RANGE_DAYS:
            raise ValidationFailed(f"Range is limited to {MAX_RANGE_DAYS} days.")


def _at(day: date, t: time, tz: ZoneInfo) -> datetime:
    from datetime import UTC

    return datetime.combine(day, t, tzinfo=tz).astimezone(UTC)
