from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import MembershipStatus, SystemRole, UserStatus
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models import Branch, Organization, OrganizationMembership, User
from app.repositories.organizations import MembershipRepository, RoleRepository
from app.repositories.users import UserRepository
from app.schemas.membership import MemberInvite, MemberUpdate
from app.security.identifiers import normalize_email, normalize_mobile
from app.services.audit_service import RequestMeta, record_audit

STAFF_ASSIGNABLE_ROLES = {r.value for r in SystemRole} - {SystemRole.PLATFORM_SUPER_ADMIN.value, SystemRole.CUSTOMER.value}


class MembershipService:
    def __init__(self, db: Session, meta: RequestMeta | None = None):
        self.db = db
        self.meta = meta or RequestMeta()
        self.memberships = MembershipRepository(db)
        self.roles = RoleRepository(db)
        self.users = UserRepository(db)

    def list_members(self, org: Organization) -> list[OrganizationMembership]:
        return [m for m in self.memberships.list_for_organization(org.id) if m.role.code != SystemRole.CUSTOMER]

    def _resolve_role(self, org: Organization, role_code: str):
        role = self.roles.get_role_for_org(org.id, role_code)
        if role is None:
            raise ValidationFailed("Unknown role.", code="unknown_role")
        if role.is_system and role.code not in STAFF_ASSIGNABLE_ROLES:
            raise PermissionDenied("This role cannot be assigned to staff.", code="role_not_assignable")
        return role

    def _resolve_branch(self, org: Organization, branch_public_id: str | None) -> Branch | None:
        if not branch_public_id:
            return None
        branch = self.db.query(Branch).filter(Branch.public_id == branch_public_id, Branch.organization_id == org.id).first()
        if branch is None:
            raise NotFoundError("Branch not found in this organization.")
        return branch

    def invite(self, org: Organization, payload: MemberInvite, actor: User, actor_role_code: str | None) -> OrganizationMembership:
        from app.services.platform_service import check_limit

        check_limit(self.db, org, "staff")
        role = self._resolve_role(org, payload.role_code)
        self._guard_owner_assignment(role.code, actor_role_code, actor)
        branch = self._resolve_branch(org, payload.branch_id)
        if "@" in payload.identifier:
            email = normalize_email(payload.identifier)
            user = self.users.get_by_email(email)
            if user is None:
                user = User(full_name=payload.full_name.strip(), email=email, status=UserStatus.PENDING_VERIFICATION)
                self.users.add(user)
        else:
            mobile = normalize_mobile(payload.identifier)
            user = self.users.get_by_mobile(mobile)
            if user is None:
                user = User(full_name=payload.full_name.strip(), mobile=mobile, status=UserStatus.PENDING_VERIFICATION)
                self.users.add(user)
        existing = [m for m in self.memberships.list_for_organization(org.id) if m.user_id == user.id]
        if existing:
            raise ConflictError("This person is already a member of the organization.", code="already_member")
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role_id=role.id,
            branch_id=branch.id if branch else None,
            status=MembershipStatus.INVITED if user.status == UserStatus.PENDING_VERIFICATION else MembershipStatus.ACTIVE,
            invited_by_user_id=actor.id,
            invited_at=utcnow(),
            accepted_at=None if user.status == UserStatus.PENDING_VERIFICATION else utcnow(),
        )
        self.memberships.add(membership)
        record_audit(
            self.db, action="staff.invited", actor=actor, organization_id=org.id, entity_type="membership",
            entity_id=membership.public_id, after={"user": user.public_id, "role": role.code}, meta=self.meta,
        )
        return membership

    def update(self, org: Organization, membership_public_id: str, payload: MemberUpdate, actor: User, actor_role_code: str | None) -> OrganizationMembership:
        membership = self._get(org, membership_public_id)
        before = {"role": membership.role.code, "status": membership.status, "branch_id": membership.branch_id}
        if payload.role_code and payload.role_code != membership.role.code:
            role = self._resolve_role(org, payload.role_code)
            self._guard_owner_assignment(role.code, actor_role_code, actor)
            if membership.role.code == SystemRole.ORG_OWNER:
                self._guard_last_owner(org, membership)
            membership.role_id = role.id
        if payload.clear_branch:
            membership.branch_id = None
        elif payload.branch_id:
            branch = self._resolve_branch(org, payload.branch_id)
            membership.branch_id = branch.id if branch else None
        if payload.status:
            if membership.user_id == actor.id and payload.status != MembershipStatus.ACTIVE:
                raise PermissionDenied("You cannot suspend your own membership.", code="self_change")
            if membership.role.code == SystemRole.ORG_OWNER and payload.status != MembershipStatus.ACTIVE:
                self._guard_last_owner(org, membership)
            membership.status = payload.status
        self.db.flush()
        self.db.refresh(membership)
        record_audit(
            self.db, action="staff.updated", actor=actor, organization_id=org.id, entity_type="membership",
            entity_id=membership.public_id, before=before,
            after={"role": membership.role.code, "status": membership.status, "branch_id": membership.branch_id}, meta=self.meta,
        )
        return membership

    def remove(self, org: Organization, membership_public_id: str, actor: User) -> None:
        membership = self._get(org, membership_public_id)
        if membership.user_id == actor.id:
            raise PermissionDenied("You cannot remove yourself. Transfer ownership first.", code="self_change")
        if membership.role.code == SystemRole.ORG_OWNER:
            self._guard_last_owner(org, membership)
        membership.status = MembershipStatus.REMOVED
        self.db.flush()
        record_audit(self.db, action="staff.removed", actor=actor, organization_id=org.id, entity_type="membership",
                     entity_id=membership.public_id, meta=self.meta)

    def _get(self, org: Organization, membership_public_id: str) -> OrganizationMembership:
        membership = self.memberships.get_by_public_id(membership_public_id)
        if membership is None or membership.organization_id != org.id or membership.status == MembershipStatus.REMOVED:
            raise NotFoundError("Member not found.")
        return membership

    def _guard_last_owner(self, org: Organization, membership: OrganizationMembership) -> None:
        if membership.status == MembershipStatus.ACTIVE and self.memberships.count_owners(org.id) <= 1:
            raise ConflictError("An organization must keep at least one owner.", code="last_owner")

    @staticmethod
    def _guard_owner_assignment(target_role_code: str, actor_role_code: str | None, actor: User) -> None:
        if target_role_code == SystemRole.ORG_OWNER and not (actor.is_platform_admin or actor_role_code == SystemRole.ORG_OWNER):
            raise PermissionDenied("Only an owner can assign the owner role.", code="owner_only")
