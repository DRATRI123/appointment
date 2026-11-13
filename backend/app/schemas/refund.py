from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class RefundCreate(APIModel):
    payment_id: str
    amount_paise: int | None = Field(default=None, ge=1, description="Defaults to the refundable balance of the payment")
    reason: str = Field(min_length=3, max_length=1000)
    destination: str | None = Field(default=None, max_length=255, description="Customer's UPI ID or bank account the money should go to")
    refund_method: str | None = Field(default=None, pattern=r"^(upi|bank_transfer|cash)$")


class RefundDecision(APIModel):
    notes: str | None = Field(default=None, max_length=1000)


class RefundReject(APIModel):
    reason: str = Field(min_length=3, max_length=1000)


class RefundProcess(APIModel):
    """Staff record the refund they already sent from the clinic's own bank/UPI app. Nothing is sent by this system."""

    refund_method: str = Field(pattern=r"^(upi|bank_transfer|cash)$")
    refund_reference: str | None = Field(default=None, max_length=128)
    destination: str | None = Field(default=None, max_length=255)
    processed_at: datetime | None = None
    money_sent_confirmed: bool
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _ref(self):
        if self.refund_method in ("upi", "bank_transfer") and not (self.refund_reference and self.refund_reference.strip()):
            raise ValueError("Enter the UTR / bank reference of the refund you sent.")
        if self.refund_method == "cash" and not (self.notes and self.notes.strip()):
            raise ValueError("Add a note on who handed over the cash refund.")
        return self


class RefundRead(APIModel):
    id: str
    reference: str
    status: str
    amount_paise: int
    reason: str | None
    rejection_reason: str | None
    refund_method: str | None
    refund_reference: str | None
    destination: str | None
    has_proof: bool
    notes: str | None
    payment_id: str
    payment_reference: str
    payment_method: str
    payment_verified_amount_paise: int | None
    appointment_id: str | None
    appointment_reference: str | None
    appointment_status: str | None
    customer_id: str | None
    customer_name: str | None
    customer_mobile: str | None
    requested_by_name: str | None
    approved_by_name: str | None
    processed_by_name: str | None
    requested_at: datetime | None
    approved_at: datetime | None
    processed_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


class RefundSummary(APIModel):
    """Refund position of a single payment, used by the payment sheet."""

    payment_id: str
    verified_amount_paise: int
    refunded_paise: int
    pending_paise: int
    refundable_paise: int
    suggested_paise: int
    suggestion_reason: str | None
    refunds: list[RefundRead]


class RefundStats(APIModel):
    requested: int
    approved: int
    processed_this_month: int
    pending_amount_paise: int
    processed_amount_this_month_paise: int
