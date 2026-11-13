"""Weekly schedules, date exceptions, holidays and leaves."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Holiday, Organization, ProfessionalLeave, Schedule, ScheduleException, User
from app.schemas.scheduling import ExceptionCreate, HolidayCreate, LeaveCreate, LeaveUpdate, ScheduleSet
from app.services.audit_service import RequestMeta, record_audit
from app.services.catalog_service import CatalogService


class ScheduleService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()
        self.catalog = CatalogService(db, org, actor, meta)

    # ---------------------------------------------------------- schedules
    def list_schedules(self, professional_id: str | None = None, branch_id: str | None = None) -> list[Schedule]:
        stmt = select(Schedule).where(Schedule.organization_id == self.org.id, Schedule.is_active.is_(True))
        if professional_id:
            stmt = stmt.where(Schedule.professional_id == self.catalog.get_professional(professional_id).id)
        if branch_id:
            stmt = stmt.where(Schedule.branch_id == self.catalog.get_branch(branch_id).id)
        return list(self.db.scalars(stmt.order_by(Schedule.professional_id, Schedule.branch_id, Schedule.weekday, Schedule.start_time)).all())

    def set_schedule(self, payload: ScheduleSet) -> list[Schedule]:
        pro = self.catalog.get_professional(payload.professional_id)
        branch = self.catalog.get_branch(payload.branch_id)
        if not any(pb.branch_id == branch.id for pb in pro.branches):
            raise ConflictError("Assign the professional to this branch before setting a schedule.", code="not_assigned")
        existing = self.db.scalars(select(Schedule).where(Schedule.professional_id == pro.id, Schedule.branch_id == branch.id)).all()
        for row in existing:
            self.db.delete(row)
        self.db.flush()
        rows = []
        for w in payload.windows:
            row = Schedule(organization_id=self.org.id, professional_id=pro.id, branch_id=branch.id, **w.model_dump())
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        record_audit(self.db, action="schedule.set", actor=self.actor, organization_id=self.org.id, entity_type="professional",
                     entity_id=pro.public_id, after={"branch": branch.public_id, "windows": len(rows)}, meta=self.meta)
        return rows

    # --------------------------------------------------------- exceptions
    def list_exceptions(self, professional_id: str | None, from_date: date | None, to_date: date | None) -> list[ScheduleException]:
        stmt = select(ScheduleException).where(ScheduleException.organization_id == self.org.id)
        if professional_id:
            stmt = stmt.where(ScheduleException.professional_id == self.catalog.get_professional(professional_id).id)
        if from_date:
            stmt = stmt.where(ScheduleException.date >= from_date)
        if to_date:
            stmt = stmt.where(ScheduleException.date <= to_date)
        return list(self.db.scalars(stmt.order_by(ScheduleException.date)).all())

    def add_exception(self, payload: ExceptionCreate) -> ScheduleException:
        pro = self.catalog.get_professional(payload.professional_id)
        branch = self.catalog.get_branch(payload.branch_id) if payload.branch_id else None
        row = ScheduleException(
            organization_id=self.org.id, professional_id=pro.id, branch_id=branch.id if branch else None,
            **payload.model_dump(exclude={"professional_id", "branch_id"}),
        )
        self.db.add(row)
        self.db.flush()
        record_audit(self.db, action="schedule.exception_added", actor=self.actor, organization_id=self.org.id,
                     entity_type="professional", entity_id=pro.public_id, after={"date": str(payload.date), "available": payload.is_available}, meta=self.meta)
        return row

    def delete_exception(self, exception_id: int) -> None:
        row = self.db.get(ScheduleException, exception_id)
        if row is None or row.organization_id != self.org.id:
            raise NotFoundError("Exception not found.")
        self.db.delete(row)
        self.db.flush()

    # ----------------------------------------------------------- holidays
    def list_holidays(self, from_date: date | None = None, to_date: date | None = None) -> list[Holiday]:
        stmt = select(Holiday).where(Holiday.organization_id == self.org.id)
        if from_date:
            stmt = stmt.where((Holiday.date >= from_date) | Holiday.is_recurring_yearly.is_(True))
        if to_date:
            stmt = stmt.where((Holiday.date <= to_date) | Holiday.is_recurring_yearly.is_(True))
        return list(self.db.scalars(stmt.order_by(Holiday.date)).all())

    def add_holiday(self, payload: HolidayCreate) -> Holiday:
        branch = self.catalog.get_branch(payload.branch_id) if payload.branch_id else None
        dup = self.db.scalar(select(Holiday.id).where(Holiday.organization_id == self.org.id, Holiday.date == payload.date, Holiday.branch_id == (branch.id if branch else None)))
        if dup:
            raise ConflictError("A holiday already exists on this date.", code="holiday_exists")
        row = Holiday(organization_id=self.org.id, branch_id=branch.id if branch else None, date=payload.date, name=payload.name, is_recurring_yearly=payload.is_recurring_yearly)
        self.db.add(row)
        self.db.flush()
        record_audit(self.db, action="holiday.added", actor=self.actor, organization_id=self.org.id, entity_type="holiday", entity_id=row.id, after={"date": str(payload.date), "name": payload.name}, meta=self.meta)
        return row

    def delete_holiday(self, holiday_id: int) -> None:
        row = self.db.get(Holiday, holiday_id)
        if row is None or row.organization_id != self.org.id:
            raise NotFoundError("Holiday not found.")
        self.db.delete(row)
        self.db.flush()

    # ------------------------------------------------------------- leaves
    def list_leaves(self, professional_id: str | None = None, from_at=None, to_at=None) -> list[ProfessionalLeave]:
        stmt = select(ProfessionalLeave).where(ProfessionalLeave.organization_id == self.org.id)
        if professional_id:
            stmt = stmt.where(ProfessionalLeave.professional_id == self.catalog.get_professional(professional_id).id)
        if from_at:
            stmt = stmt.where(ProfessionalLeave.end_at >= from_at)
        if to_at:
            stmt = stmt.where(ProfessionalLeave.start_at <= to_at)
        return list(self.db.scalars(stmt.order_by(ProfessionalLeave.start_at.desc())).all())

    def add_leave(self, payload: LeaveCreate, status: str = "approved") -> ProfessionalLeave:
        pro = self.catalog.get_professional(payload.professional_id)
        branch = self.catalog.get_branch(payload.branch_id) if payload.branch_id else None
        row = ProfessionalLeave(
            organization_id=self.org.id, professional_id=pro.id, branch_id=branch.id if branch else None, leave_type=payload.leave_type,
            start_at=payload.start_at, end_at=payload.end_at, reason=payload.reason, status=status,
            approved_by_user_id=self.actor.id if (self.actor and status == "approved") else None,
        )
        self.db.add(row)
        self.db.flush()
        record_audit(self.db, action="leave.added", actor=self.actor, organization_id=self.org.id, entity_type="professional", entity_id=pro.public_id,
                     after={"from": payload.start_at.isoformat(), "to": payload.end_at.isoformat(), "status": status}, meta=self.meta)
        return row

    def update_leave(self, public_id: str, payload: LeaveUpdate) -> ProfessionalLeave:
        row = self.db.scalar(select(ProfessionalLeave).where(ProfessionalLeave.public_id == public_id, ProfessionalLeave.organization_id == self.org.id))
        if row is None:
            raise NotFoundError("Leave not found.")
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(row, k, v)
        if row.start_at >= row.end_at:
            raise ConflictError("start_at must be before end_at.")
        if payload.status == "approved" and self.actor:
            row.approved_by_user_id = self.actor.id
        self.db.flush()
        return row

    def delete_leave(self, public_id: str) -> None:
        row = self.db.scalar(select(ProfessionalLeave).where(ProfessionalLeave.public_id == public_id, ProfessionalLeave.organization_id == self.org.id))
        if row is None:
            raise NotFoundError("Leave not found.")
        self.db.delete(row)
        self.db.flush()
