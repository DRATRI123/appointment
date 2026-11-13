"""Bank statement parsing and payment matching.

Parsers are configuration, not code: every bank format is a ``ParserConfig`` (column names, date formats,
amount style). Presets cover common Indian bank CSV exports; organizations can supply their own mapping.
Matching only *suggests*. Linking a bank credit to a payment, and verifying it, are staff actions.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

UTR_PATTERNS = [
    re.compile(r"(?:UPI|IMPS|NEFT|RTGS)[/\-: ]+(?:[A-Z]{2,6}[/\-: ]+)?(\d{12})\b", re.I),
    re.compile(r"\b(\d{12})\b"),
    re.compile(r"\b([A-Z]{4}[A-Z0-9]{1}\d{10,16})\b"),  # NEFT/RTGS references such as HDFCN52026111300012
]
VPA_RE = re.compile(r"(?<![A-Za-z0-9._])([A-Za-z0-9._]{2,64}@[A-Za-z][A-Za-z0-9]{1,30})\b")


@dataclass
class ParserConfig:
    date_column: str
    description_column: str
    credit_column: str | None = None  # separate deposit column
    debit_column: str | None = None
    amount_column: str | None = None  # single signed/flagged amount column
    type_column: str | None = None  # "CR"/"DR" flag for single-amount layouts
    reference_column: str | None = None  # bank's reference / cheque column (often holds the UTR)
    value_date_column: str | None = None
    balance_column: str | None = None
    date_formats: list[str] = field(default_factory=lambda: ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y-%m-%d", "%d-%b-%y", "%d.%m.%Y"])
    delimiter: str = ","
    include_debits: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParserConfig:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and v not in (None, "")}
        if "date_column" not in known or "description_column" not in known:
            raise ValueError("Mapping needs date_column and description_column.")
        if not (known.get("credit_column") or known.get("amount_column")):
            raise ValueError("Mapping needs credit_column (deposits) or amount_column.")
        return cls(**known)


PRESETS: dict[str, dict[str, Any]] = {
    "hdfc": {"label": "HDFC Bank (CSV export)", "date_column": "Date", "description_column": "Narration", "reference_column": "Chq./Ref.No.",
             "value_date_column": "Value Dt", "debit_column": "Withdrawal Amt.", "credit_column": "Deposit Amt.", "balance_column": "Closing Balance"},
    "icici": {"label": "ICICI Bank", "date_column": "Transaction Date", "description_column": "Transaction Remarks", "reference_column": "Cheque Number",
              "value_date_column": "Value Date", "debit_column": "Withdrawal Amount (INR )", "credit_column": "Deposit Amount (INR )", "balance_column": "Balance (INR )"},
    "sbi": {"label": "State Bank of India", "date_column": "Txn Date", "description_column": "Description", "reference_column": "Ref No./Cheque No.",
            "value_date_column": "Value Date", "debit_column": "Debit", "credit_column": "Credit", "balance_column": "Balance"},
    "axis": {"label": "Axis Bank", "date_column": "Tran Date", "description_column": "PARTICULARS", "reference_column": "CHQNO",
             "debit_column": "DR", "credit_column": "CR", "balance_column": "BAL"},
    "kotak": {"label": "Kotak Mahindra Bank", "date_column": "Transaction Date", "description_column": "Description", "reference_column": "Chq / Ref No.",
              "amount_column": "Amount", "type_column": "Dr / Cr", "balance_column": "Balance"},
    "generic": {"label": "Generic (Date, Description, Credit, Debit, Balance)", "date_column": "Date", "description_column": "Description",
                "reference_column": "Reference", "debit_column": "Debit", "credit_column": "Credit", "balance_column": "Balance"},
}


@dataclass
class ParsedRow:
    transaction_date: date
    value_date: date | None
    description: str
    utr: str | None
    payer_vpa: str | None
    amount_paise: int
    direction: str
    balance_paise: int | None
    raw: dict[str, str]
    fingerprint: str = ""


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    skipped: list[dict[str, Any]]
    header: list[str]


def to_paise(value: str | None) -> int | None:
    if value is None:
        return None
    v = value.strip().replace(",", "").replace("₹", "").replace("INR", "").replace("Rs.", "").strip()
    if v in ("", "-", "0", "0.0", "0.00"):
        return None if v in ("", "-") else 0
    neg = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    for suffix in ("CR", "Cr", "DR", "Dr"):
        if v.endswith(suffix):
            v = v[: -len(suffix)].strip()
    try:
        d = Decimal(v)
    except InvalidOperation as exc:
        raise ValueError(f"Not an amount: {value!r}") from exc
    paise = int((d * 100).quantize(Decimal("1")))
    return -paise if neg else paise


def parse_date(value: str, formats: list[str]) -> date:
    v = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date {value!r}")


def extract_utr(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        for pattern in UTR_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(1).upper()
    return None


def extract_vpa(text: str | None) -> str | None:
    if not text:
        return None
    m = VPA_RE.search(text)
    return m.group(1).lower() if m else None


def squash(text: str | None) -> str:
    """Upper-case alphanumerics only: bank narrations break references with spaces, dashes and slashes."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _find_header(lines: list[list[str]], cfg: ParserConfig) -> int:
    """Bank exports often start with account details; find the row that holds the mapped column names."""
    wanted = {cfg.date_column.strip().lower(), cfg.description_column.strip().lower()}
    for i, row in enumerate(lines[:40]):
        cells = {c.strip().lower() for c in row}
        if wanted <= cells:
            return i
    raise ValueError(f"Could not find the header row with '{cfg.date_column}' and '{cfg.description_column}'. Check the column mapping.")


