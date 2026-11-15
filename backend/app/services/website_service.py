"""Clinic website: draft editing, publishing, version history and the public read.

Publishing copies the draft into ``published`` and stores a numbered ``WebsiteVersion``; restoring copies a version
back into the draft (it goes live only when published again). Until a clinic publishes, the public site is generated
from its profile and settings, so every clinic has a working website on day one without any invented content:
sections without real content (testimonials, FAQ, gallery) are simply not shown.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import lock_row
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.time import utcnow
from app.models.auth import User
from app.models.branch import Branch
from app.models.organization import Organization
from app.models.website import Website, WebsiteVersion
from app.schemas.website import MAX_DOCUMENT_BYTES, WebsiteDocument
from app.services.audit_service import RequestMeta, record_audit
from app.services.organization_service import OrganizationService

MAX_VERSIONS = 50


def _dump(doc: WebsiteDocument) -> dict[str, Any]:
    return doc.model_dump(mode="json")


_TAGS = {"hero", "about", "doctors", "services", "categories", "features", "gallery", "testimonials", "faq", "branches", "contact", "cta", "text"}
_FIELD_NAMES = {"heading": "heading", "intro": "introduction", "url": "web address", "label": "label", "title": "title", "text": "text",
                "question": "question", "answer": "answer", "name": "name", "slug": "page address", "value": "number"}


def _where(raw: Any, loc: tuple[Any, ...]) -> str:
    """('sections', 9, 'features', 'items', 0, 'title') -> 'Facilities › item 1 › title' using the admin's own labels."""
    parts: list[str] = []
    node: Any = raw
    for key in loc:
        if isinstance(key, int) and isinstance(node, list):
            node = node[key] if key < len(node) else {}
            label = next((node.get(k) for k in ("heading", "title", "label", "question", "name") if isinstance(node, dict) and node.get(k)), None)
            parts.append(str(label)[:40] if label else f"item {key + 1}")
        elif key in _TAGS:
            continue  # the union tag Pydantic adds to the path; the node stays the same
        elif isinstance(key, str) and key not in ("sections", "items", "buttons", "pages", "images", "nav", "columns", "links", "stats", "highlights"):
            parts.append(_FIELD_NAMES.get(key, key.replace("_", " ")))
            node = node.get(key) if isinstance(node, dict) else None
        elif isinstance(key, str) and isinstance(node, dict):
            node = node.get(key)
    return " › ".join(parts)


def _friendly(msg: str) -> str:
    msg = msg.removeprefix("Value error, ")
    if msg.startswith("String should have at least 1 character"):
        return "cannot be empty"
    if msg.startswith("String should have at most"):
        return "is too long (" + msg.removeprefix("String should have at most ").rstrip(".") + " max)"
    if "#[0-9a-fA-F]{6}" in msg:
        return "must be a colour like #0F766E"
    return msg


def parse_document(raw: Any) -> WebsiteDocument:
    """Validate a stored or submitted document, turning Pydantic errors into readable messages that say where."""
    try:
        doc = raw if isinstance(raw, WebsiteDocument) else WebsiteDocument.model_validate(raw)
    except ValidationError as exc:
        errors = []
        for e in exc.errors()[:20]:
            where = _where(raw, tuple(e["loc"]))
            msg = _friendly(e["msg"])
            errors.append({"loc": [str(p) for p in e["loc"]], "msg": f"{where}: {msg}" if where else msg})
        raise ValidationFailed(errors[0]["msg"] if errors else "Invalid website content.", code="website_invalid", errors=errors) from None
    if len(json.dumps(_dump(doc))) > MAX_DOCUMENT_BYTES:
        raise ValidationFailed("The website is too large. Remove some sections, pages or images.", code="website_too_large")
    return doc


