"""Idempotent seed of permissions, system roles and platform settings."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SystemRole
from app.models import Permission, Role, SystemSetting
from app.security.permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS


def seed_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code, description in PERMISSIONS.items():
        module = code.split(":", 1)[0]
        if code in existing:
            existing[code].description = description
            existing[code].module = module
        else:
            perm = Permission(code=code, module=module, description=description)
            db.add(perm)
            existing[code] = perm
    db.flush()
    return existing


def seed_system_roles(db: Session) -> dict[str, Role]:
    perms = seed_permissions(db)
    existing = {
        r.code: r
        for r in db.scalars(select(Role).where(Role.organization_id.is_(None), Role.is_system.is_(True)))
    }
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = existing.get(role_code.value)
        if role is None:
            role = Role(
                organization_id=None,
                code=role_code.value,
                name=ROLE_LABELS[role_code],
                is_system=True,
                scope="platform" if role_code == SystemRole.PLATFORM_SUPER_ADMIN else "organization",
            )
            db.add(role)
            existing[role_code.value] = role
        role.permissions = [perms[c] for c in perm_codes]
    db.flush()
    return existing


def seed_system_settings(db: Session) -> None:
    defaults = {
        "platform.name": {"value": "Appointment Platform"},
        "platform.default_timezone": {"value": "Asia/Kolkata"},
        "platform.default_currency": {"value": "INR"},
        "booking.default_hold_minutes": {"value": 10},
        "payments.default_window_minutes": {"value": 30},
    }
    existing = {s.key: s for s in db.scalars(select(SystemSetting)).all()}
    for key, value in defaults.items():
        if key not in existing:
            db.add(SystemSetting(key=key, value=value, is_public=key.startswith("platform.")))
    db.flush()


def seed_all(db: Session) -> None:
    seed_system_roles(db)
    seed_system_settings(db)
