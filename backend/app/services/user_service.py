from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User
from app.repositories.organizations import MembershipRepository
from app.schemas.user import MeResponse, MembershipSummary, OrganizationSummary, UserRead, UserUpdate
from app.security.permissions import PERMISSIONS


def permissions_for_membership(membership) -> list[str]:
    return sorted(p.code for p in membership.role.permissions)


def build_me_response(db: Session, user: User) -> MeResponse:
    memberships = MembershipRepository(db).list_for_user(user.id)
    summaries = []
    for m in memberships:
        if m.organization.deleted_at is not None:
            continue
        summaries.append(
            MembershipSummary(
                id=m.public_id,
                organization=OrganizationSummary.model_validate(m.organization),
                role_code=m.role.code,
                role_name=m.role.name,
                branch_id=m.branch.public_id if m.branch else None,
                status=m.status,
                permissions=sorted(PERMISSIONS) if user.is_platform_admin else permissions_for_membership(m),
            )
        )
    return MeResponse(user=UserRead.model_validate(user), memberships=summaries, is_platform_admin=user.is_platform_admin)


def update_me(db: Session, user: User, payload: UserUpdate) -> User:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    db.flush()
    return user
