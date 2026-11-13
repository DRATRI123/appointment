from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class ParserPreset(APIModel):
    code: str
    label: str
    mapping: dict[str, Any]


class StatementPreview(APIModel):
    rows: list[list[str]]
    total_lines: int
    detected_preset: str | None


class ImportRead(APIModel):
    id: str
    file_name: str
    parser_code: str
    status: str
    statement_from: date | None
    statement_to: date | None
    total_rows: int
    matched_rows: int
    suggested_rows: int = 0
    duplicate_rows: int
    skipped_rows: int
    skipped: list[dict[str, Any]] | None = None
    upi_account_name: str | None
    uploaded_by_name: str | None
    error_message: str | None
    created_at: datetime


class MatchCandidate(APIModel):
    payment_id: str
    payment_reference: str
    payment_status: str
    amount_paise: int
    customer_name: str | None
    appointment_reference: str | None
    latest_utr: str | None
    submitted_at: datetime | None
    score: int
    reasons: list[str]


class TransactionRead(APIModel):
    id: int
    import_id: str
    transaction_date: date
    value_date: date | None
    description: str | None
    utr: str | None
    payer_vpa: str | None
    amount_paise: int
    direction: str
    balance_paise: int | None
    match_status: str
    match_confidence: int | None
    matched_payment_id: str | None
    matched_payment_reference: str | None
    matched_payment_status: str | None
    matched_customer_name: str | None
    matched_by_name: str | None
    matched_at: datetime | None
    notes: str | None
    duplicate_utr: bool = False


class MatchRequest(APIModel):
    payment_id: str
    notes: str | None = Field(default=None, max_length=1000)


class IgnoreRequest(APIModel):
    reason: str = Field(min_length=3, max_length=500)


class ReconciliationStats(APIModel):
    unmatched: int
    suggested: int
    matched: int
    ignored: int
    unmatched_amount_paise: int
    verified_without_bank_match: int


class UnmatchedPayment(APIModel):
    payment_id: str
    payment_reference: str
    status: str
    method: str
    amount_paise: int
    verified_amount_paise: int | None
    latest_utr: str | None
    customer_name: str | None
    verified_at: datetime | None
    submitted_at: datetime | None


class UnmatchedReport(APIModel):
    bank_credits: list[TransactionRead]
    payments: list[UnmatchedPayment]


class BankEvidence(APIModel):
    """Bank statement lines that back (or might back) a payment, shown to the verifier."""

    transaction_id: int
    transaction_date: date
    amount_paise: int
    utr: str | None
    description: str | None
    match_status: str
    matched_to_this_payment: bool
    matched_payment_reference: str | None
