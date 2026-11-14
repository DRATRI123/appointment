"""Bank statement import and payment reconciliation.

Staff export a statement from their own net-banking, upload the CSV here, and the system lines bank credits
up against payments by UTR, payment reference and amount/date. Matching is evidence for the verifier; it
never verifies a payment on its own (``PaymentService.verify`` still requires a person with ``payments:verify``).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import lock_row
from app.core.enums import BankImportStatus, PaymentMethod, PaymentStatus
from app.core.enums import BankTransactionMatchStatus as M
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailed
from app.core.storage import get_storage
from app.core.time import utcnow
from app.models import (
    Appointment,
    BankStatementImport,
    BankTransaction,
    Customer,
    Organization,
    Payment,
    PaymentSubmission,
    UPIAccount,
    User,
)
from app.payments.reconciliation import PRESETS, ParserConfig, parse_csv, preview, squash
from app.schemas.reconciliation import (
    BankEvidence,
    ImportRead,
    MatchCandidate,
    ParserPreset,
    ReconciliationStats,
    StatementPreview,
    TransactionRead,
    UnmatchedPayment,
    UnmatchedReport,
)
from app.services.audit_service import RequestMeta, record_audit

MATCHABLE_METHODS = (PaymentMethod.UPI_QR, PaymentMethod.BANK_TRANSFER)
CANDIDATE_STATUSES = (PaymentStatus.AWAITING_PAYMENT, PaymentStatus.SUBMITTED, PaymentStatus.UNDER_REVIEW, PaymentStatus.VERIFIED,
                      PaymentStatus.REJECTED, PaymentStatus.EXPIRED, PaymentStatus.CANCELLED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED)
AUTO_SUGGEST_THRESHOLD = 60


def _mapping_of(preset: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in preset.items() if k != "label"}


class ReconciliationService:
    def __init__(self, db: Session, org: Organization, actor: User | None = None, meta: RequestMeta | None = None):
        self.db = db
        self.org = org
        self.actor = actor
        self.meta = meta or RequestMeta()

    # ------------------------------------------------------------- parsing
    @staticmethod
    def presets() -> list[ParserPreset]:
        return [ParserPreset(code=code, label=p["label"], mapping=_mapping_of(p)) for code, p in PRESETS.items()]

    @staticmethod
    def _check_file(content: bytes) -> None:
        if not content:
            raise ValidationFailed("Empty file.", code="empty_file")
        if len(content) > get_settings().max_upload_size_mb * 1024 * 1024:
            raise ValidationFailed(f"File larger than {get_settings().max_upload_size_mb} MB.", code="file_too_large")
        if b"\x00" in content[:4096] or content[:4] in (b"PK\x03\x04", b"%PDF"):
            raise ValidationFailed("Upload the statement as CSV. Most net-banking sites offer 'Download as CSV'; Excel files can be saved as CSV.", code="unsupported_file")

    def preview(self, content: bytes, delimiter: str = ",") -> StatementPreview:
        self._check_file(content)
        data = preview(content, delimiter)
        detected = None
        for code, p in PRESETS.items():
            wanted = {p["date_column"].lower(), p["description_column"].lower(), (p.get("credit_column") or p.get("amount_column") or "").lower()}
            if any(wanted <= {c.strip().lower() for c in row} for row in data["rows"]):
                detected = code
                break
        return StatementPreview(rows=data["rows"], total_lines=data["total_lines"], detected_preset=detected)

    def _config(self, parser_code: str, mapping: dict[str, Any] | None) -> ParserConfig:
        base = _mapping_of(PRESETS[parser_code]) if parser_code in PRESETS else {}
        if parser_code not in PRESETS and parser_code != "custom":
            raise ValidationFailed("Unknown statement format.", code="unknown_parser")
        try:
            return ParserConfig.from_dict({**base, **(mapping or {})})
        except (TypeError, ValueError) as exc:
            raise ValidationFailed(str(exc), code="invalid_mapping") from exc

    # ------------------------------------------------------------- import
    def import_statement(self, *, content: bytes, file_name: str, parser_code: str, mapping: dict[str, Any] | None, upi_account_id: str | None) -> BankStatementImport:
        self._check_file(content)
        cfg = self._config(parser_code, mapping)
        try:
            result = parse_csv(content, cfg)
        except ValueError as exc:
            raise ValidationFailed(str(exc), code="statement_unreadable") from exc
        if not result.rows and not result.skipped:
            raise ValidationFailed("No incoming credits were found in this statement.", code="statement_empty")
        if not result.rows:
            raise ValidationFailed(f"None of the rows could be read. First problem: line {result.skipped[0]['line']}: {result.skipped[0]['error']}", code="statement_unreadable")
        account = None
        if upi_account_id:
            account = self.db.scalar(select(UPIAccount).where(UPIAccount.public_id == upi_account_id, UPIAccount.organization_id == self.org.id))
            if account is None:
                raise NotFoundError("UPI account not found.")
        stored = get_storage().save(scope=f"org/{self.org.public_id}/statements", visibility="private", data=content, mime_type="text/csv")
        imp = BankStatementImport(
            organization_id=self.org.id, upi_account_id=account.id if account else None, uploaded_by_user_id=self.actor.id if self.actor else None,
            file_name=(file_name or "statement.csv")[:255], storage_path=stored.key, parser_code=parser_code,
            parser_config={k: v for k, v in cfg.__dict__.items()}, status=BankImportStatus.PARSED,
            statement_from=min(r.transaction_date for r in result.rows), statement_to=max(r.transaction_date for r in result.rows),
            skipped_rows=len(result.skipped), skipped=result.skipped[:50],
        )
        self.db.add(imp)
        self.db.flush()

        fps = [r.fingerprint for r in result.rows]
        existing = set(self.db.scalars(select(BankTransaction.fingerprint).where(BankTransaction.organization_id == self.org.id, BankTransaction.fingerprint.in_(fps))).all())
        new: list[BankTransaction] = []
        dupes = 0
        for r in result.rows:
            if r.fingerprint in existing:
                dupes += 1
                continue
            existing.add(r.fingerprint)
            txn = BankTransaction(
                organization_id=self.org.id, import_id=imp.id, transaction_date=r.transaction_date, value_date=r.value_date, description=r.description,
                utr=r.utr, payer_vpa=r.payer_vpa, amount_paise=r.amount_paise, direction=r.direction, balance_paise=r.balance_paise,
                fingerprint=r.fingerprint, match_status=M.UNMATCHED, raw=r.raw,
            )
            self.db.add(txn)
            new.append(txn)
        self.db.flush()
        imp.total_rows = len(new)
        imp.duplicate_rows = dupes
        for txn in new:
            self._auto_suggest(txn)
        self._recount(imp)
        record_audit(self.db, action="reconciliation.statement_imported", actor=self.actor, organization_id=self.org.id, entity_type="bank_statement_import",
                     entity_id=imp.public_id, after={"rows": len(new), "duplicates": dupes, "skipped": len(result.skipped), "parser": parser_code}, meta=self.meta)
        return imp

    def delete_import(self, imp: BankStatementImport) -> None:
        if any(t.match_status == M.MATCHED for t in imp.transactions):
            raise ConflictError("Unmatch the confirmed transactions of this statement before deleting it.", code="import_has_matches")
        record_audit(self.db, action="reconciliation.statement_deleted", actor=self.actor, organization_id=self.org.id, entity_type="bank_statement_import",
                     entity_id=imp.public_id, before={"file_name": imp.file_name, "rows": imp.total_rows}, meta=self.meta)
        key = imp.storage_path
        self.db.delete(imp)
        self.db.flush()
        get_storage().delete(key)

    def _recount(self, imp: BankStatementImport) -> None:
        self.db.flush()
        imp.matched_rows = int(self.db.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.import_id == imp.id, BankTransaction.match_status == M.MATCHED)) or 0)
        open_rows = self.db.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.import_id == imp.id, BankTransaction.match_status.in_([M.UNMATCHED, M.SUGGESTED]))) or 0
        imp.status = BankImportStatus.RECONCILED if imp.total_rows and open_rows == 0 else BankImportStatus.PARSED

    # ------------------------------------------------------------- matching
    def _payment_utrs(self, payment_ids: list[int]) -> dict[int, str]:
        if not payment_ids:
            return {}
        rows = self.db.execute(select(PaymentSubmission.payment_id, PaymentSubmission.utr_normalized).where(
            PaymentSubmission.payment_id.in_(payment_ids), PaymentSubmission.is_superseded.is_(False))).all()
        return {pid: utr for pid, utr in rows}

    def candidates(self, txn: BankTransaction, limit: int = 8) -> list[MatchCandidate]:
        if txn.direction != "credit":
            return []
        scores: dict[int, tuple[int, list[str]]] = {}

        def add(pid: int, pts: int, why: str) -> None:
            s, reasons = scores.get(pid, (0, []))
            if why not in reasons:
                scores[pid] = (s + pts, [*reasons, why])

        base = select(Payment).where(Payment.organization_id == self.org.id, Payment.method.in_(MATCHABLE_METHODS), Payment.status.in_(CANDIDATE_STATUSES))
        # 1. UTR quoted by the customer equals the UTR in the bank narration / reference column.
        if txn.utr:
            for (pid,) in self.db.execute(select(PaymentSubmission.payment_id).where(PaymentSubmission.organization_id == self.org.id, PaymentSubmission.utr_normalized == txn.utr)).all():
                add(pid, 70, "UTR matches the customer's submission")
        # 2. Our payment/appointment reference appears in the narration (UPI apps pass the 'tr'/'tn' fields through).
        narr = squash(txn.description)
        window_start = datetime.combine(txn.transaction_date - timedelta(days=10), datetime.min.time())
        window_end = datetime.combine(txn.transaction_date + timedelta(days=2), datetime.min.time())
        recent = self.db.scalars(base.where(Payment.created_at >= window_start, Payment.created_at <= window_end)).all()
        appt_refs = dict(self.db.execute(select(Appointment.id, Appointment.reference).where(Appointment.id.in_({p.appointment_id for p in recent if p.appointment_id}))).all()) if recent else {}
        for p in recent:
            if narr and _ref_in(squash(p.reference), narr):
                add(p.id, 60, "Payment reference appears in the bank narration")
            ar = squash(appt_refs.get(p.appointment_id))
            if narr and ar and _ref_in(ar, narr):
                add(p.id, 50, "Appointment reference appears in the bank narration")
        # 3. Same amount around the same date.
        same_amount = [p for p in recent if (p.verified_amount_paise or p.amount_paise) == txn.amount_paise]
        for p in same_amount:
            when = (p.submitted_at or p.created_at).date()
            gap = abs((when - txn.transaction_date).days)
            if gap <= 3:
                add(p.id, 40 if gap <= 1 else 30, f"Same amount, {'same day' if gap == 0 else f'{gap} day(s) apart'}")
        if len(same_amount) == 1 and same_amount[0].id in scores:
            add(same_amount[0].id, 10, "Only payment with this amount in the period")
        if not scores:
            return []
        payments = {p.id: p for p in self.db.scalars(select(Payment).where(Payment.id.in_(scores.keys()), Payment.organization_id == self.org.id)).all()}
        utrs = self._payment_utrs(list(payments))
        matched_elsewhere = set(self.db.scalars(select(BankTransaction.matched_payment_id).where(
            BankTransaction.organization_id == self.org.id, BankTransaction.match_status == M.MATCHED, BankTransaction.id != txn.id, BankTransaction.matched_payment_id.in_(list(payments)))).all())
        out: list[MatchCandidate] = []
        for pid, (score, reasons) in scores.items():
            p = payments.get(pid)
            if p is None or pid in matched_elsewhere:
                continue
            if (p.verified_amount_paise or p.amount_paise) == txn.amount_paise:
                if not any(r.startswith("Same amount") for r in reasons):
                    score += 20
                    reasons = [*reasons, "Amount matches"]
            elif reasons and reasons[0].startswith("UTR"):
                score -= 30
                reasons = [*reasons, "Amount differs from the payment"]
            if txn.payer_vpa:
                sub_vpa = self.db.scalar(select(PaymentSubmission.payer_upi_id).where(PaymentSubmission.payment_id == pid, PaymentSubmission.is_superseded.is_(False)))
                if sub_vpa and sub_vpa.strip().lower() == txn.payer_vpa:
                    score += 10
                    reasons = [*reasons, "Payer UPI ID matches"]
            cust = self.db.get(Customer, p.customer_id) if p.customer_id else None
            appt = self.db.get(Appointment, p.appointment_id) if p.appointment_id else None
            out.append(MatchCandidate(payment_id=p.public_id, payment_reference=p.reference, payment_status=p.status, amount_paise=p.verified_amount_paise or p.amount_paise,
                                      customer_name=cust.full_name if cust else None, appointment_reference=appt.reference if appt else None, latest_utr=utrs.get(pid),
                                      submitted_at=p.submitted_at, score=max(0, min(100, score)), reasons=reasons))
        out.sort(key=lambda c: -c.score)
        return out[:limit]

    def _auto_suggest(self, txn: BankTransaction) -> None:
        if txn.match_status != M.UNMATCHED:
            return
        cands = self.candidates(txn, limit=2)
        if not cands or cands[0].score < AUTO_SUGGEST_THRESHOLD:
            return
        if len(cands) > 1 and cands[1].score >= cands[0].score - 10:
            return  # ambiguous: leave it for a person
        p = self.db.scalar(select(Payment).where(Payment.public_id == cands[0].payment_id))
        txn.match_status = M.SUGGESTED
        txn.matched_payment_id = p.id
        txn.match_confidence = cands[0].score

    def rerun_suggestions(self) -> int:
        n = 0
        for txn in self.db.scalars(select(BankTransaction).where(BankTransaction.organization_id == self.org.id, BankTransaction.match_status == M.UNMATCHED,
                                                                 BankTransaction.direction == "credit")).all():
            self._auto_suggest(txn)
            n += txn.match_status == M.SUGGESTED
        for imp in self.db.scalars(select(BankStatementImport).where(BankStatementImport.organization_id == self.org.id)).all():
            self._recount(imp)
        return n

    def _payment_log(self, payment: Payment, action: str, reason: str | None, details: dict) -> None:
        from app.services.payment_service import PaymentService

        PaymentService(self.db, self.org, self.actor, self.meta)._log(payment, action, payment.status, payment.status, reason=reason, details=details)

    def confirm(self, txn: BankTransaction, payment_id: str, notes: str | None) -> BankTransaction:
        lock_row(self.db, txn)
        if txn.match_status == M.MATCHED:
            raise ConflictError("This bank line is already matched. Unmatch it first.", code="already_matched")
        if txn.direction != "credit":
            raise ConflictError("Only incoming credits can be matched to payments.", code="not_a_credit")
        payment = self.db.scalar(select(Payment).where(Payment.public_id == payment_id, Payment.organization_id == self.org.id))
        if payment is None:
            raise NotFoundError("Payment not found.")
        lock_row(self.db, payment)  # two bank lines must not both claim one payment
        other = self.db.scalar(select(BankTransaction).where(BankTransaction.organization_id == self.org.id, BankTransaction.matched_payment_id == payment.id,
                                                            BankTransaction.match_status == M.MATCHED))
        if other is not None:
            raise ConflictError(f"Payment {payment.reference} is already matched to the bank credit of {other.transaction_date:%d %b %Y}.", code="payment_already_matched")
        expected = payment.verified_amount_paise or payment.amount_paise
        if expected != txn.amount_paise and not (notes and notes.strip()):
            raise ValidationFailed("The bank credit and the payment amounts differ. Add a note explaining why they belong together.", code="amount_mismatch")
        txn.match_status = M.MATCHED
        txn.matched_payment_id = payment.id
        txn.matched_by_user_id = self.actor.id if self.actor else None
        txn.matched_at = utcnow()
        txn.notes = (notes or "").strip() or txn.notes
        txn.match_confidence = txn.match_confidence or None
        self._payment_log(payment, "bank_matched", notes, {"bank_date": txn.transaction_date.isoformat(), "bank_amount_paise": txn.amount_paise, "bank_utr": txn.utr, "transaction": txn.id})
        record_audit(self.db, action="reconciliation.matched", actor=self.actor, organization_id=self.org.id, entity_type="bank_transaction", entity_id=str(txn.id),
                     after={"payment": payment.reference, "amount_paise": txn.amount_paise}, purpose=notes, meta=self.meta)
        self._recount(txn.import_)
        return txn

    def unmatch(self, txn: BankTransaction, reason: str | None = None) -> BankTransaction:
        if txn.match_status not in (M.MATCHED, M.SUGGESTED):
            raise ConflictError("This bank line is not matched.", code="not_matched")
        was = txn.match_status
        payment = self.db.get(Payment, txn.matched_payment_id) if txn.matched_payment_id else None
        txn.match_status = M.UNMATCHED
        txn.matched_payment_id = None
        txn.matched_by_user_id = None
        txn.matched_at = None
        txn.match_confidence = None
        if was == M.MATCHED and payment is not None:
            self._payment_log(payment, "bank_unmatched", reason, {"transaction": txn.id})
        record_audit(self.db, action="reconciliation.unmatched" if was == M.MATCHED else "reconciliation.suggestion_dismissed", actor=self.actor,
                     organization_id=self.org.id, entity_type="bank_transaction", entity_id=str(txn.id), purpose=reason, meta=self.meta)
        self._recount(txn.import_)
        return txn

    def ignore(self, txn: BankTransaction, reason: str) -> BankTransaction:
        if txn.match_status == M.MATCHED:
            raise ConflictError("Unmatch this bank line before ignoring it.", code="already_matched")
        txn.match_status = M.IGNORED
        txn.matched_payment_id = None
        txn.match_confidence = None
        txn.notes = reason.strip()
        record_audit(self.db, action="reconciliation.ignored", actor=self.actor, organization_id=self.org.id, entity_type="bank_transaction", entity_id=str(txn.id), purpose=reason, meta=self.meta)
        self._recount(txn.import_)
        return txn

    def restore(self, txn: BankTransaction) -> BankTransaction:
        if txn.match_status != M.IGNORED:
            raise ConflictError("Only ignored lines can be restored.", code="not_ignored")
        txn.match_status = M.UNMATCHED
        self._auto_suggest(txn)
        self._recount(txn.import_)
        return txn

    # ---------------------------------------------------------------- reads
    def get_import(self, public_id: str) -> BankStatementImport:
        imp = self.db.scalar(select(BankStatementImport).where(BankStatementImport.public_id == public_id, BankStatementImport.organization_id == self.org.id))
        if imp is None:
            raise NotFoundError("Statement not found.")
        return imp

    def get_txn(self, txn_id: int) -> BankTransaction:
        txn = self.db.scalar(select(BankTransaction).where(BankTransaction.id == txn_id, BankTransaction.organization_id == self.org.id))
        if txn is None:
            raise NotFoundError("Bank transaction not found.")
        return txn

    def imports(self) -> list[BankStatementImport]:
        return list(self.db.scalars(select(BankStatementImport).where(BankStatementImport.organization_id == self.org.id).order_by(BankStatementImport.created_at.desc())).all())

    def import_read(self, imp: BankStatementImport) -> ImportRead:
        acct = self.db.get(UPIAccount, imp.upi_account_id) if imp.upi_account_id else None
        by = self.db.get(User, imp.uploaded_by_user_id) if imp.uploaded_by_user_id else None
        suggested = self.db.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.import_id == imp.id, BankTransaction.match_status == M.SUGGESTED)) or 0
        return ImportRead(id=imp.public_id, file_name=imp.file_name, parser_code=imp.parser_code, status=imp.status, statement_from=imp.statement_from, statement_to=imp.statement_to,
                          total_rows=imp.total_rows, matched_rows=imp.matched_rows, suggested_rows=int(suggested), duplicate_rows=imp.duplicate_rows, skipped_rows=imp.skipped_rows,
                          skipped=imp.skipped, upi_account_name=acct.display_name if acct else None, uploaded_by_name=by.full_name if by else None,
                          error_message=imp.error_message, created_at=imp.created_at)

    def txn_read(self, t: BankTransaction, dup_utrs: set[str] | None = None) -> TransactionRead:
        p = self.db.get(Payment, t.matched_payment_id) if t.matched_payment_id else None
        cust = self.db.get(Customer, p.customer_id) if p and p.customer_id else None
        by = self.db.get(User, t.matched_by_user_id) if t.matched_by_user_id else None
        if dup_utrs is None:
            dup_utrs = self._duplicate_utrs([t.utr] if t.utr else [])
        return TransactionRead(id=t.id, import_id=t.import_.public_id, transaction_date=t.transaction_date, value_date=t.value_date, description=t.description, utr=t.utr,
                               payer_vpa=t.payer_vpa, amount_paise=t.amount_paise, direction=t.direction, balance_paise=t.balance_paise, match_status=t.match_status,
                               match_confidence=t.match_confidence, matched_payment_id=p.public_id if p else None, matched_payment_reference=p.reference if p else None,
                               matched_payment_status=p.status if p else None, matched_customer_name=cust.full_name if cust else None,
                               matched_by_name=by.full_name if by else None, matched_at=t.matched_at, notes=t.notes, duplicate_utr=bool(t.utr and t.utr in dup_utrs))

    def _duplicate_utrs(self, utrs: list[str]) -> set[str]:
        if not utrs:
            return set()
        rows = self.db.execute(select(BankTransaction.utr, func.count()).where(BankTransaction.organization_id == self.org.id, BankTransaction.utr.in_(set(utrs)))
                               .group_by(BankTransaction.utr).having(func.count() > 1)).all()
        return {u for u, _ in rows}

    def txn_reads(self, rows: list[BankTransaction]) -> list[TransactionRead]:
        dups = self._duplicate_utrs([t.utr for t in rows if t.utr])
        return [self.txn_read(t, dups) for t in rows]

    def transactions(self, *, status: str | None, import_id: str | None, search: str | None, from_date: date | None, to_date: date | None,
                     direction: str | None, page: int, page_size: int) -> tuple[list[BankTransaction], int]:
        stmt = select(BankTransaction).where(BankTransaction.organization_id == self.org.id)
        if status:
            stmt = stmt.where(BankTransaction.match_status.in_(status.split(",")))
        if import_id:
            stmt = stmt.where(BankTransaction.import_id == self.get_import(import_id).id)
        if direction:
            stmt = stmt.where(BankTransaction.direction == direction)
        if from_date:
            stmt = stmt.where(BankTransaction.transaction_date >= from_date)
        if to_date:
            stmt = stmt.where(BankTransaction.transaction_date <= to_date)
        if search:
            s = search.strip()
            like = f"%{s.upper()}%"
            conds = [func.upper(func.coalesce(BankTransaction.utr, "")).like(like), func.upper(func.coalesce(BankTransaction.description, "")).like(like)]
            digits = s.replace(",", "").replace("₹", "")
            try:
                conds.append(BankTransaction.amount_paise == int(round(float(digits) * 100)))
            except ValueError:
                pass
            stmt = stmt.where(or_(*conds))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(BankTransaction.transaction_date.desc(), BankTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), int(total)

    def _verified_without_match(self, from_date: date | None = None, to_date: date | None = None):
        matched = select(BankTransaction.matched_payment_id).where(BankTransaction.organization_id == self.org.id, BankTransaction.match_status == M.MATCHED,
                                                                   BankTransaction.matched_payment_id.is_not(None))
        stmt = select(Payment).where(Payment.organization_id == self.org.id, Payment.method.in_(MATCHABLE_METHODS),
                                     Payment.status.in_([PaymentStatus.VERIFIED, PaymentStatus.REFUND_REQUESTED, PaymentStatus.REFUND_PROCESSED]), Payment.id.not_in(matched))
        if from_date:
            stmt = stmt.where(Payment.verified_at >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            stmt = stmt.where(Payment.verified_at < datetime.combine(to_date + timedelta(days=1), datetime.min.time()))
        return stmt

    def stats(self) -> ReconciliationStats:
        def count(status: str) -> int:
            return int(self.db.scalar(select(func.count()).select_from(BankTransaction).where(BankTransaction.organization_id == self.org.id, BankTransaction.direction == "credit",
                                                                                             BankTransaction.match_status == status)) or 0)

        amt = self.db.scalar(select(func.coalesce(func.sum(BankTransaction.amount_paise), 0)).where(
            BankTransaction.organization_id == self.org.id, BankTransaction.direction == "credit", BankTransaction.match_status.in_([M.UNMATCHED, M.SUGGESTED]))) or 0
        vwm = self.db.scalar(select(func.count()).select_from(self._verified_without_match().subquery())) or 0
        return ReconciliationStats(unmatched=count(M.UNMATCHED), suggested=count(M.SUGGESTED), matched=count(M.MATCHED), ignored=count(M.IGNORED),
                                   unmatched_amount_paise=int(amt), verified_without_bank_match=int(vwm))

    def report(self, from_date: date | None, to_date: date | None) -> UnmatchedReport:
        stmt = select(BankTransaction).where(BankTransaction.organization_id == self.org.id, BankTransaction.direction == "credit",
                                             BankTransaction.match_status.in_([M.UNMATCHED, M.SUGGESTED]))
        if from_date:
            stmt = stmt.where(BankTransaction.transaction_date >= from_date)
        if to_date:
            stmt = stmt.where(BankTransaction.transaction_date <= to_date)
        credits = self.db.scalars(stmt.order_by(BankTransaction.transaction_date.desc()).limit(1000)).all()
        pays = self.db.scalars(self._verified_without_match(from_date, to_date).order_by(Payment.verified_at.desc()).limit(1000)).all()
        utrs = self._payment_utrs([p.id for p in pays])
        names = dict(self.db.execute(select(Customer.id, Customer.full_name).where(Customer.id.in_({p.customer_id for p in pays if p.customer_id}))).all()) if pays else {}
        return UnmatchedReport(bank_credits=self.txn_reads(list(credits)), payments=[
            UnmatchedPayment(payment_id=p.public_id, payment_reference=p.reference, status=p.status, method=p.method, amount_paise=p.amount_paise, verified_amount_paise=p.verified_amount_paise,
                             latest_utr=utrs.get(p.id), customer_name=names.get(p.customer_id), verified_at=p.verified_at, submitted_at=p.submitted_at) for p in pays])

    def report_csv(self, from_date: date | None, to_date: date | None) -> str:
        rep = self.report(from_date, to_date)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Section", "Date", "Amount (INR)", "UTR", "Reference / Description", "Customer", "Status"])
        for t in rep.bank_credits:
            w.writerow(["Bank credit without payment", t.transaction_date.isoformat(), f"{t.amount_paise / 100:.2f}", t.utr or "", _safe(t.description), "", t.match_status])
        for p in rep.payments:
            w.writerow(["Verified payment without bank credit", p.verified_at.date().isoformat() if p.verified_at else "", f"{(p.verified_amount_paise or p.amount_paise) / 100:.2f}",
                        p.latest_utr or "", p.payment_reference, _safe(p.customer_name), p.status])
        return buf.getvalue()

    def evidence_for(self, payment: Payment) -> list[BankEvidence]:
        utrs = [u for u in self._payment_utrs([payment.id]).values() if u]
        conds = [BankTransaction.matched_payment_id == payment.id]
        if utrs:
            conds.append(BankTransaction.utr.in_(utrs))
        rows = self.db.scalars(select(BankTransaction).where(BankTransaction.organization_id == self.org.id, or_(*conds)).order_by(BankTransaction.transaction_date.desc()).limit(10)).all()
        out = []
        for t in rows:
            other = self.db.get(Payment, t.matched_payment_id) if t.matched_payment_id and t.matched_payment_id != payment.id else None
            out.append(BankEvidence(transaction_id=t.id, transaction_date=t.transaction_date, amount_paise=t.amount_paise, utr=t.utr, description=t.description,
                                    match_status=t.match_status, matched_to_this_payment=t.matched_payment_id == payment.id,
                                    matched_payment_reference=other.reference if other else None))
        return out


def _ref_in(ref: str, narration: str) -> bool:
    """References end in a 26-char ULID. Banks cut long narrations at the end, so a prefix that still carries
    16 ULID characters (timestamp + 30 random bits) is as good as the full reference; so is the random tail."""
    if not ref:
        return False
    if ref in narration:
        return True
    if len(ref) >= 26:
        prefix = ref[: len(ref) - 26 + 16]
        return prefix in narration or ref[-14:] in narration
    return False


def _safe(value: str | None) -> str:
    """Neutralise spreadsheet formula injection in exported text."""
    v = value or ""
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
