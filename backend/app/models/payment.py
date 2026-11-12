from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    BankImportStatus,
    BankTransactionMatchStatus,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
)
from app.models.base import Base, PKMixin, PublicIdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class UPIAccount(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Organization-owned UPI collection account. Customers pay this account directly."""

    __tablename__ = "upi_accounts"
    __table_args__ = (UniqueConstraint("organization_id", "upi_id"),)

    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    upi_id: Mapped[str] = mapped_column(String(120), nullable=False)  # vpa, e.g. clinic@upi
    merchant_name: Mapped[str] = mapped_column(String(120), nullable=False)
    merchant_code: Mapped[str | None] = mapped_column(String(16))  # mc param, optional
    static_qr_path: Mapped[str | None] = mapped_column(String(512))
    use_dynamic_qr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    payment_instructions: Mapped[str | None] = mapped_column(Text)
    bank_name: Mapped[str | None] = mapped_column(String(120))
    account_last4: Mapped[str | None] = mapped_column(String(4))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selection_rules: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Payment(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_non_negative"),
        Index("ix_payments_org_status", "organization_id", "status"),
        Index("ix_payments_appointment", "appointment_id"),
    )

    reference: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL")
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    upi_account_id: Mapped[int | None] = mapped_column(ForeignKey("upi_accounts.id", ondelete="SET NULL"))
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), default=PaymentKind.ADVANCE, nullable=False)
    method: Mapped[str] = mapped_column(String(24), default=PaymentMethod.UPI_QR, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=PaymentStatus.INITIATED, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_amount_paise: Mapped[int | None] = mapped_column(Integer)
    upi_uri: Mapped[str | None] = mapped_column(Text)  # the exact URI encoded in the QR
    qr_image_path: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", nullable=True)

    submissions: Mapped[list["PaymentSubmission"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )
    verification_logs: Mapped[list["PaymentVerificationLog"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentSubmission(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    """Customer's claim of payment (UTR, screenshot). Never proof by itself."""

    __tablename__ = "payment_submissions"
    __table_args__ = (
        UniqueConstraint("organization_id", "utr_normalized"),
        Index("ix_payment_submissions_payment", "payment_id"),
    )

    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    utr: Mapped[str | None] = mapped_column(String(64))
    utr_normalized: Mapped[str | None] = mapped_column(String(64))  # upper-cased, stripped
    transaction_reference: Mapped[str | None] = mapped_column(String(128))
    payer_upi_id: Mapped[str | None] = mapped_column(String(120))
    payer_name: Mapped[str | None] = mapped_column(String(120))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_amount_paise: Mapped[int | None] = mapped_column(Integer)
    screenshot_path: Mapped[str | None] = mapped_column(String(512))
    screenshot_mime: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_ip: Mapped[str | None] = mapped_column(String(64))
    duplicate_of_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_submissions.id", ondelete="SET NULL")
    )
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="submissions")


class PaymentVerificationLog(PKMixin, TenantMixin, Base):
    """Immutable audit trail for every payment state change."""

    __tablename__ = "payment_verification_logs"

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # submit, review, approve, reject...
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    bank_credit_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    details: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="verification_logs")


class PaymentRefund(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (CheckConstraint("amount_paise > 0", name="amount_positive"),)

    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"))
    reference: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=RefundStatus.REQUESTED, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    processed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    refund_method: Mapped[str | None] = mapped_column(String(24))  # upi, bank_transfer, cash
    refund_reference: Mapped[str | None] = mapped_column(String(128))  # UTR / bank ref
    refund_proof_path: Mapped[str | None] = mapped_column(String(512))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class BankStatementImport(PKMixin, PublicIdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bank_statement_imports"

    upi_account_id: Mapped[int | None] = mapped_column(ForeignKey("upi_accounts.id", ondelete="SET NULL"))
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    parser_code: Mapped[str] = mapped_column(String(48), nullable=False)  # generic_csv, hdfc, icici...
    parser_config: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=BankImportStatus.UPLOADED, nullable=False)
    statement_from: Mapped[date | None] = mapped_column(Date)
    statement_to: Mapped[date | None] = mapped_column(Date)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    transactions: Mapped[list["BankTransaction"]] = relationship(
        back_populates="import_", cascade="all, delete-orphan"
    )


class BankTransaction(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("organization_id", "fingerprint"),
        Index("ix_bank_transactions_utr", "organization_id", "utr"),
    )

    import_id: Mapped[int] = mapped_column(
        ForeignKey("bank_statement_imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    utr: Mapped[str | None] = mapped_column(String(64))
    payer_vpa: Mapped[str | None] = mapped_column(String(120))
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), default="credit", nullable=False)
    balance_paise: Mapped[int | None] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 of row
    match_status: Mapped[str] = mapped_column(
        String(16), default=BankTransactionMatchStatus.UNMATCHED, nullable=False
    )
    matched_payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    match_confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    matched_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    import_: Mapped[BankStatementImport] = relationship(back_populates="transactions")
