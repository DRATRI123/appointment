"""Branch isolation: staff assigned to one branch only ever read that branch's data.

A membership with a ``branch_id`` (branch manager, receptionist, doctor or staff at one location) turns on a filter
for that request's database session. Every ORM query then gets "only this branch" added automatically, so list pages,
detail pages, reports, exports and any future endpoint are covered without each one remembering to check. A record
of another branch simply does not exist for them (404), the same as a record of another clinic.

* Booked work belongs to one branch: appointments, holds, payments, refunds, the appointment slot grid.
* Set-up can apply to all branches (no branch) or one: schedules, leave, holidays, date exceptions, UPI accounts,
  booking forms, waitlist entries, branch prices. Branch staff see the ones for all branches and their own.
* Patients have no branch. Branch staff see patients with a visit at their branch, or none yet (just registered at
  the desk); patients who only visit other branches are hidden. Their notes and documents follow the patient.
* Help desk requests follow the booking they are about; general questions (no booking) are visible to all branches.
* Owners and administrators (no branch on their membership) and the platform super admin are not filtered.

This is in addition to, not instead of, the organization isolation every query already has.
"""
from __future__ import annotations

from sqlalchemy import event, exists, or_, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

SCOPE_KEY = "branch_scope"


def set_branch_scope(db: Session, branch_id: int | None) -> None:
    """Limit this session to one branch, or (None) remove the limit."""
    if branch_id is None:
        db.info.pop(SCOPE_KEY, None)
    else:
        db.info[SCOPE_KEY] = branch_id


@event.listens_for(Session, "do_orm_execute")
def _only_this_branch(state: ORMExecuteState) -> None:
    bid = state.session.info.get(SCOPE_KEY)
    if bid is None or not state.is_select or state.is_column_load:
        return
    from app.models import (
        Appointment,
        AppointmentSlot,
        BookingForm,
        BookingHold,
        Branch,
        Customer,
        CustomerDocument,
        CustomerNote,
        Holiday,
        Payment,
        PaymentRefund,
        ProfessionalLeave,
        Schedule,
        ScheduleException,
        ServicePricing,
        SupportTicket,
        UPIAccount,
        Waitlist,
    )

    def own(cls):
        return lambda c: c.branch_id == bid

    def own_or_all(cls):
        return lambda c: or_(c.branch_id == bid, c.branch_id.is_(None))

    # Plain tables (not ORM classes) inside the conditions, so the conditions themselves are not filtered again:
    # "has no visit anywhere" must look at every branch.
    appts, pays = Appointment.__table__.c, Payment.__table__.c
    in_branch = select(appts.id).where(appts.branch_id == bid)
    criteria = [
        with_loader_criteria(Branch, lambda c: c.id == bid, include_aliases=True),
        with_loader_criteria(Appointment, own(Appointment), include_aliases=True),
        with_loader_criteria(BookingHold, own(BookingHold), include_aliases=True),
        with_loader_criteria(AppointmentSlot, own(AppointmentSlot), include_aliases=True),
        with_loader_criteria(Schedule, own(Schedule), include_aliases=True),
        with_loader_criteria(ServicePricing, own(ServicePricing), include_aliases=True),
        with_loader_criteria(ScheduleException, own_or_all(ScheduleException), include_aliases=True),
        with_loader_criteria(Holiday, own_or_all(Holiday), include_aliases=True),
        with_loader_criteria(ProfessionalLeave, own_or_all(ProfessionalLeave), include_aliases=True),
        with_loader_criteria(UPIAccount, own_or_all(UPIAccount), include_aliases=True),
        with_loader_criteria(BookingForm, own_or_all(BookingForm), include_aliases=True),
        with_loader_criteria(Waitlist, own_or_all(Waitlist), include_aliases=True),
        # Help desk: requests about this branch's bookings, and general ones (no branch).
        with_loader_criteria(SupportTicket, own_or_all(SupportTicket), include_aliases=True),
        with_loader_criteria(Payment, lambda c: or_(c.branch_id == bid, c.appointment_id.in_(in_branch)), include_aliases=True),
        with_loader_criteria(PaymentRefund, lambda c: c.payment_id.in_(
            select(pays.id).where(or_(pays.branch_id == bid, pays.appointment_id.in_(in_branch)))), include_aliases=True),
        with_loader_criteria(Customer, lambda c: or_(
            exists().where(appts.customer_id == c.id, appts.branch_id == bid),
            ~exists().where(appts.customer_id == c.id)), include_aliases=True),
        with_loader_criteria(CustomerNote, lambda c: or_(c.appointment_id.is_(None), c.appointment_id.in_(in_branch)), include_aliases=True),
        with_loader_criteria(CustomerDocument, lambda c: or_(c.appointment_id.is_(None), c.appointment_id.in_(in_branch)), include_aliases=True),
    ]
    state.statement = state.statement.options(*criteria)
