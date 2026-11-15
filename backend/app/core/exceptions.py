"""Application exceptions and their HTTP mapping.

Services raise ``AppError`` subclasses; the API layer never builds HTTP errors by hand.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger

_log = get_logger("app.errors")


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, detail: str | None = None, *, code: str | None = None, errors: Any = None, headers: dict[str, str] | None = None,
                 persist: bool = False, data: dict[str, Any] | None = None):
        self.detail = detail or self.__class__.__name__
        self.headers = headers
        self.data = data  # extra fields for the error body (e.g. the token for the second sign-in step)
        # Security bookkeeping (failed-login counters, OTP attempts, duplicate-UTR flags) must survive the error:
        # the request session commits instead of rolling back when this is set.
        self.persist_changes = persist
        if code:
            self.code = code
        self.errors = errors
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationFailed(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_failed"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class PermissionDenied(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class SlotUnavailable(ConflictError):
    code = "slot_unavailable"


class DuplicateUTR(ConflictError):
    code = "duplicate_utr"


def _payload(detail: str, code: str, errors: Any = None, request: Request | None = None) -> dict:
    body: dict[str, Any] = {"detail": detail, "code": code}
    if errors is not None:
        body["errors"] = errors
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            body["request_id"] = request_id
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        from app.core.observability import security_event_for_code

        security_event_for_code(exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content={**(getattr(exc, "data", None) or {}), **_payload(exc.detail, exc.code, exc.errors, request)},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted value back: it may be a password, OTP, UTR or other personal data.
        errors = [{k: v for k, v in err.items() if k not in ("input", "ctx", "url")} for err in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_payload("Validation failed", "validation_failed", jsonable_encoder(errors), request),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_payload("Resource conflict", "integrity_error", None, request),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback server-side; the client only gets a request id to quote to support.
        _log.exception("request.unhandled_error", path=request.url.path, error=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("Something went wrong. Please try again.", "internal_error", None, request),
        )
