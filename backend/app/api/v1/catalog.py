"""Branches, categories, services, packages and professionals (tenant routes via X-Organization-Id)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.models import Branch, Organization, Professional, Service, ServiceCategory, ServicePackage
from app.schemas.catalog import (
    BranchCreate,
    BranchRead,
    BranchUpdate,
    CategoryBase,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PackageCreate,
    PackageItemRead,
    PackageRead,
    PackageUpdate,
    ProfessionalBase,
    ProfessionalBranchRead,
    ProfessionalCreate,
    ProfessionalRead,
    ProfessionalServiceRead,
    ProfessionalUpdate,
    ServiceBase,
    ServiceCreate,
    ServicePricingRead,
    ServiceRead,
    ServiceUpdate,
)
from app.schemas.common import Message
from app.services.catalog_service import CatalogService, branch_names, ids_to_public, service_names

router = APIRouter(tags=["catalog"])

ReadBranches = Annotated[TenantContext, Depends(require_permission("branches:read"))]
WriteBranches = Annotated[TenantContext, Depends(require_permission("branches:write"))]
ReadServices = Annotated[TenantContext, Depends(require_permission("services:read"))]
WriteServices = Annotated[TenantContext, Depends(require_permission("services:write"))]
ReadPros = Annotated[TenantContext, Depends(require_permission("professionals:read"))]
WritePros = Annotated[TenantContext, Depends(require_permission("professionals:write"))]


def _svc(db: Session, ctx: TenantContext, meta) -> CatalogService:
    return CatalogService(db, ctx.organization, ctx.user, meta)


# ------------------------------------------------------------- serializers
def _fields(obj, base_cls, extra: tuple[str, ...] = ()) -> dict:
    """Plain dict of base-schema fields from an ORM object (never the integer FK columns)."""
    return {k: getattr(obj, k) for k in list(base_cls.model_fields) + list(extra)}


def category_read(cat: ServiceCategory, count: int, parents: dict[int, str]) -> CategoryRead:
    return CategoryRead(
        **_fields(cat, CategoryBase, ("slug",)), id=cat.public_id, service_count=count,
        parent_id=parents.get(cat.parent_id) if cat.parent_id else None,
    )


def service_read(db: Session, org: Organization, svc: Service, catalog: CatalogService) -> ServiceRead:
    bnames = branch_names(db, org.id)
    bpub = ids_to_public(db, Branch, {p.branch_id for p in svc.pricing})
    pricing = [
        ServicePricingRead(branch_id=bpub[p.branch_id], branch_name=bnames.get(p.branch_id), price_paise=p.price_paise,
                           discounted_price_paise=p.discounted_price_paise, advance_amount_paise=p.advance_amount_paise, is_available=p.is_available)
        for p in svc.pricing if p.branch_id in bpub
    ]
    follow_up = ids_to_public(db, Service, {svc.follow_up_service_id}).get(svc.follow_up_service_id) if svc.follow_up_service_id else None
    return ServiceRead(
        **_fields(svc, ServiceBase, ("slug", "currency", "created_at", "updated_at")), id=svc.public_id,
        category_id=svc.category.public_id if svc.category else None, category_name=svc.category.name if svc.category else None,
        follow_up_service_id=follow_up, pricing=pricing, professional_ids=catalog.service_professional_ids(svc),
    )


def professional_read(db: Session, org: Organization, pro: Professional) -> ProfessionalRead:
    data = ProfessionalRead(**_fields(pro, ProfessionalBase, ("slug", "created_at", "updated_at")), id=pro.public_id)
    bnames = branch_names(db, org.id)
    snames = service_names(db, org.id)
    bpub = ids_to_public(db, Branch, {pb.branch_id for pb in pro.branches} | {ps.branch_id for ps in pro.services if ps.branch_id})
    spub = ids_to_public(db, Service, {ps.service_id for ps in pro.services})
    data.branches = [
        ProfessionalBranchRead(branch_id=bpub[pb.branch_id], branch_name=bnames.get(pb.branch_id), fee_paise=pb.fee_paise, duration_minutes=pb.duration_minutes,
                               buffer_minutes=pb.buffer_minutes, room_label=pb.room_label, is_active=pb.is_active)
        for pb in pro.branches if pb.branch_id in bpub
    ]
    data.services = [
        ProfessionalServiceRead(service_id=spub[ps.service_id], service_name=snames.get(ps.service_id), branch_id=bpub.get(ps.branch_id) if ps.branch_id else None,
                                fee_override_paise=ps.fee_override_paise, duration_override_minutes=ps.duration_override_minutes, is_active=ps.is_active)
        for ps in pro.services if ps.service_id in spub
    ]
    if pro.user_id:
        from app.models import User

        data.user_id = ids_to_public(db, User, {pro.user_id}).get(pro.user_id)
    return data


def package_read(db: Session, org: Organization, pkg: ServicePackage) -> PackageRead:
    data = PackageRead(id=pkg.public_id, name=pkg.name, description=pkg.description, price_paise=pkg.price_paise,
                       validity_days=pkg.validity_days, is_active=pkg.is_active, created_at=pkg.created_at)
    snames = service_names(db, org.id)
    spub = ids_to_public(db, Service, {i.service_id for i in pkg.items})
    data.items = [PackageItemRead(service_id=spub[i.service_id], service_name=snames.get(i.service_id), quantity=i.quantity) for i in pkg.items if i.service_id in spub]
    return data


# ---------------------------------------------------------------- branches
@router.get("/branches", response_model=list[BranchRead])
def list_branches(db: DB, ctx: ReadBranches, meta: Meta, include_inactive: bool = True) -> list[BranchRead]:
    return [BranchRead.model_validate(b) for b in _svc(db, ctx, meta).list_branches(include_inactive)]


@router.post("/branches", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(payload: BranchCreate, db: DB, ctx: WriteBranches, meta: Meta) -> BranchRead:
    return BranchRead.model_validate(_svc(db, ctx, meta).create_branch(payload))


@router.get("/branches/{branch_id}", response_model=BranchRead)
def get_branch(branch_id: str, db: DB, ctx: ReadBranches, meta: Meta) -> BranchRead:
    return BranchRead.model_validate(_svc(db, ctx, meta).get_branch(branch_id))


@router.patch("/branches/{branch_id}", response_model=BranchRead)
def update_branch(branch_id: str, payload: BranchUpdate, db: DB, ctx: WriteBranches, meta: Meta) -> BranchRead:
    return BranchRead.model_validate(_svc(db, ctx, meta).update_branch(branch_id, payload))


@router.delete("/branches/{branch_id}", response_model=Message)
def delete_branch(branch_id: str, db: DB, ctx: WriteBranches, meta: Meta) -> Message:
    _svc(db, ctx, meta).delete_branch(branch_id)
    return Message(detail="Branch deleted.")


# -------------------------------------------------------------- categories
@router.get("/service-categories", response_model=list[CategoryRead])
def list_categories(db: DB, ctx: ReadServices, meta: Meta, include_inactive: bool = True) -> list[CategoryRead]:
    rows = _svc(db, ctx, meta).list_categories(include_inactive)
    parents = ids_to_public(db, ServiceCategory, {c.parent_id for c, _ in rows if c.parent_id})
    return [category_read(c, n, parents) for c, n in rows]


@router.post("/service-categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DB, ctx: WriteServices, meta: Meta) -> CategoryRead:
    cat = _svc(db, ctx, meta).create_category(payload)
    return category_read(cat, 0, ids_to_public(db, ServiceCategory, {cat.parent_id} if cat.parent_id else set()))


@router.patch("/service-categories/{category_id}", response_model=CategoryRead)
def update_category(category_id: str, payload: CategoryUpdate, db: DB, ctx: WriteServices, meta: Meta) -> CategoryRead:
    service = _svc(db, ctx, meta)
    cat = service.update_category(category_id, payload)
    count = next((n for c, n in service.list_categories() if c.id == cat.id), 0)
    return category_read(cat, count, ids_to_public(db, ServiceCategory, {cat.parent_id} if cat.parent_id else set()))


@router.delete("/service-categories/{category_id}", response_model=Message)
def delete_category(category_id: str, db: DB, ctx: WriteServices, meta: Meta) -> Message:
    _svc(db, ctx, meta).delete_category(category_id)
    return Message(detail="Category deleted. Its services are now uncategorised.")


# ---------------------------------------------------------------- services
@router.get("/services", response_model=list[ServiceRead])
def list_services(
    db: DB, ctx: ReadServices, meta: Meta, include_inactive: bool = True,
    category_id: str | None = None, branch_id: str | None = None, kind: str | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ServiceRead]:
    service = _svc(db, ctx, meta)
    return [service_read(db, ctx.organization, s, service) for s in service.list_services(include_inactive=include_inactive, category_id=category_id, branch_id=branch_id, kind=kind, search=search)]


@router.post("/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, db: DB, ctx: WriteServices, meta: Meta) -> ServiceRead:
    service = _svc(db, ctx, meta)
    svc = service.create_service(payload)
    db.refresh(svc)
    return service_read(db, ctx.organization, svc, service)


@router.get("/services/{service_id}", response_model=ServiceRead)
def get_service(service_id: str, db: DB, ctx: ReadServices, meta: Meta) -> ServiceRead:
    service = _svc(db, ctx, meta)
    return service_read(db, ctx.organization, service.get_service(service_id), service)


@router.patch("/services/{service_id}", response_model=ServiceRead)
def update_service(service_id: str, payload: ServiceUpdate, db: DB, ctx: WriteServices, meta: Meta) -> ServiceRead:
    service = _svc(db, ctx, meta)
    return service_read(db, ctx.organization, service.update_service(service_id, payload), service)


@router.delete("/services/{service_id}", response_model=Message)
def delete_service(service_id: str, db: DB, ctx: WriteServices, meta: Meta) -> Message:
    _svc(db, ctx, meta).delete_service(service_id)
    return Message(detail="Service deleted.")


# ---------------------------------------------------------------- packages
@router.get("/service-packages", response_model=list[PackageRead])
def list_packages(db: DB, ctx: ReadServices, meta: Meta, include_inactive: bool = True) -> list[PackageRead]:
    return [package_read(db, ctx.organization, p) for p in _svc(db, ctx, meta).list_packages(include_inactive)]


@router.post("/service-packages", response_model=PackageRead, status_code=status.HTTP_201_CREATED)
def create_package(payload: PackageCreate, db: DB, ctx: WriteServices, meta: Meta) -> PackageRead:
    pkg = _svc(db, ctx, meta).create_package(payload)
    db.refresh(pkg)
    return package_read(db, ctx.organization, pkg)


@router.patch("/service-packages/{package_id}", response_model=PackageRead)
def update_package(package_id: str, payload: PackageUpdate, db: DB, ctx: WriteServices, meta: Meta) -> PackageRead:
    return package_read(db, ctx.organization, _svc(db, ctx, meta).update_package(package_id, payload))


@router.delete("/service-packages/{package_id}", response_model=Message)
def delete_package(package_id: str, db: DB, ctx: WriteServices, meta: Meta) -> Message:
    _svc(db, ctx, meta).delete_package(package_id)
    return Message(detail="Package deleted.")


# ----------------------------------------------------------- professionals
@router.get("/professionals", response_model=list[ProfessionalRead])
def list_professionals(
    db: DB, ctx: ReadPros, meta: Meta, include_inactive: bool = True,
    branch_id: str | None = None, service_id: str | None = None, search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ProfessionalRead]:
    return [professional_read(db, ctx.organization, p) for p in _svc(db, ctx, meta).list_professionals(include_inactive=include_inactive, branch_id=branch_id, service_id=service_id, search=search)]


@router.post("/professionals", response_model=ProfessionalRead, status_code=status.HTTP_201_CREATED)
def create_professional(payload: ProfessionalCreate, db: DB, ctx: WritePros, meta: Meta) -> ProfessionalRead:
    return professional_read(db, ctx.organization, _svc(db, ctx, meta).create_professional(payload))


@router.get("/professionals/{professional_id}", response_model=ProfessionalRead)
def get_professional(professional_id: str, db: DB, ctx: ReadPros, meta: Meta) -> ProfessionalRead:
    return professional_read(db, ctx.organization, _svc(db, ctx, meta).get_professional(professional_id))


@router.patch("/professionals/{professional_id}", response_model=ProfessionalRead)
def update_professional(professional_id: str, payload: ProfessionalUpdate, db: DB, ctx: WritePros, meta: Meta) -> ProfessionalRead:
    return professional_read(db, ctx.organization, _svc(db, ctx, meta).update_professional(professional_id, payload))


@router.delete("/professionals/{professional_id}", response_model=Message)
def delete_professional(professional_id: str, db: DB, ctx: WritePros, meta: Meta) -> Message:
    _svc(db, ctx, meta).delete_professional(professional_id)
    return Message(detail="Professional deleted.")