def parse_csv(content: bytes, cfg: ParserConfig) -> ParseResult:
    text = content.decode("utf-8-sig", errors="replace")
    lines = list(csv.reader(io.StringIO(text), delimiter=cfg.delimiter))
    h = _find_header(lines, cfg)
    header = [c.strip() for c in lines[h]]
    index = {name.lower(): i for i, name in enumerate(header)}

    def col(row: list[str], name: str | None) -> str | None:
        if not name:
            return None
        i = index.get(name.strip().lower())
        return row[i].strip() if i is not None and i < len(row) else None

    rows: list[ParsedRow] = []
    skipped: list[dict[str, Any]] = []
    for line_no, row in enumerate(lines[h + 1:], start=h + 2):
        if not any(c.strip() for c in row):
            continue
        raw = {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
        try:
            d_raw = col(row, cfg.date_column)
            if not d_raw or set(d_raw) <= {"*", "-"}:
                continue  # separator/footer lines
            txn_date = parse_date(d_raw, cfg.date_formats)
            desc = col(row, cfg.description_column) or ""
            credit = debit = None
            if cfg.credit_column:
                credit = to_paise(col(row, cfg.credit_column))
                debit = to_paise(col(row, cfg.debit_column)) if cfg.debit_column else None
            else:
                amount = to_paise(col(row, cfg.amount_column))
                flag = (col(row, cfg.type_column) or "").upper()
                amt_raw = (col(row, cfg.amount_column) or "").upper()
                if amount is None:
                    raise ValueError("Missing amount")
                if flag.startswith("D") or amt_raw.endswith("DR") or amount < 0:
                    debit = abs(amount)
                else:
                    credit = amount
            if credit and credit > 0:
                amount_paise, direction = credit, "credit"
            elif debit and debit > 0:
                amount_paise, direction = debit, "debit"
            else:
                continue
            if direction == "debit" and not cfg.include_debits:
                continue
            ref = col(row, cfg.reference_column)
            value_raw = col(row, cfg.value_date_column)
            parsed = ParsedRow(
                transaction_date=txn_date,
                value_date=parse_date(value_raw, cfg.date_formats) if value_raw else None,
                description=desc[:2000],
                utr=extract_utr(ref if ref and ref.strip("0") else None, desc),
                payer_vpa=extract_vpa(desc),
                amount_paise=amount_paise,
                direction=direction,
                balance_paise=to_paise(col(row, cfg.balance_column)) if cfg.balance_column else None,
                raw=raw,
            )
            parsed.fingerprint = fingerprint(parsed)
            rows.append(parsed)
        except ValueError as exc:
            skipped.append({"line": line_no, "error": str(exc)})
    return ParseResult(rows=rows, skipped=skipped, header=header)


def fingerprint(row: ParsedRow) -> str:
    key = "|".join([row.transaction_date.isoformat(), str(row.amount_paise), row.direction, row.utr or "", row.description.strip().upper(),
                    "" if row.balance_paise is None else str(row.balance_paise)])
    return hashlib.sha256(key.encode()).hexdigest()


def preview(content: bytes, delimiter: str = ",", limit: int = 12) -> dict[str, Any]:
    text = content.decode("utf-8-sig", errors="replace")
    lines = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    return {"rows": lines[:limit], "total_lines": len(lines)}
