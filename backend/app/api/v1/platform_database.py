"""Super admin → Database: see the database, apply updates, and move from SQLite to PostgreSQL without commands."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import DB, Meta, PlatformAdmin
from app.core.exceptions import AuthenticationError, ConflictError, ValidationFailed
from app.ops import db_move
from app.schemas.common import APIModel
from app.security.passwords import verify_password
from app.services.audit_service import record_audit

router = APIRouter(prefix="/platform/database", tags=["platform"])


class TargetIn(APIModel):
    host: str = Field(default="localhost", max_length=253)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="appointments", max_length=63)
    user: str = Field(default="postgres", max_length=63)
    password: str = Field(default="", max_length=256)

    def target(self) -> db_move.Target:
        return db_move.Target(self.host.strip(), self.port, self.database.strip(), self.user.strip(), self.password)


class Confirm(APIModel):
    confirm_password: str = Field(min_length=1, max_length=256, description="Your own password, to confirm it is you")
    mfa_code: str | None = Field(default=None, max_length=16, description="Needed when your account uses two-step sign-in")


class MoveIn(Confirm):
    target: TargetIn
    i_understand: bool = Field(description="Saving is paused for a few minutes and the app must be restarted afterwards")


def _confirm(db, user, body: Confirm) -> None:
    if not user.password_hash or not verify_password(body.confirm_password, user.password_hash):
        raise AuthenticationError("Your password is not right.", code="invalid_credentials")
    if user.mfa_enabled_at is not None:
        from app.services.mfa_service import MFAService

        if not body.mfa_code or not MFAService(db)._check_code(user, body.mfa_code):
            raise AuthenticationError("Enter the current code from your authenticator app.", code="mfa_code_invalid")


def _run(fn, *args) -> Any:
    try:
        return fn(*args)
    except db_move.DatabaseTaskError as exc:
        raise ConflictError(str(exc), code="database_task") from exc


@router.get("", summary="Which database the app uses, waiting updates, and the progress of a running task")
def database_overview(_: PlatformAdmin) -> dict[str, Any]:
    return db_move.overview()


@router.post("/test", summary="Try to connect to a PostgreSQL database (nothing is changed)")
def test_postgresql(body: TargetIn, _: PlatformAdmin) -> dict[str, Any]:
    try:
        return db_move.test_target(body.target())
    except db_move.DatabaseTaskError as exc:
        raise ValidationFailed(str(exc), code="invalid_target") from exc


@router.post("/create", summary="Create the empty PostgreSQL database (if this user may)")
def create_postgresql(body: TargetIn, db: DB, user: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    result = _run(db_move.create_target_database, body.target())
    record_audit(db, action="platform.database_created", actor=user, entity_type="database", entity_id=body.database, meta=meta,
                 after={"host": body.host, "port": body.port, "database": body.database})
    return result


@router.post("/updates", summary="Apply waiting database updates (saving pauses for a moment)")
def apply_updates(body: Confirm, db: DB, user: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    _confirm(db, user, body)
    record_audit(db, action="platform.database_updates_started", actor=user, entity_type="database", entity_id="current", meta=meta)
    db.commit()  # saved before saving pauses
    _run(db_move.start_updates)
    return db_move.overview()


@router.post("/move", summary="Copy everything to PostgreSQL, check it, and switch the app to it")
def move_to_postgresql(body: MoveIn, db: DB, user: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    if not body.i_understand:
        raise ValidationFailed("Please confirm you understand saving pauses and the app must be restarted.", code="confirmation_required")
    _confirm(db, user, body)
    record_audit(db, action="platform.database_move_started", actor=user, entity_type="database", entity_id=body.target.database, meta=meta,
                 after={"host": body.target.host, "port": body.target.port, "database": body.target.database, "user": body.target.user})
    db.commit()  # in the snapshot that is copied
    _run(db_move.start_move, body.target.target())
    return db_move.overview()


@router.post("/undo", summary="Before restarting: keep using SQLite and resume saving")
def undo_move(body: Confirm, db: DB, user: PlatformAdmin, meta: Meta) -> dict[str, Any]:
    _confirm(db, user, body)
    _run(db_move.undo_switch)
    record_audit(db, action="platform.database_move_undone", actor=user, entity_type="database", entity_id="current", meta=meta)
    return db_move.overview()
