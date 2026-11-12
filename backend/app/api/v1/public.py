"""Unauthenticated catalogue for the public booking website. Only active, bookable data is exposed."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import DB
from app.core.exceptions import NotFoundError
from app.models import Organization, ServiceCategory
from app.schemas.catalog import BranchRead, CategoryRead, ProfessionalRead, ServiceRead
from app.schemas.common import APIModel
from app.schemas.organization import OrganizationRead
from app.services.catalog_service import CatalogService, ids_to_public
from app.services.organization_service import OrganizationService

router = APIRouter(prefix="/public", tags=["public"])


class PublicOrganization(APIModel):
    organization: OrganizationRead
    branches: list[BranchRead]
    categories: list[CategoryRead]
    settings: dict


def _org(db: Session, slug: str) -> tuple[Organization, CatalogService]:
    org = OrganizationService(db).get_by_slug_public(slug)
    return org, CatalogService(db, org)


def _public_settings(db: Session, org: Organization) -> dict:
    all_settings = OrganizationService(db).get_settings(org)
    return {ns: all_settings.get(ns, {}) for ns in ("branding", "booking", "cancellation", "legal", "general")}


@router.get("/organizations/{slug}", response_model=PublicOrganization)
def organization(slug: str, db: DB) -> PublicOrganization:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import category_read

    rows = catalog.list_categories(include_inactive=False)
    parents = ids_to_public(db, ServiceCategory, {c.parent_id for c, _ in rows if c.parent_id})
    return PublicOrganization(
        organization=OrganizationRead.model_validate(org),
        branches=[BranchRead.model_validate(b) for b in catalog.list_branches(include_inactive=False)],
        categories=[category_read(c, n, parents) for c, n in rows],
        settings=_public_settings(db, org),
    )


@router.get("/organizations/{slug}/branches", response_model=list[BranchRead])
def branches(slug: str, db: DB) -> list[BranchRead]:
    _, catalog = _org(db, slug)
    return [BranchRead.model_validate(b) for b in catalog.list_branches(include_inactive=False)]


@router.get("/organizations/{slug}/services", response_model=list[ServiceRead])
def services(slug: str, db: DB, branch_id: str | None = None, category_id: str | None = None) -> list[ServiceRead]:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import service_read

    rows = catalog.list_services(include_inactive=False, branch_id=branch_id, category_id=category_id)
    return [service_read(db, org, s, catalog) for s in rows if s.is_bookable_online]


@router.get("/organizations/{slug}/services/{service_id}", response_model=ServiceRead)
def service(slug: str, service_id: str, db: DB) -> ServiceRead:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import service_read

    svc = catalog.get_service(service_id)
    if not svc.is_active or not svc.is_bookable_online:
        raise NotFoundError("Service not found.")
    return service_read(db, org, svc, catalog)


@router.get("/organizations/{slug}/professionals", response_model=list[ProfessionalRead])
def professionals(slug: str, db: DB, branch_id: str | None = None, service_id: str | None = None) -> list[ProfessionalRead]:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import professional_read

    rows = catalog.list_professionals(include_inactive=False, branch_id=branch_id, service_id=service_id)
    return [_strip_private(professional_read(db, org, p)) for p in rows if p.is_bookable_online]


@router.get("/organizations/{slug}/professionals/{professional_id}", response_model=ProfessionalRead)
def professional(slug: str, professional_id: str, db: DB) -> ProfessionalRead:
    org, catalog = _org(db, slug)
    from app.api.v1.catalog import professional_read

    pro = catalog.get_professional(professional_id)
    if not pro.is_active or not pro.is_bookable_online:
        raise NotFoundError("Professional not found.")
    return _strip_private(professional_read(db, org, pro))


def _strip_private(data: ProfessionalRead) -> ProfessionalRead:
    data.email = None
    data.phone = None
    data.user_id = None
    return data
