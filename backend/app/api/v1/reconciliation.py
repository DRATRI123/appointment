"""Bank statement import and reconciliation (``reconciliation:manage``)."""
from __future__ import annotations

import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import DB, Meta, TenantContext, require_permission
from app.core.exceptions import ValidationFailed
from app.core.pagination import Page, PageMeta, PageParams, page_params
from app.schemas.common import APIModel, Message
from app.schemas.reconciliation import (
    IgnoreRequest,
    ImportRead,
    MatchCandidate,
    MatchRequest,
    ParserPreset,
    ReconciliationStats,
    StatementPreview,
    TransactionRead,
    UnmatchedReport,
)
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])
Manage = Annotated[TenantContext, Depends(require_permission("reconciliation:manage"))]


class UnmatchRequest(APIModel):
    reason: str | None = None


def _svc(db, ctx: TenantContext, meta) -> ReconciliationService:
    return ReconciliationService(db, ctx.organization, ctx.user, meta)


@router.get("/presets", response_model=list[ParserPreset], summary="Built-in column mappings for common bank CSV exports")
def presets(ctx: Manage):
    return ReconciliationService.presets()


@router.post("/preview", response_model=StatementPreview, summary="First rows of a statement, to set up a column mapping")
def preview_statement(db: DB, ctx: Manage, meta: Meta, file: UploadFile = File(...), delimiter: Annotated[str, Form(max_length=1)] = ","):
    return _svc(db, ctx, meta).preview(file.file.read(), delimiter or ",")


@router.get("/imports", response_model=list[ImportRead])
def list_imports(db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return [svc.import_read(i) for i in svc.imports()]


@router.post("/imports", response_model=ImportRead, status_code=status.HTTP_201_CREATED, summary="Import a bank statement CSV and suggest matches")
def import_statement(
    db: DB, ctx: Manage, meta: Meta, file: UploadFile = File(...),
    parser_code: Annotated[str, Form(max_length=48)] = "generic",
    mapping: Annotated[str | None, Form(max_length=4000, description="JSON column mapping overriding the preset")] = None,
    upi_account_id: Annotated[str | None, Form()] = None,
):
    try:
        mapping_dict = json.loads(mapping) if mapping else None
    except json.JSONDecodeError as exc:
        raise ValidationFailed("Column mapping is not valid JSON.", code="invalid_mapping") from exc
    if mapping_dict is not None and not isinstance(mapping_dict, dict):
        raise ValidationFailed("Column mapping must be an object.", code="invalid_mapping")
    svc = _svc(db, ctx, meta)
    imp = svc.import_statement(content=file.file.read(), file_name=file.filename or "statement.csv", parser_code=parser_code, mapping=mapping_dict, upi_account_id=upi_account_id or None)
    return svc.import_read(imp)


@router.delete("/imports/{import_id}", response_model=Message)
def delete_import(import_id: str, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    svc.delete_import(svc.get_import(import_id))
    return Message(detail="Statement removed.")


@router.get("/stats", response_model=ReconciliationStats)
def stats(db: DB, ctx: Manage, meta: Meta):
    return _svc(db, ctx, meta).stats()


@router.post("/suggest", response_model=Message, summary="Re-run match suggestions for unmatched credits (e.g. after new UTR submissions)")
def rerun(db: DB, ctx: Manage, meta: Meta):
    n = _svc(db, ctx, meta).rerun_suggestions()
    return Message(detail=f"{n} new suggestion(s).")


@router.get("/transactions", response_model=Page[TransactionRead])
def transactions(db: DB, ctx: Manage, meta: Meta, params: Annotated[PageParams, Depends(page_params)],
                 status_filter: Annotated[str | None, Query(alias="status")] = None, import_id: str | None = None,
                 search: Annotated[str | None, Query(max_length=64)] = None, from_date: date | None = None, to_date: date | None = None,
                 direction: Annotated[str | None, Query(pattern=r"^(credit|debit)$")] = "credit"):
    svc = _svc(db, ctx, meta)
    rows, total = svc.transactions(status=status_filter, import_id=import_id, search=search, from_date=from_date, to_date=to_date, direction=direction,
                                   page=params.page, page_size=params.page_size)
    return Page(data=svc.txn_reads(rows), meta=PageMeta(page=params.page, page_size=params.page_size, total=total))


@router.get("/transactions/{txn_id}/candidates", response_model=list[MatchCandidate])
def candidates(txn_id: int, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.candidates(svc.get_txn(txn_id))


@router.post("/transactions/{txn_id}/match", response_model=TransactionRead, summary="Confirm that a bank credit belongs to a payment (does not verify the payment)")
def match(txn_id: int, payload: MatchRequest, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.txn_read(svc.confirm(svc.get_txn(txn_id), payload.payment_id, payload.notes))


@router.post("/transactions/{txn_id}/unmatch", response_model=TransactionRead)
def unmatch(txn_id: int, payload: UnmatchRequest, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.txn_read(svc.unmatch(svc.get_txn(txn_id), payload.reason))


@router.post("/transactions/{txn_id}/ignore", response_model=TransactionRead, summary="Mark a credit as not related to bookings (e.g. a supplier refund)")
def ignore(txn_id: int, payload: IgnoreRequest, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.txn_read(svc.ignore(svc.get_txn(txn_id), payload.reason))


@router.post("/transactions/{txn_id}/restore", response_model=TransactionRead)
def restore(txn_id: int, db: DB, ctx: Manage, meta: Meta):
    svc = _svc(db, ctx, meta)
    return svc.txn_read(svc.restore(svc.get_txn(txn_id)))


@router.get("/report", response_model=UnmatchedReport, summary="Bank credits without a payment, and verified payments without a bank credit")
def report(db: DB, ctx: Manage, meta: Meta, from_date: date | None = None, to_date: date | None = None):
    return _svc(db, ctx, meta).report(from_date, to_date)


@router.get("/report.csv", summary="Unmatched report as CSV")
def report_csv(db: DB, ctx: Manage, meta: Meta, from_date: date | None = None, to_date: date | None = None):
    body = _svc(db, ctx, meta).report_csv(from_date, to_date)
    return Response(content="﻿" + body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="unmatched-report.csv"', "Cache-Control": "no-store"})
