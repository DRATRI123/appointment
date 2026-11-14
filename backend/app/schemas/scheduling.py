"""Schedules, exceptions, holidays, leaves and availability."""
from __future__ import annotations

from datetime import date, datetime, time

from pydantic import AliasChoices, Field, model_validator

from app.schemas.common import APIModel


class ScheduleWindow(APIModel):
    weekday: int = Field(ge=0, le=6, description="0=Monday … 6=Sunday")
    start_time: time
    end_time: time
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    capacity: int = Field(default=1, ge=1, le=50)
    consultation_mode: str | None = Field(default=None, pattern=r"^(in_person|online|both)$")
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ScheduleSet(APIModel):
    """Replace the weekly schedule of a professional at a branch."""

    professional_id: str
    branch_id: str
    windows: list[ScheduleWindow]

    @model_validator(mode="after")
    def _no_overlap(self):
        by_day: dict[int, list[ScheduleWindow]] = {}
        for w in self.windows:
            by_day.setdefault(w.weekday, []).append(w)
        for day, ws in by_day.items():
            ws.sort(key=lambda w: w.start_time)
            for a, b in zip(ws, ws[1:], strict=False):
                if b.start_time < a.end_time:
                    raise ValueError(f"Overlapping windows on weekday {day}")
        return self


class ScheduleRead(ScheduleWindow):
    id: int
    professional_id: str
    branch_id: str
    is_active: bool


class ExceptionCreate(APIModel):
    professional_id: str
    branch_id: str | None = None
    date: date
    is_available: bool = False
    start_time: time | None = None
    end_time: time | None = None
    capacity: int | None = Field(default=None, ge=1, le=50)
    reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _window(self):
        if self.is_available and not (self.start_time and self.end_time):
            raise ValueError("An available exception needs start_time and end_time")
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class ExceptionRead(ExceptionCreate):
    id: int


class HolidayCreate(APIModel):
    branch_id: str | None = None
    date: date
    name: str = Field(min_length=1, max_length=120)
    is_recurring_yearly: bool = False


class HolidayRead(HolidayCreate):
    id: int


class LeaveCreate(APIModel):
    professional_id: str
    branch_id: str | None = None
    leave_type: str = Field(default="leave", pattern=r"^(leave|holiday|blocked)$")
    start_at: datetime
    end_at: datetime
    reason: str | None = None

    @model_validator(mode="after")
    def _order(self):
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at")
        return self


class LeaveUpdate(APIModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str | None = None
    status: str | None = Field(default=None, pattern=r"^(approved|pending|rejected|cancelled)$")


class LeaveRead(APIModel):
    id: str = Field(validation_alias=AliasChoices("public_id", "id"), serialization_alias="id")
    professional_id: str
    branch_id: str | None
    leave_type: str
    start_at: datetime
    end_at: datetime
    reason: str | None
    status: str


# ------------------------------------------------------------ availability
class SlotRead(APIModel):
    start_at: datetime
    end_at: datetime
    remaining: int
    professional_id: str


class ProfessionalAvailability(APIModel):
    professional_id: str
    display_name: str
    slots: list[SlotRead]


class DayAvailability(APIModel):
    date: date
    timezone: str
    service_id: str
    branch_id: str
    duration_minutes: int
    professionals: list[ProfessionalAvailability]

    @property
    def total_slots(self) -> int:
        return sum(len(p.slots) for p in self.professionals)


class AvailabilitySummary(APIModel):
    date: date
    available: bool
    slot_count: int
