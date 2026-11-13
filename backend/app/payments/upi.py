"""UPI payment request helpers: URI building, QR rendering and app deep links.

A UPI QR code is only a *request* to pay. Nothing in this module (or anywhere else) treats a generated
QR, a scanned QR or a returned deep link as proof that money moved. Payments are confirmed only when
authorised staff verify the bank credit.
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from urllib.parse import quote

import qrcode
from qrcode.constants import ERROR_CORRECT_M

UPI_ID_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")
MAX_NOTE_LEN = 80  # most PSP apps truncate the transaction note around here


def validate_upi_id(value: str) -> str:
    v = value.strip()
    if not UPI_ID_RE.fullmatch(v):
        raise ValueError("Enter a valid UPI ID such as clinic@okhdfcbank.")
    return v.lower()


def paise_to_rupees_str(paise: int) -> str:
    """UPI 'am' parameter: rupees with exactly two decimals, no thousands separators."""
    if paise < 0:
        raise ValueError("Amount cannot be negative.")
    return f"{paise // 100}.{paise % 100:02d}"


def _enc(value: str, safe: str = "") -> str:
    return quote(value, safe=safe)


@dataclass(frozen=True)
class UPIRequest:
    payee_vpa: str
    payee_name: str
    amount_paise: int | None
    reference: str
    note: str | None = None
    merchant_code: str | None = None
    currency: str = "INR"

    def uri(self, scheme: str = "upi", host: str = "pay") -> str:
        """``upi://pay?pa=...&pn=...&am=...&cu=INR&tn=...&tr=...`` with every value percent-encoded.

        ``@`` in the VPA is left literal because several PSP apps fail to decode ``%40``.
        """
        params = [("pa", _enc(self.payee_vpa, safe="@")), ("pn", _enc(self.payee_name[:50]))]
        if self.merchant_code:
            params.append(("mc", _enc(self.merchant_code)))
        params.append(("tr", _enc(self.reference)))
        note = (self.note or self.reference)[:MAX_NOTE_LEN]
        params.append(("tn", _enc(note)))
        if self.amount_paise is not None:
            params.append(("am", paise_to_rupees_str(self.amount_paise)))
        params.append(("cu", _enc(self.currency)))
        query = "&".join(f"{k}={v}" for k, v in params)
        return f"{scheme}://{host}?{query}"

    def app_links(self) -> dict[str, str]:
        """Deep links for popular apps. Support varies by platform; the generic ``upi://`` link opens the
        system chooser on Android. On iOS, app-specific schemes are the only option."""
        query = self.uri().split("?", 1)[1]
        return {
            "any": self.uri(),
            "gpay": f"tez://upi/pay?{query}",
            "phonepe": f"phonepe://pay?{query}",
            "paytm": f"paytmmp://pay?{query}",
            "bhim": f"bhim://pay?{query}",
        }


def qr_png(data: str, *, box_size: int = 8, border: int = 3) -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_data_url(data: str) -> str:
    return "data:image/png;base64," + base64.b64encode(qr_png(data)).decode("ascii")


def normalize_utr(value: str) -> str:
    """Upper-case, strip spaces and separators. UPI UTRs are usually 12 digits; bank refs vary."""
    v = re.sub(r"[\s\-_/]", "", value).upper()
    if not re.fullmatch(r"[A-Z0-9]{6,35}", v):
        raise ValueError("Enter the UTR / transaction reference exactly as shown in your UPI app.")
    return v
