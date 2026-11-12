"""Normalisation of login identifiers."""
from __future__ import annotations

import re

from app.core.exceptions import ValidationFailed

DEFAULT_COUNTRY_CODE = "+91"


def normalize_mobile(raw: str, default_country_code: str = DEFAULT_COUNTRY_CODE) -> str:
    """Return an E.164 number. Indian 10-digit numbers get +91 by default."""
    value = re.sub(r"[\s\-().]", "", raw.strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if not value.startswith("+"):
        if len(value) == 10 and value.isdigit():
            value = f"{default_country_code}{value}"
        elif value.startswith("0") and len(value) == 11 and value.isdigit():
            value = f"{default_country_code}{value[1:]}"
        else:
            value = f"+{value}"
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValidationFailed("Enter a valid mobile number.", code="invalid_mobile")
    return value


def normalize_email(raw: str) -> str:
    value = raw.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValidationFailed("Enter a valid email address.", code="invalid_email")
    return value
