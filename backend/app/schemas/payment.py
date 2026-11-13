from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.common import APIModel


# ------------------------------------------------------------- UPI accounts
class UPIAccountBase(APIModel):
    display_name: str = Field(min_length=2, max_length=120)
    upi_id: str = Field(min_length=5, max_length=120)
    merchant_name: str = Field(min_length=2, max_length=120)
    merchant_code: str | None = Field(default=None, max_length=16, pattern=r"^\d{4}$")
    static_qr_path: str | None = Field(default=None, max_length=512)
    use_dynamic_qr: bool = True
    payment_instructions: str | None = Field(default=None, max_length=2000)
    bank_name: str | None = Field(default=None, max_length=120)
    account_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 0

    @field_validator("upi_id")
    @classmethod
    def _vpa(cls, v: str) -> str:
        from app.payments.upi import validate_upi_id

        return validate_upi_id(v)

    @model_validator(mode="after")
    def _qr_mode(self):
        if not self.use_dynamic_qr and not self.static_qr_path:
            raise ValueError("Upload a static QR image or enable dynamic QR.")
        return self


class UPIAccountCreate(UPIAccountBase):
    branch_id: str | None = None


class UPIAccountUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    upi_id: str | None = Field(default=None, min_length=5, max_length=120)
    merchant_name: str | None = Field(default=None, min_length=2, max_length=120)
    merchant_code: str | None = Field(default=None, max_length=16, pattern=r"^\d{4}$")
    static_qr_path: str | None = Field(default=None, max_length=512)
    use_dynamic_qr: bool | None = None
    payment_instructions: str | None = Field(default=None, max_length=2000)
    bank_name: str | None = Field(default=None, max_length=120)
    account_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    branch_id: str | None = None
    clear_branch: bool = False

    @field_validator("upi_id")
    @classmethod
    def _vpa(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from app.payments.upi import validate_upi_id

        return validate_upi_id(v)


class UPIAccountRead(UPIAccountBase):
    id: str
    branch_id: str | None
    branch_name: str | None = None
    service_count: int = 0
    created_at: datetime


class QRPreview(APIModel):
    upi_uri: str | None
    qr_data_url: str
    is_static: bool
    amount_paise: int | None


# ----------------------------------------------------------------- coupons
class CouponBase(APIModel):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=500)
    discount_type: str = Field(pattern=r"^(percent|flat)$")
    discount_value: int = Field(gt=0)
    max_discount_paise: int | None = Field(default=None, gt=0)
    min_amount_paise: int | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)
    per_customer_limit: int | None = Field(default=None, ge=1)
    service_ids: list[str] | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.discount_type == "percent" and self.discount_value > 100:
            raise ValueError("A percent discount cannot exceed 100.")
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("valid_from must be before valid_to")
        return self


class CouponCreate(CouponBase):
    pass


class CouponUpdate(APIModel):
    description: str | None = Field(default=None, max_length=500)
    max_discount_paise: int | None = Field(default=None, gt=0)
    min_amount_paise: int | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    max_redemptions: int | None = Field(default=None, ge=1)
    per_customer_limit: int | None = Field(default=None, ge=1)
    service_ids: list[str] | None = None
    is_active: bool | None = None


class CouponRead(CouponBase):
    id: str
    redemptions: int = 0
    created_at: datetime


# ---------------------------------------------------------------- payments
class SubmissionRead(APIModel):
    id: str
    utr: str | None
    transaction_reference: str | None
    payer_upi_id: str | None
    payer_name: str | None
    paid_at: datetime | None
    claimed_amount_paise: int | None
    has_screenshot: bool
    notes: str | None
    is_superseded: bool
    created_at: datetime


class VerificationLogRead(APIModel):
    action: str
    from_status: str | None
    to_status: str
    reason: str | None
    bank_credit_confirmed: bool | None
    actor_name: str | None
    details: dict[str, Any] | None
    created_at: datetime


class PaymentRead(APIModel):
    id: str
    reference: str
    status: str
    kind: str
    method: str
    currency: str
    amount_paise: int
    verified_amount_paise: int | None
    expires_at: datetime | None
    submitted_at: datetime | None
    verified_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    appointment_id: str | None
    appointment_reference: str | None
    appointment_start_at: datetime | None
    appointment_timezone: str | None = None
    appointment_status: str | None
    service_name: str | None
    branch_name: str | None
    customer_id: str | None
    customer_name: str | None
    customer_mobile: str | None
    upi_account_id: str | None
    upi_account_name: str | None
    upi_id: str | None
    latest_utr: str | None = None
    duplicate_utr_flag: bool = False
    created_at: datetime


class PaymentDetail(PaymentRead):
    submissions: list[SubmissionRead] = Field(default_factory=list)
    logs: list[VerificationLogRead] = Field(default_factory=list)
    notes: str | None = None


class PaymentCreate(APIModel):
    """Staff: request or record a payment. The amount is always computed by the server."""

    appointment_id: str
    kind: str = Field(default="advance", pattern=r"^(advance|balance|full)$")
    method: str = Field(default="upi_qr", pattern=r"^(upi_qr|cash|bank_transfer)$")
    utr: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _bank(self):
        if self.method == "bank_transfer" and not self.utr:
            raise ValueError("A bank reference (UTR) is required for bank transfers.")
        return self


class VerifyRequest(APIModel):
    bank_credit_confirmed: bool
    verified_amount_paise: int = Field(ge=1)
    amount_mismatch_reason: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class RejectRequest(APIModel):
    reason: str = Field(min_length=3, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class NoteRequest(APIModel):
    notes: str = Field(min_length=1, max_length=1000)


class PaymentStats(APIModel):
    awaiting_payment: int
    submitted: int
    under_review: int
    verified_today: int
    rejected_today: int
    pending_amount_paise: int
    verified_amount_today_paise: int


# ---------------------------------------------------------- public checkout
class CheckoutUPI(APIModel):
    account_name: str
    upi_id: str
    merchant_name: str
    instructions: str | None
    is_static: bool
    upi_uri: str | None
    qr_data_url: str | None
    static_qr_url: str | None
    app_links: dict[str, str]


class Checkout(APIModel):
    payment: PaymentRead
    upi: CheckoutUPI | None
    can_submit: bool
    latest_submission: SubmissionRead | None
    message: str | None = None
