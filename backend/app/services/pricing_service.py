"""Server-side price computation. The client never sends amounts; everything is integer paise."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ServicePaymentMode
from app.models import Branch, Professional, Service


@dataclass
class Quote:
    currency: str
    subtotal_paise: int
    discount_paise: int
    tax_paise: int
    total_amount_paise: int
    advance_due_paise: int
    payment_mode: str
    breakdown: dict[str, Any] = field(default_factory=dict)

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "currency": self.currency, "subtotal_paise": self.subtotal_paise, "discount_paise": self.discount_paise,
            "tax_paise": self.tax_paise, "total_amount_paise": self.total_amount_paise, "advance_due_paise": self.advance_due_paise,
            "payment_mode": self.payment_mode, **self.breakdown,
        }


def quote(service: Service, branch: Branch, professional: Professional | None, coupon=None) -> Quote:
    """Price precedence: professional fee override for this service → branch price override → service price.

    A validated ``Coupon`` (see ``CouponService.validate``) is applied after the list discount and before tax.
    """
    source = "service"
    list_price = service.price_paise
    discounted = service.discounted_price_paise
    advance_amount = service.advance_amount_paise

    branch_row = next((p for p in service.pricing if p.branch_id == branch.id), None)
    if branch_row:
        if branch_row.price_paise is not None:
            list_price, source = branch_row.price_paise, "branch"
            discounted = branch_row.discounted_price_paise
        elif branch_row.discounted_price_paise is not None:
            discounted = branch_row.discounted_price_paise
        if branch_row.advance_amount_paise is not None:
            advance_amount = branch_row.advance_amount_paise

    if professional is not None:
        override = next(
            (ps for ps in professional.services if ps.service_id == service.id and ps.is_active and ps.branch_id in (None, branch.id) and ps.fee_override_paise is not None),
            None,
        )
        if override:
            list_price, source = override.fee_override_paise, "professional"
            discounted = None

    if service.payment_mode == ServicePaymentMode.FREE:
        list_price, discounted = 0, None

    effective = discounted if (discounted is not None and discounted < list_price) else list_price
    coupon_discount_paise = 0
    if coupon is not None:
        from app.services.coupon_service import coupon_discount

        coupon_discount_paise = coupon_discount(coupon, effective)
        effective -= coupon_discount_paise
    discount = list_price - effective
    tax = round(effective * service.tax_percent / 100) if service.tax_percent else 0
    total = effective + tax

    mode = service.payment_mode
    if mode == ServicePaymentMode.FULL_ADVANCE:
        advance = total
    elif mode in (ServicePaymentMode.PARTIAL_ADVANCE, ServicePaymentMode.OPTIONAL_ADVANCE):
        if advance_amount is not None:
            advance = min(advance_amount, total)
        elif service.advance_percent:
            advance = round(total * service.advance_percent / 100)
        else:
            advance = total if mode == ServicePaymentMode.PARTIAL_ADVANCE else 0
    else:  # free, pay_at_clinic
        advance = 0

    return Quote(
        currency=service.currency, subtotal_paise=list_price, discount_paise=discount, tax_paise=tax,
        total_amount_paise=total, advance_due_paise=advance, payment_mode=mode,
        breakdown={"price_source": source, "tax_percent": service.tax_percent, "service_id": service.public_id, "branch_id": branch.public_id,
                   "professional_id": professional.public_id if professional else None,
                   "coupon_code": coupon.code if coupon is not None else None, "coupon_discount_paise": coupon_discount_paise},
    )
