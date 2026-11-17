from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User
from app.repositories.organizations import MembershipRepository
from app.schemas.user import MembershipSummary, MeResponse, OrganizationSummary, UserRead, UserUpdate
from app.security.permissions import PERMISSIONS


def permissions_for_membership(membership) -> list[str]:
    return sorted(p.code for p in membership.role.permissions)


def build_me_response(db: Session, user: User, *, panel_organization_id: int | None = None) -> MeResponse:
    """``panel_organization_id``: an embedded-panel sign-in sees only that clinic (and no super admin role)."""
    memberships = MembershipRepository(db).list_for_user(user.id)
    summaries = []
    for m in memberships:
        if m.organization.deleted_at is not None:
            continue
        if panel_organization_id is not None and m.organization_id != panel_organization_id:
            continue
        summaries.append(
            MembershipSummary(
                id=m.public_id,
                organization=OrganizationSummary.model_validate(m.organization),
                role_code=m.role.code,
                role_name=m.role.name,
                branch_id=m.branch.public_id if m.branch else None,
                status=m.status,
                permissions=sorted(PERMISSIONS) if user.is_platform_admin and panel_organization_id is None else permissions_for_membership(m),
            )
        )
    return MeResponse(user=UserRead.model_validate(user), memberships=summaries,
                      is_platform_admin=user.is_platform_admin and panel_organization_id is None)


def update_me(db: Session, user: User, payload: UserUpdate) -> User:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    db.flush()
    return user