def default_document(db: Session, org: Organization) -> WebsiteDocument:
    """A starting website built only from what the clinic already entered (profile, branding, branches)."""
    settings = OrganizationService(db).get_settings(org)
    branding = settings.get("branding", {})
    has_branches = db.scalar(select(Branch.id).where(Branch.organization_id == org.id, Branch.is_active.is_(True), Branch.deleted_at.is_(None)).limit(1)) is not None
    address = org.address or {}
    address_line = ", ".join(str(address[k]) for k in ("line1", "line2", "city", "state", "postal_code") if address.get(k))
    sections: list[dict[str, Any]] = [
        {"type": "hero", "id": "home", "heading": org.name, "intro": branding.get("tagline") or (org.description or "")[:300],
         "eyebrow": "Book online in a few steps", "layout": "split"},
    ]
    if org.description:
        sections.append({"type": "about", "id": "about", "heading": f"About {org.name}", "body": org.description, "layout": "text_only"})
    sections += [
        {"type": "services", "id": "services", "heading": "Services and consultations",
         "intro": "Choose a service to see fees, duration and the next free times."},
        {"type": "doctors", "id": "doctors", "heading": "Our doctors"},
        {"type": "testimonials", "id": "reviews", "heading": "What our patients say"},
        {"type": "faq", "id": "faq", "heading": "Frequently asked questions"},
    ]
    if has_branches:
        sections.append({"type": "branches", "id": "locations", "heading": "Locations and opening hours"})
    sections.append({"type": "contact", "id": "contact", "heading": "Contact us"})
    buttons: list[dict[str, Any]] = [
        {"id": "book", "label": "Book appointment", "kind": "book", "icon": "calendar", "positions": ["header", "hero", "floating", "footer"]},
    ]
    if org.phone:
        buttons.append({"id": "call", "label": "Call the clinic", "kind": "call", "icon": "phone", "style": "outline", "positions": ["hero", "contact"]})
    nav = [{"label": "Services", "kind": "section", "target": "services"}, {"label": "Doctors", "kind": "section", "target": "doctors"}]
    if org.description:
        nav.insert(0, {"label": "About", "kind": "section", "target": "about"})
    if has_branches:
        nav.append({"label": "Locations", "kind": "section", "target": "locations"})
    nav.append({"label": "Contact", "kind": "section", "target": "contact"})
    raw = {
        "settings": {
            "site_name": org.name, "clinic_name": org.name, "tagline": branding.get("tagline", ""), "description": (org.description or "")[:600],
            "logo_url": _safe_url(org.logo_url), "primary_color": _hex(branding.get("primary_color"), "#0f766e"),
            "secondary_color": _hex(branding.get("accent_color"), "#14b8a6"), "phone": org.phone or "", "email": org.email or "",
            "address": address_line[:300],
        },
        "header": {"nav": nav},
        "sections": sections,
        "buttons": buttons,
        "footer": {"about": (org.description or "")[:600], "copyright": f"© {utcnow().year} {org.legal_name or org.name}"},
        "seo": {"title": org.name[:70], "description": (org.description or f"Book an appointment at {org.name} online.")[:170]},
    }
    try:
        return WebsiteDocument.model_validate(raw)
    except ValidationError:
        # Profile data that does not pass the website rules (e.g. an odd phone format): start from a minimal site.
        raw["settings"] = {"site_name": org.name, "clinic_name": org.name}
        raw["buttons"] = buttons[:1]
        return WebsiteDocument.model_validate(raw)


def _hex(value: Any, fallback: str) -> str:
    import re

    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def _safe_url(value: str | None) -> str:
    from app.schemas.website import safe_https_url

    try:
        return safe_https_url(value or "")
    except ValueError:
        return ""


