"""Embedded admin panel: a clinic's own app (for example its clinic software) shows this admin panel in an iframe.

* The clinic admin turns it on and lists the exact web addresses of its app (Admin → Settings → Panel in your app).
  The website lets only those addresses frame /panel/<clinic> (CSP ``frame-ancestors``); every other page keeps
  refusing frames.
* Inside the frame the person signs in again (email and password, plus the authenticator code if they use one). Only
  members of this clinic with the ``panel:use`` permission can (owners and administrators have it; other roles only if
  given in Roles & permissions).
* That sign-in is separate from the normal one: its tokens live only in that frame (never in cookies), and the session
  works only for this clinic, only while the panel stays on and the person keeps ``panel:use``. Turning the panel off,
  removing the permission or the address cuts it off at the next request.
* Both apps stay independent: no shared database and no data passes through the clinic's app.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import PermissionDenied
from app.models import Organization, OrganizationMembership, User
from app.repositories.organizations import MembershipRepository, OrganizationRepository

PERMISSION = "panel:use"
DEVICE_LABEL = "Clinic app panel"


class PanelNotAllowed(PermissionDenied):
    pass


def policy(db: Session, org: Organization) -> dict[str, Any]:
    """{"enabled": bool, "allowed_origins": [...]}: the clinic's saved values, or the defaults."""
    repo = OrganizationRepository(db)
    out: dict[str, Any] = {"enabled": False, "allowed_origins": []}
    for row in repo.list_settings(org.id, "panel"):
        out[row.key] = (row.value or {}).get("v")
    out["enabled"] = out.get("enabled") is True
    out["allowed_origins"] = [o for o in (out.get("allowed_origins") or []) if isinstance(o, str)]
    return out


def is_open(pol: dict[str, Any]) -> bool:
    return bool(pol["enabled"] and pol["allowed_origins"])


def require_open(db: Session, org: Organization) -> dict[str, Any]:
    pol = policy(db, org)
    if not is_open(pol):
        raise PanelNotAllowed("The admin panel is not switched on for this clinic's app.", code="panel_disabled")
    return pol


def member_with_permission(db: Session, org: Organization, user: User) -> OrganizationMembership:
    """The person's active membership in this clinic, if their role has ``panel:use``; otherwise refused."""
    membership = MembershipRepository(db).get_for_user_in_org(user.id, org.id)
    if membership is None or membership.role is None or PERMISSION not in {p.code for p in membership.role.permissions}:
        raise PanelNotAllowed("This account cannot open the admin panel here. Ask the clinic owner for the permission "
                              "\"Open the admin panel inside the clinic's own app\".", code="panel_not_allowed")
    return membership


def check_session(db: Session, org: Organization, user: User, panel_organization_id: int) -> OrganizationMembership:
    """Every request of an embedded-panel session: same clinic, panel still on, permission still held."""
    if org.id != panel_organization_id:
        raise PanelNotAllowed("This sign-in works only for the clinic whose app you opened it in.", code="panel_scope")
    require_open(db, org)
    return member_with_permission(db, org, user)
