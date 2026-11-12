from __future__ import annotations

from sqlalchemy import select

from app.models import Organization, OrganizationDomain, OrganizationMembership, OrganizationSetting, Role
from app.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    def get_by_slug(self, slug: str) -> Organization | None:
        return self.db.scalar(select(Organization).where(Organization.slug == slug))

    def get_by_code(self, code: str) -> Organization | None:
        return self.db.scalar(select(Organization).where(Organization.code == code))

    def get_setting(self, organization_id: int, namespace: str, key: str) -> OrganizationSetting | None:
        return self.db.scalar(
            select(OrganizationSetting).where(
                OrganizationSetting.organization_id == organization_id,
                OrganizationSetting.namespace == namespace,
                OrganizationSetting.key == key,
            )
        )

    def list_settings(self, organization_id: int, namespace: str | None = None) -> list[OrganizationSetting]:
        stmt = select(OrganizationSetting).where(OrganizationSetting.organization_id == organization_id)
        if namespace:
            stmt = stmt.where(OrganizationSetting.namespace == namespace)
        return list(self.db.scalars(stmt.order_by(OrganizationSetting.namespace, OrganizationSetting.key)).all())

    def list_domains(self, organization_id: int) -> list[OrganizationDomain]:
        return list(
            self.db.scalars(
                select(OrganizationDomain)
                .where(OrganizationDomain.organization_id == organization_id)
                .order_by(OrganizationDomain.is_primary.desc(), OrganizationDomain.domain)
            ).all()
        )

    def get_domain(self, domain: str) -> OrganizationDomain | None:
        return self.db.scalar(select(OrganizationDomain).where(OrganizationDomain.domain == domain))


class MembershipRepository(BaseRepository[OrganizationMembership]):
    model = OrganizationMembership

    def list_for_user(self, user_id: int, active_only: bool = True) -> list[OrganizationMembership]:
        stmt = select(OrganizationMembership).where(OrganizationMembership.user_id == user_id)
        if active_only:
            stmt = stmt.where(OrganizationMembership.status == "active")
        return list(self.db.scalars(stmt.order_by(OrganizationMembership.id)).all())

    def list_for_organization(self, organization_id: int) -> list[OrganizationMembership]:
        stmt = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status != "removed",
            )
            .order_by(OrganizationMembership.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_for_user_in_org(self, user_id: int, organization_id: int) -> OrganizationMembership | None:
        stmt = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == "active",
            )
            .order_by(OrganizationMembership.id)
        )
        return self.db.scalars(stmt).first()

    def count_owners(self, organization_id: int) -> int:
        stmt = (
            select(OrganizationMembership)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == "active",
                Role.code == "org_owner",
            )
        )
        return len(self.db.scalars(stmt).all())


class RoleRepository(BaseRepository[Role]):
    model = Role

    def get_system_role(self, code: str) -> Role | None:
        return self.db.scalar(select(Role).where(Role.organization_id.is_(None), Role.code == code))

    def get_role_for_org(self, organization_id: int, code: str) -> Role | None:
        """Custom organization role first, then system role."""
        custom = self.db.scalar(select(Role).where(Role.organization_id == organization_id, Role.code == code))
        return custom or self.get_system_role(code)

    def list_for_org(self, organization_id: int) -> list[Role]:
        stmt = (
            select(Role)
            .where(
                (Role.organization_id == organization_id)
                | ((Role.organization_id.is_(None)) & (Role.code != "platform_super_admin"))
            )
            .order_by(Role.is_system.desc(), Role.id)
        )
        return list(self.db.scalars(stmt).all())