class WebsiteService:
    def __init__(self, db: Session, org: Organization, user: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.user = user
        self.meta = meta

    # ------------------------------------------------------------------------------------------ admin side
    def _existing(self) -> Website:
        row = self._row()
        if row is None:  # _row(create=True) always returns a row; this keeps type checkers and bandit satisfied
            raise NotFoundError("Website not found.")
        return row

    def _row(self, *, create: bool = True) -> Website | None:
        row = self.db.scalar(select(Website).where(Website.organization_id == self.org.id))
        if row is None and create:
            row = Website(organization_id=self.org.id, draft=_dump(default_document(self.db, self.org)), lock_version=0)
            self.db.add(row)
            self.db.flush()
        return row

    def state(self) -> dict[str, Any]:
        row = self._existing()
        draft = parse_document(row.draft)
        published = parse_document(row.published) if row.published else None
        return {
            "draft": draft, "published": published, "lock_version": row.lock_version, "published_version": row.published_version,
            "published_at": row.published_at, "draft_updated_at": row.draft_updated_at,
            "has_unpublished_changes": published is None or _dump(draft) != _dump(published),
            "public_url_path": f"/{self.org.slug}",
        }

    def _locked(self, lock_version: int) -> Website:
        row = self._existing()
        lock_row(self.db, row)
        if row.lock_version != lock_version:
            raise ConflictError("Someone else saved the website since you opened it. Reload to see their changes.", code="website_edit_conflict")
        return row

    def save_draft(self, document: WebsiteDocument | dict[str, Any], lock_version: int) -> dict[str, Any]:
        doc = parse_document(document)
        self._check_references(doc)
        row = self._locked(lock_version)
        before = _summary(row.draft)
        row.draft = _dump(doc)
        row.lock_version += 1
        row.draft_updated_at = utcnow()
        row.draft_updated_by_id = self.user.id if self.user else None
        record_audit(self.db, action="website.draft_saved", actor=self.user, organization_id=self.org.id, entity_type="website",
                     entity_id=self.org.public_id, before=before, after=_summary(row.draft), meta=self.meta)
        self.db.flush()
        return self.state()

    def publish(self, lock_version: int, note: str = "") -> dict[str, Any]:
        row = self._locked(lock_version)
        doc = parse_document(row.draft)
        self._check_references(doc)
        now = utcnow()
        row.published = _dump(doc)
        row.published_version += 1
        row.published_at = now
        row.published_by_id = self.user.id if self.user else None
        self.db.add(WebsiteVersion(organization_id=self.org.id, version=row.published_version, content=row.published, published_at=now,
                                   published_by_id=row.published_by_id, note=note or None))
        self.db.flush()
        self._prune_versions()
        record_audit(self.db, action="website.published", actor=self.user, organization_id=self.org.id, entity_type="website",
                     entity_id=self.org.public_id, after={"version": row.published_version, "note": note, **_summary(row.published)}, meta=self.meta)
        return self.state()

    def discard_draft(self, lock_version: int) -> dict[str, Any]:
        row = self._locked(lock_version)
        if not row.published:
            raise ConflictError("Nothing has been published yet, so there is nothing to go back to.", code="website_not_published")
        row.draft = row.published
        row.lock_version += 1
        row.draft_updated_at = utcnow()
        record_audit(self.db, action="website.draft_discarded", actor=self.user, organization_id=self.org.id, entity_type="website",
                     entity_id=self.org.public_id, meta=self.meta)
        self.db.flush()
        return self.state()

    def versions(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(WebsiteVersion, User.full_name).outerjoin(User, User.id == WebsiteVersion.published_by_id)
            .where(WebsiteVersion.organization_id == self.org.id).order_by(WebsiteVersion.version.desc())
        ).all()
        return [{"version": v.version, "published_at": v.published_at, "published_by": name, "note": v.note} for v, name in rows]

    def restore(self, version: int, lock_version: int) -> dict[str, Any]:
        """Copy an earlier published version into the draft. It goes live when the draft is published."""
        row = self._locked(lock_version)
        old = self.db.scalar(select(WebsiteVersion).where(WebsiteVersion.organization_id == self.org.id, WebsiteVersion.version == version))
        if old is None:
            raise NotFoundError("That version no longer exists.", code="website_version_not_found")
        row.draft = _dump(parse_document(old.content))
        row.lock_version += 1
        row.draft_updated_at = utcnow()
        row.draft_updated_by_id = self.user.id if self.user else None
        record_audit(self.db, action="website.version_restored", actor=self.user, organization_id=self.org.id, entity_type="website",
                     entity_id=self.org.public_id, after={"restored_version": version}, meta=self.meta)
        self.db.flush()
        return self.state()

    def _prune_versions(self) -> None:
        old = self.db.scalars(
            select(WebsiteVersion).where(WebsiteVersion.organization_id == self.org.id).order_by(WebsiteVersion.version.desc()).offset(MAX_VERSIONS)
        ).all()
        for v in old:
            self.db.delete(v)

    def _check_references(self, doc: WebsiteDocument) -> None:
        """Custom page addresses must not hide a branch page (both live at /{clinic}/{name})."""
        branch_slugs = set(self.db.scalars(select(Branch.slug).where(Branch.organization_id == self.org.id, Branch.deleted_at.is_(None))))
        for page in doc.pages:
            if page.slug in branch_slugs:
                raise ValidationFailed(f"The page address “{page.slug}” is already used by a location. Choose another.", code="website_page_conflict")

    # ------------------------------------------------------------------------------------------ public side
    def public(self) -> dict[str, Any]:
        row = self._row(create=False)
        if row is not None and row.published:
            return {"document": parse_document(row.published), "published": True, "version": row.published_version}
        return {"document": default_document(self.db, self.org), "published": False, "version": 0}


def _summary(doc: dict[str, Any] | None) -> dict[str, Any]:
    """Audit-friendly summary (the full document would bloat the audit log)."""
    if not doc:
        return {}
    return {
        "sections": [f"{s.get('type')}:{s.get('id')}{'' if s.get('enabled', True) else ' (off)'}" for s in doc.get("sections", [])],
        "pages": [p.get("slug") for p in doc.get("pages", [])],
        "buttons": len(doc.get("buttons", [])),
    }
