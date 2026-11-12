"""Application exceptions and their HTTP mapping.

Services raise ``AppError`` subclasses; the API layer never builds HTTP errors by hand.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, detail: str | None = None, *, code: str | None = None, errors: Any = None):
        self.detail = detail or self.__class__.__name__
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
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.detail, exc.code, exc.errors, request),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_payload("Validation failed", "validation_failed", exc.errors(), request),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_payload("Resource conflict", "integrity_error", None, request),
        )
