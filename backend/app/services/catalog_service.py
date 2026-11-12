"""Branches, categories, services, packages and professionals for one organization."""
from __future__ import annotations

import re
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.models import (
    Branch,
    Organization,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Service,
    ServiceCategory,
    ServicePackage,
    ServicePackageItem,
    ServicePricing,
    User,
)
from app.schemas.catalog import (
    BranchCreate,
    BranchUpdate,
    CategoryCreate,
    CategoryUpdate,
    PackageCreate,
    PackageUpdate,
    ProfessionalCreate,
    ProfessionalUpdate,
    ServiceCreate,
    ServiceUpdate,
)
from app.services.audit_service import RequestMeta, record_audit


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60] or "item"


class CatalogService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # ------------------------------------------------------------- helpers
    def _audit(self, action: str, entity_type: str, entity_id: str, before=None, after=None) -> None:
        record_audit(
            self.db, action=action, actor=self.actor, organization_id=self.org.id, entity_type=entity_type,
            entity_id=entity_id, before=before, after=after, meta=self.meta,
        )

    def _unique_slug(self, model, base: str, exclude_id: int | None = None) -> str:
        slug = slugify(base)
        candidate = slug
        for _ in range(20):
            stmt = select(model.id).where(model.organization_id == self.org.id, model.slug == candidate, model.deleted_at.is_(None))
            if exclude_id:
                stmt = stmt.where(model.id != exclude_id)
            if self.db.scalar(stmt) is None:
                return candidate
            candidate = f"{slug}-{secrets.token_hex(2)}"
        raise ConflictError("Could not generate a unique slug.")

    def _assert_slug_free(self, model, slug: str, exclude_id: int | None = None) -> None:
        stmt = select(model.id).where(model.organization_id == self.org.id, model.slug == slug, model.deleted_at.is_(None))
        if exclude_id:
            stmt = stmt.where(model.id != exclude_id)
        if self.db.scalar(stmt) is not None:
            raise ConflictError("This slug is already in use.", code="slug_taken")

    def _branch(self, public_id: str) -> Branch:
        b = self.db.scalar(select(Branch).where(Branch.public_id == public_id, Branch.organization_id == self.org.id, Branch.deleted_at.is_(None)))
        if b is None:
            raise NotFoundError("Branch not found.")
        return b

    def _service(self, public_id: str) -> Service:
        s = self.db.scalar(select(Service).where(Service.public_id == public_id, Service.organization_id == self.org.id, Service.deleted_at.is_(None)))
        if s is None:
            raise NotFoundError("Service not found.")
        return s

    def _category(self, public_id: str) -> ServiceCategory:
        c = self.db.scalar(select(ServiceCategory).where(ServiceCategory.public_id == public_id, ServiceCategory.organization_id == self.org.id, ServiceCategory.deleted_at.is_(None)))
        if c is None:
            raise NotFoundError("Category not found.")
        return c

    def _professional(self, public_id: str) -> Professional:
        p = self.db.scalar(
            select(Professional)
            .options(selectinload(Professional.branches), selectinload(Professional.services))
            .where(Professional.public_id == public_id, Professional.organization_id == self.org.id, Professional.deleted_at.is_(None))
        )
        if p is None:
            raise NotFoundError("Professional not found.")
        return p

    # ------------------------------------------------------------ branches
    def list_branches(self, include_inactive: bool = True) -> list[Branch]:
        stmt = select(Branch).where(Branch.organization_id == self.org.id, Branch.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(Branch.is_active.is_(True))
        return list(self.db.scalars(stmt.order_by(Branch.is_default.desc(), Branch.name)).all())

    def get_branch(self, public_id: str) -> Branch:
        return self._branch(public_id)

    def create_branch(self, payload: BranchCreate) -> Branch:
        data = payload.model_dump(exclude={"slug"})
        data["code"] = data["code"].upper()
        if self.db.scalar(select(Branch.id).where(Branch.organization_id == self.org.id, Branch.code == data["code"], Branch.deleted_at.is_(None))):
            raise ConflictError("A branch with this code already exists.", code="branch_code_taken")
        if payload.slug:
            self._assert_slug_free(Branch, payload.slug)
            slug = payload.slug
        else:
            slug = self._unique_slug(Branch, payload.name)
        has_any = self.db.scalar(select(func.count()).select_from(Branch).where(Branch.organization_id == self.org.id, Branch.deleted_at.is_(None))) or 0
        branch = Branch(organization_id=self.org.id, slug=slug, **data)
        if has_any == 0:
            branch.is_default = True
        if branch.is_default:
            self._clear_default_branch()
        self.db.add(branch)
        self.db.flush()
        self._audit("branch.created", "branch", branch.public_id, after={"name": branch.name, "code": branch.code})
        return branch

    def update_branch(self, public_id: str, payload: BranchUpdate) -> Branch:
        branch = self._branch(public_id)
        data = payload.model_dump(exclude_unset=True)
        if "code" in data:
            data["code"] = data["code"].upper()
            dup = self.db.scalar(select(Branch.id).where(Branch.organization_id == self.org.id, Branch.code == data["code"], Branch.id != branch.id, Branch.deleted_at.is_(None)))
            if dup:
                raise ConflictError("A branch with this code already exists.", code="branch_code_taken")
        before = {k: getattr(branch, k) for k in data}
        if data.get("is_default"):
            self._clear_default_branch()
        for k, v in data.items():
            setattr(branch, k, v)
        self.db.flush()
        self._audit("branch.updated", "branch", branch.public_id, before=before, after=data)
        return branch

    def delete_branch(self, public_id: str) -> None:
        from app.core.time import utcnow

        branch = self._branch(public_id)
        active_count = len(self.list_branches())
        if active_count <= 1:
            raise ConflictError("An organization needs at least one branch.", code="last_branch")
        branch.deleted_at = utcnow()
        branch.is_active = False
        branch.is_default = False
        self.db.flush()
        remaining = self.list_branches()
        if remaining and not any(b.is_default for b in remaining):
            remaining[0].is_default = True
        self._audit("branch.deleted", "branch", branch.public_id)

    def _clear_default_branch(self) -> None:
        for b in self.list_branches():
            b.is_default = False

    # ---------------------------------------------------------- categories
    def list_categories(self, include_inactive: bool = True) -> list[tuple[ServiceCategory, int]]:
        count_sq = (
            select(Service.category_id, func.count(Service.id).label("n"))
            .where(Service.organization_id == self.org.id, Service.deleted_at.is_(None))
            .group_by(Service.category_id)
            .subquery()
        )
        stmt = (
            select(ServiceCategory, func.coalesce(count_sq.c.n, 0))
            .outerjoin(count_sq, count_sq.c.category_id == ServiceCategory.id)
            .where(ServiceCategory.organization_id == self.org.id, ServiceCategory.deleted_at.is_(None))
        )
        if not include_inactive:
            stmt = stmt.where(ServiceCategory.is_active.is_(True))
        rows = self.db.execute(stmt.order_by(ServiceCategory.sort_order, ServiceCategory.name)).all()
        return [(row[0], int(row[1])) for row in rows]

    def create_category(self, payload: CategoryCreate) -> ServiceCategory:
        data = payload.model_dump(exclude={"slug", "parent_id"})
        slug = payload.slug or self._unique_slug(ServiceCategory, payload.name)
        if payload.slug:
            self._assert_slug_free(ServiceCategory, payload.slug)
        cat = ServiceCategory(organization_id=self.org.id, slug=slug, **data)
        if payload.parent_id:
            cat.parent_id = self._category(payload.parent_id).id
        self.db.add(cat)
        self.db.flush()
        self._audit("category.created", "service_category", cat.public_id, after={"name": cat.name})
        return cat

    def update_category(self, public_id: str, payload: CategoryUpdate) -> ServiceCategory:
        cat = self._category(public_id)
        data = payload.model_dump(exclude_unset=True)
        parent = data.pop("parent_id", None)
        if "parent_id" in payload.model_fields_set:
            if parent is None:
                cat.parent_id = None
            else:
                p = self._category(parent)
                if p.id == cat.id:
                    raise ValidationFailed("A category cannot be its own parent.")
                cat.parent_id = p.id
        for k, v in data.items():
            setattr(cat, k, v)
        self.db.flush()
        self._audit("category.updated", "service_category", cat.public_id, after=data)
        return cat

    def delete_category(self, public_id: str) -> None:
        from app.core.time import utcnow

        cat = self._category(public_id)
        for svc in self.db.scalars(select(Service).where(Service.category_id == cat.id)).all():
            svc.category_id = None
        cat.deleted_at = utcnow()
        cat.is_active = False
        self.db.flush()
        self._audit("category.deleted", "service_category", cat.public_id)

    # ------------------------------------------------------------ services
    def list_services(self, *, include_inactive: bool = True, category_id: str | None = None, branch_id: str | None = None, kind: str | None = None, search: str | None = None) -> list[Service]:
        stmt = (
            select(Service)
            .options(selectinload(Service.pricing), selectinload(Service.category))
            .where(Service.organization_id == self.org.id, Service.deleted_at.is_(None))
        )
        if not include_inactive:
            stmt = stmt.where(Service.is_active.is_(True))
        if category_id:
            stmt = stmt.where(Service.category_id == self._category(category_id).id)
        if kind:
            stmt = stmt.where(Service.kind == kind)
        if search:
            stmt = stmt.where(func.lower(Service.name).like(f"%{search.lower()}%"))
        services = list(self.db.scalars(stmt.order_by(Service.sort_order, Service.name)).all())
        if branch_id:
            branch = self._branch(branch_id)
            services = [s for s in services if self.service_available_at(s, branch.id)]
        return services

    @staticmethod
    def service_available_at(service: Service, branch_id: int) -> bool:
        for p in service.pricing:
            if p.branch_id == branch_id:
                return p.is_available
        return True  # no override row means available at every branch

    def get_service(self, public_id: str) -> Service:
        return self._service(public_id)

    def service_professional_ids(self, service: Service) -> list[str]:
        stmt = (
            select(Professional.public_id)
            .join(ProfessionalService, ProfessionalService.professional_id == Professional.id)
            .where(ProfessionalService.service_id == service.id, ProfessionalService.is_active.is_(True), Professional.deleted_at.is_(None))
            .distinct()
        )
        return list(self.db.scalars(stmt).all())

    def create_service(self, payload: ServiceCreate) -> Service:
        data = payload.model_dump(exclude={"slug", "category_id", "follow_up_service_id", "pricing", "professional_ids"})
        self._validate_payment_mode(data)
        slug = payload.slug or self._unique_slug(Service, payload.name)
        if payload.slug:
            self._assert_slug_free(Service, payload.slug)
        svc = Service(organization_id=self.org.id, slug=slug, currency=self.org.currency, **data)
        if payload.category_id:
            svc.category_id = self._category(payload.category_id).id
        if payload.follow_up_service_id:
            svc.follow_up_service_id = self._service(payload.follow_up_service_id).id
        self.db.add(svc)
        self.db.flush()
        self._apply_pricing(svc, payload.pricing)
        self._apply_service_professionals(svc, payload.professional_ids)
        self._audit("service.created", "service", svc.public_id, after={"name": svc.name, "price_paise": svc.price_paise})
        return svc

    def update_service(self, public_id: str, payload: ServiceUpdate) -> Service:
        svc = self._service(public_id)
        data = payload.model_dump(exclude_unset=True, exclude={"category_id", "clear_category", "follow_up_service_id", "pricing", "professional_ids"})
        merged = {**{k: getattr(svc, k) for k in ("payment_mode", "advance_amount_paise", "advance_percent", "price_paise")}, **data}
        self._validate_payment_mode(merged)
        before = {k: getattr(svc, k) for k in data}
        for k, v in data.items():
            setattr(svc, k, v)
        if payload.clear_category:
            svc.category_id = None
        elif payload.category_id:
            svc.category_id = self._category(payload.category_id).id
        if "follow_up_service_id" in payload.model_fields_set:
            if payload.follow_up_service_id is None:
                svc.follow_up_service_id = None
            else:
                target = self._service(payload.follow_up_service_id)
                if target.id == svc.id:
                    raise ValidationFailed("A service cannot be its own follow-up.")
                svc.follow_up_service_id = target.id
        if payload.pricing is not None:
            self._apply_pricing(svc, payload.pricing)
        if payload.professional_ids is not None:
            self._apply_service_professionals(svc, payload.professional_ids)
        self.db.flush()
        self.db.refresh(svc)
        self._audit("service.updated", "service", svc.public_id, before=before, after=data)
        return svc

    def delete_service(self, public_id: str) -> None:
        from app.core.time import utcnow

        svc = self._service(public_id)
        svc.deleted_at = utcnow()
        svc.is_active = False
        self.db.flush()
        self._audit("service.deleted", "service", svc.public_id)

    @staticmethod
    def _validate_payment_mode(data: dict[str, Any]) -> None:
        mode = data.get("payment_mode")
        if mode == "partial_advance" and not (data.get("advance_amount_paise") or data.get("advance_percent")):
            raise ValidationFailed("Partial advance needs an advance amount or percent.", code="advance_required")
        if mode == "free" and (data.get("price_paise") or 0) > 0:
            raise ValidationFailed("A free service must have a zero price.", code="free_price")
        if data.get("discounted_price_paise") is not None and data.get("price_paise") is not None and data["discounted_price_paise"] > data["price_paise"]:
            raise ValidationFailed("Discounted price cannot exceed the price.", code="discount_invalid")

    def _apply_pricing(self, svc: Service, pricing) -> None:
        existing = {p.branch_id: p for p in svc.pricing}
        seen: set[int] = set()
        for row in pricing:
            branch = self._branch(row.branch_id)
            seen.add(branch.id)
            values = row.model_dump(exclude={"branch_id"})
            if branch.id in existing:
                for k, v in values.items():
                    setattr(existing[branch.id], k, v)
            else:
                self.db.add(ServicePricing(service_id=svc.id, branch_id=branch.id, **values))
        for branch_id, row in existing.items():
            if branch_id not in seen:
                self.db.delete(row)
        self.db.flush()

    def _apply_service_professionals(self, svc: Service, professional_ids: list[str]) -> None:
        wanted = {self._professional(pid).id for pid in professional_ids}
        current = self.db.scalars(select(ProfessionalService).where(ProfessionalService.service_id == svc.id, ProfessionalService.branch_id.is_(None))).all()
        current_ids = {ps.professional_id for ps in current}
        for ps in current:
            if ps.professional_id not in wanted:
                self.db.delete(ps)
        for pid in wanted - current_ids:
            self.db.add(ProfessionalService(professional_id=pid, service_id=svc.id, branch_id=None))
        self.db.flush()

    # ------------------------------------------------------------ packages
    def list_packages(self, include_inactive: bool = True) -> list[ServicePackage]:
        stmt = select(ServicePackage).options(selectinload(ServicePackage.items)).where(ServicePackage.organization_id == self.org.id, ServicePackage.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(ServicePackage.is_active.is_(True))
        return list(self.db.scalars(stmt.order_by(ServicePackage.name)).all())

    def create_package(self, payload: PackageCreate) -> ServicePackage:
        pkg = ServicePackage(organization_id=self.org.id, **payload.model_dump(exclude={"items"}))
        self.db.add(pkg)
        self.db.flush()
        self._apply_package_items(pkg, payload.items)
        self._audit("package.created", "service_package", pkg.public_id, after={"name": pkg.name})
        return pkg

    def update_package(self, public_id: str, payload: PackageUpdate) -> ServicePackage:
        pkg = self.db.scalar(select(ServicePackage).where(ServicePackage.public_id == public_id, ServicePackage.organization_id == self.org.id, ServicePackage.deleted_at.is_(None)))
        if pkg is None:
            raise NotFoundError("Package not found.")
        for k, v in payload.model_dump(exclude_unset=True, exclude={"items"}).items():
            setattr(pkg, k, v)
        if payload.items is not None:
            self._apply_package_items(pkg, payload.items)
        self.db.flush()
        self.db.refresh(pkg)
        self._audit("package.updated", "service_package", pkg.public_id)
        return pkg

    def delete_package(self, public_id: str) -> None:
        from app.core.time import utcnow

        pkg = self.db.scalar(select(ServicePackage).where(ServicePackage.public_id == public_id, ServicePackage.organization_id == self.org.id, ServicePackage.deleted_at.is_(None)))
        if pkg is None:
            raise NotFoundError("Package not found.")
        pkg.deleted_at = utcnow()
        pkg.is_active = False
        self.db.flush()
        self._audit("package.deleted", "service_package", pkg.public_id)

    def _apply_package_items(self, pkg: ServicePackage, items) -> None:
        for item in list(pkg.items):
            self.db.delete(item)
        self.db.flush()
        seen = set()
        for item in items:
            svc = self._service(item.service_id)
            if svc.id in seen:
                raise ValidationFailed("Duplicate service in package.", code="duplicate_item")
            seen.add(svc.id)
            self.db.add(ServicePackageItem(package_id=pkg.id, service_id=svc.id, quantity=item.quantity))
        self.db.flush()

    # ------------------------------------------------------- professionals
    def list_professionals(self, *, include_inactive: bool = True, branch_id: str | None = None, service_id: str | None = None, search: str | None = None) -> list[Professional]:
        stmt = (
            select(Professional)
            .options(selectinload(Professional.branches), selectinload(Professional.services))
            .where(Professional.organization_id == self.org.id, Professional.deleted_at.is_(None))
        )
        if not include_inactive:
            stmt = stmt.where(Professional.is_active.is_(True))
        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(func.lower(Professional.display_name).like(like) | func.lower(Professional.specialization).like(like))
        pros = list(self.db.scalars(stmt.order_by(Professional.sort_order, Professional.display_name)).all())
        if branch_id:
            bid = self._branch(branch_id).id
            pros = [p for p in pros if any(pb.branch_id == bid and pb.is_active for pb in p.branches)]
        if service_id:
            sid = self._service(service_id).id
            pros = [p for p in pros if any(ps.service_id == sid and ps.is_active for ps in p.services)]
        return pros

    def get_professional(self, public_id: str) -> Professional:
        return self._professional(public_id)

    def create_professional(self, payload: ProfessionalCreate) -> Professional:
        data = payload.model_dump(exclude={"slug", "user_id", "branches", "services"})
        slug = payload.slug or self._unique_slug(Professional, payload.display_name)
        if payload.slug:
            self._assert_slug_free(Professional, payload.slug)
        pro = Professional(organization_id=self.org.id, slug=slug, **data)
        if payload.user_id:
            pro.user_id = self._resolve_user(payload.user_id).id
        self.db.add(pro)
        self.db.flush()
        self._apply_professional_branches(pro, payload.branches)
        self._apply_professional_services(pro, payload.services)
        self.db.refresh(pro)
        self._audit("professional.created", "professional", pro.public_id, after={"display_name": pro.display_name})
        return pro

    def update_professional(self, public_id: str, payload: ProfessionalUpdate) -> Professional:
        pro = self._professional(public_id)
        data = payload.model_dump(exclude_unset=True, exclude={"user_id", "clear_user", "branches", "services"})
        before = {k: getattr(pro, k) for k in data}
        for k, v in data.items():
            setattr(pro, k, v)
        if payload.clear_user:
            pro.user_id = None
        elif payload.user_id:
            pro.user_id = self._resolve_user(payload.user_id).id
        if payload.branches is not None:
            self._apply_professional_branches(pro, payload.branches)
        if payload.services is not None:
            self._apply_professional_services(pro, payload.services)
        self.db.flush()
        self.db.refresh(pro)
        self._audit("professional.updated", "professional", pro.public_id, before=before, after=data)
        return pro

    def delete_professional(self, public_id: str) -> None:
        from app.core.time import utcnow

        pro = self._professional(public_id)
        pro.deleted_at = utcnow()
        pro.is_active = False
        pro.is_bookable_online = False
        self.db.flush()
        self._audit("professional.deleted", "professional", pro.public_id)

    def _resolve_user(self, user_public_id: str) -> User:
        from app.models import OrganizationMembership

        user = self.db.scalar(select(User).where(User.public_id == user_public_id, User.deleted_at.is_(None)))
        if user is None:
            raise NotFoundError("User not found.")
        member = self.db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == self.org.id,
                OrganizationMembership.status.in_(["active", "invited"]),
            )
        )
        if member is None:
            raise ValidationFailed("Add this person as staff (doctor/professional role) before linking.", code="not_staff")
        return user

    def _apply_professional_branches(self, pro: Professional, rows) -> None:
        existing = {pb.branch_id: pb for pb in pro.branches}
        seen: set[int] = set()
        for row in rows:
            branch = self._branch(row.branch_id)
            seen.add(branch.id)
            values = row.model_dump(exclude={"branch_id"})
            if branch.id in existing:
                for k, v in values.items():
                    setattr(existing[branch.id], k, v)
            else:
                self.db.add(ProfessionalBranch(professional_id=pro.id, branch_id=branch.id, **values))
        for bid, pb in existing.items():
            if bid not in seen:
                self.db.delete(pb)
        self.db.flush()

    def _apply_professional_services(self, pro: Professional, rows) -> None:
        existing = {(ps.service_id, ps.branch_id): ps for ps in pro.services}
        seen: set[tuple[int, int | None]] = set()
        for row in rows:
            svc = self._service(row.service_id)
            bid = self._branch(row.branch_id).id if row.branch_id else None
            key = (svc.id, bid)
            if key in seen:
                raise ValidationFailed("Duplicate service assignment.", code="duplicate_assignment")
            seen.add(key)
            values = row.model_dump(exclude={"service_id", "branch_id"})
            if key in existing:
                for k, v in values.items():
                    setattr(existing[key], k, v)
            else:
                self.db.add(ProfessionalService(professional_id=pro.id, service_id=svc.id, branch_id=bid, **values))
        for key, ps in existing.items():
            if key not in seen:
                self.db.delete(ps)
        self.db.flush()


# ------------------------------------------------------------- serializers
def branch_names(db: Session, org_id: int) -> dict[int, str]:
    return dict(db.execute(select(Branch.id, Branch.name).where(Branch.organization_id == org_id)).all())


def service_names(db: Session, org_id: int) -> dict[int, str]:
    return dict(db.execute(select(Service.id, Service.name).where(Service.organization_id == org_id)).all())


def ids_to_public(db: Session, model, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(db.execute(select(model.id, model.public_id).where(model.id.in_(ids))).all())
