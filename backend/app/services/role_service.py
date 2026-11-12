from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SystemRole
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.models import Organization, OrganizationMembership, Permission, Role, User
from app.repositories.organizations import RoleRepository
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.security.permissions import PERMISSIONS
from app.services.audit_service import RequestMeta, record_audit


def role_to_read(role: Role) -> RoleRead:
    return RoleRead(
        id=role.id, code=role.code, name=role.name, description=role.description, is_system=role.is_system,
        scope=role.scope, is_custom=role.organization_id is not None, permissions=sorted(p.code for p in role.permissions),
    )


class RoleService:
    def __init__(self, db: Session, meta: RequestMeta | None = None):
        self.db = db
        self.meta = meta or RequestMeta()
        self.roles = RoleRepository(db)

    def list_permissions(self) -> list[Permission]:
        return list(self.db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all())

    def list_roles(self, org: Organization) -> list[Role]:
        return self.roles.list_for_org(org.id)

    def _validate_permissions(self, codes: list[str], granter_permissions: set[str], is_platform_admin: bool) -> list[Permission]:
        unknown = [c for c in codes if c not in PERMISSIONS]
        if unknown:
            raise ValidationFailed(f"Unknown permissions: {', '.join(unknown)}", code="unknown_permission")
        if any(c.startswith("platform:") for c in codes):
            raise PermissionDenied("Platform permissions cannot be granted to organization roles.", code="platform_permission")
        if not is_platform_admin:
            escalation = [c for c in codes if c not in granter_permissions]
            if escalation:
                raise PermissionDenied(
                    f"You cannot grant permissions you do not hold: {', '.join(escalation)}", code="privilege_escalation"
                )
        return list(self.db.scalars(select(Permission).where(Permission.code.in_(codes))).all())

    def create(self, org: Organization, payload: RoleCreate, actor: User, granter_permissions: set[str]) -> Role:
        if payload.code in {r.value for r in SystemRole} or self.roles.get_role_for_org(org.id, payload.code) and \
                self.roles.get_role_for_org(org.id, payload.code).organization_id == org.id:
            raise ConflictError("A role with this code already exists.", code="role_code_taken")
        codes = list(payload.permissions)
        if payload.clone_from:
            base = self.roles.get_system_role(payload.clone_from)
            if base is None:
                raise ValidationFailed("Unknown role to clone from.", code="unknown_role")
            codes = sorted(set(codes) | {p.code for p in base.permissions})
        perms = self._validate_permissions(codes, granter_permissions, actor.is_platform_admin)
        role = Role(organization_id=org.id, code=payload.code, name=payload.name, description=payload.description, is_system=False)
        role.permissions = perms
        self.db.add(role)
        self.db.flush()
        record_audit(self.db, action="role.created", actor=actor, organization_id=org.id, entity_type="role",
                     entity_id=role.code, after={"permissions": codes}, meta=self.meta)
        return role

    def update(self, org: Organization, role_id: int, payload: RoleUpdate, actor: User, granter_permissions: set[str]) -> Role:
        role = self._get_custom(org, role_id)
        before = {"name": role.name, "permissions": sorted(p.code for p in role.permissions)}
        if payload.name is not None:
            role.name = payload.name
        if payload.description is not None:
            role.description = payload.description
        if payload.permissions is not None:
            role.permissions = self._validate_permissions(payload.permissions, granter_permissions, actor.is_platform_admin)
        self.db.flush()
        record_audit(self.db, action="role.updated", actor=actor, organization_id=org.id, entity_type="role",
                     entity_id=role.code, before=before,
                     after={"name": role.name, "permissions": sorted(p.code for p in role.permissions)}, meta=self.meta)
        return role

    def delete(self, org: Organization, role_id: int, actor: User) -> None:
        role = self._get_custom(org, role_id)
        in_use = self.db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.role_id == role.id, OrganizationMembership.status != "removed"
            )
        )
        if in_use:
            raise ConflictError("Role is assigned to staff. Reassign them first.", code="role_in_use")
        self.db.delete(role)
        self.db.flush()
        record_audit(self.db, action="role.deleted", actor=actor, organization_id=org.id, entity_type="role",
                     entity_id=role.code, meta=self.meta)

    def _get_custom(self, org: Organization, role_id: int) -> Role:
        role = self.db.get(Role, role_id)
        if role is None or role.organization_id != org.id:
            raise NotFoundError("Custom role not found.")
        return role
