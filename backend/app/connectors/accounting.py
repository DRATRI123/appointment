"""Zoho Books (OAuth) and Tally (XML import file). Only verified payments and processed refunds are ever sent.

Zoho Books: a verified payment becomes an invoice plus a customer payment applied to it; a refund becomes a credit note
(and a credit-note refund when a refund account is set). Each step's id is saved as soon as Zoho returns it, so a retry
continues where it stopped and never creates a second invoice. Zoho's own docs allow refunds of customer payments only
for online card payments, which is why UPI/cash refunds go through credit notes.

Tally has no cloud API: the clinic downloads an XML file (Gateway of Tally → Import → Vouchers). Each voucher carries
the payment's id as REMOTEID, and payments already exported are left out of the next file unless asked for.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.connectors.base import Adapter, split_name, zoho_access_token, zoho_api_domain
from app.core.enums import PaymentStatus, RefundStatus
from app.integrations.http import IntegrationAPIError, check, request

MODES = {"upi_qr": "UPI", "cash": "Cash", "bank_transfer": "Bank Transfer", "pay_at_clinic": "Cash", "upi": "UPI"}


def rupees(paise: int | None) -> float:
    return round((paise or 0) / 100, 2)


def _local_date(dt: datetime | None, tz: str) -> date:
    dt = dt or datetime.now(UTC)
    return dt.replace(tzinfo=dt.tzinfo or UTC).astimezone(ZoneInfo(tz or "Asia/Kolkata")).date()


def _parts(external_id: str | None) -> dict[str, str]:
    out = {}
    for part in (external_id or "").split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k] = v
    return out


def _join(parts: dict[str, str]) -> str:
    return "|".join(f"{k}:{v}" for k, v in parts.items())


class ZohoBooks(Adapter):
    progress = None  # set by the sync queue: saves partial ids immediately

    def base(self) -> str:
        return f"{zoho_api_domain(self.ctx)}/books/v3"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Zoho-oauthtoken {zoho_access_token(self.ctx)}"}

    def params(self) -> dict[str, str]:
        org = self.ctx.config.get("organization_id")
        if not org:
            raise IntegrationAPIError("Choose the Zoho Books organization first (press Test).")
        return {"organization_id": str(org)}

    def test(self) -> str:
        data = check(request("GET", f"{self.base()}/organizations", headers=self.headers()), "Zoho Books organizations")
        orgs = data.get("organizations") or []
        if not orgs:
            raise IntegrationAPIError("This Zoho account has no Zoho Books organization.")
        chosen = next((o for o in orgs if str(o.get("organization_id")) == str(self.ctx.config.get("organization_id"))), None)
        if chosen is None:
            chosen = orgs[0]
            self.ctx.integ.config = {**(self.ctx.integ.config or {}), "organization_id": str(chosen["organization_id"])}
        return f"Connected to {chosen.get('name')} (organization {chosen['organization_id']})"

    def _save(self, parts: dict[str, str]) -> None:
        if self.progress:
            self.progress(_join(parts))

    def _contact(self, customer) -> str:
        from app.connectors.crm import ensure_contact

        return ensure_contact(self, customer)

    def push(self, entity_type: str, obj, external_id: str | None) -> str | None:
        if entity_type == "customer":
            return self._create_contact(obj, external_id)
        if entity_type == "payment":
            return self._payment(obj, external_id)
        if entity_type == "refund":
            return self._refund(obj, external_id)
        return super().push(entity_type, obj, external_id)

    def _create_contact(self, customer, external_id: str | None) -> str:
        if external_id:
            return external_id
        first, last = split_name(customer.full_name)
        person: dict[str, Any] = {"first_name": first, "last_name": last, "is_primary_contact": True}
        if customer.email:
            person["email"] = customer.email
        if customer.mobile:
            person["mobile"] = customer.mobile
        name = f"{customer.full_name} ({customer.customer_code})" if customer.customer_code else customer.full_name  # names must be unique in Zoho Books
        data = check(request("POST", f"{self.base()}/contacts", params=self.params(), json={"contact_name": name[:200], "contact_type": "customer",
                                                                                            "contact_persons": [person]}, headers=self.headers()), "Create Zoho Books contact")
        return str(data["contact"]["contact_id"])

    def _payment(self, payment, external_id: str | None) -> str | None:
        from app.models import Appointment, Customer, PaymentSubmission, Service

        if payment.status != PaymentStatus.VERIFIED or payment.customer_id is None:
            return external_id  # only verified payments are sent
        db, tz = self.ctx.db, self.ctx.org.timezone
        parts = _parts(external_id)
        customer = db.get(Customer, payment.customer_id)
        contact = self._contact(customer)
        appt = db.get(Appointment, payment.appointment_id) if payment.appointment_id else None
        svc = db.get(Service, appt.service_id) if appt else None
        amount = rupees(payment.verified_amount_paise or payment.amount_paise)
        day = _local_date(payment.verified_at, tz).isoformat()
        if "inv" not in parts:
            inv = check(request("POST", f"{self.base()}/invoices", params=self.params(), headers=self.headers(), json={
                "customer_id": contact, "date": day, "reference_number": (appt.reference if appt else payment.reference)[:50],
                "line_items": [{"name": (svc.name if svc else "Appointment")[:100], "rate": amount, "quantity": 1}]}), "Create Zoho Books invoice")
            parts["inv"] = str(inv["invoice"]["invoice_id"])
            self._save(parts)
        if "pay" not in parts:
            utr = db.scalar(select(PaymentSubmission.utr).where(PaymentSubmission.payment_id == payment.id, PaymentSubmission.is_superseded.is_(False))
                            .order_by(PaymentSubmission.id.desc()))
            pay = check(request("POST", f"{self.base()}/customerpayments", params=self.params(), headers=self.headers(), json={
                "customer_id": contact, "payment_mode": MODES.get(payment.method, "Cash"), "amount": amount, "date": day,
                "reference_number": (utr or payment.reference)[:50], "invoices": [{"invoice_id": parts["inv"], "amount_applied": amount}]}),
                "Record Zoho Books payment")
            parts["pay"] = str(pay["payment"]["payment_id"])
        return _join(parts)

    def _refund(self, refund, external_id: str | None) -> str | None:
        from app.models import Customer, Payment

        if refund.status != RefundStatus.PROCESSED:
            return external_id
        db = self.ctx.db
        payment = db.get(Payment, refund.payment_id)
        if payment is None or payment.customer_id is None:
            return external_id
        parts = _parts(external_id)
        contact = self._contact(db.get(Customer, payment.customer_id))
        amount, day = rupees(refund.amount_paise), _local_date(refund.processed_at, self.ctx.org.timezone).isoformat()
        if "cn" not in parts:
            cn = check(request("POST", f"{self.base()}/creditnotes", params=self.params(), headers=self.headers(), json={
                "customer_id": contact, "date": day, "reference_number": refund.reference[:50],
                "line_items": [{"name": f"Refund for {payment.reference}"[:100], "rate": amount, "quantity": 1}]}), "Create Zoho Books credit note")
            parts["cn"] = str(cn["creditnote"]["creditnote_id"])
            self._save(parts)
        account = self.ctx.config.get("refund_account_id")
        if account and "rf" not in parts:
            rf = check(request("POST", f"{self.base()}/creditnotes/{parts['cn']}/refunds", params=self.params(), headers=self.headers(), json={
                "date": day, "refund_mode": MODES.get(refund.refund_method or "", "Cash"), "amount": amount, "from_account_id": account,
                "reference_number": (refund.refund_reference or refund.reference)[:50]}), "Record Zoho Books refund")
            parts["rf"] = str((rf.get("creditnote_refund") or {}).get("creditnote_refund_id") or "done")
        return _join(parts)


# ============================================================================================================ Tally
class Tally(Adapter):
    def test(self) -> str:
        missing = [k for k in ("bank_ledger", "cash_ledger", "income_ledger") if not self.ctx.config.get(k)]
        if missing:
            raise IntegrationAPIError("Fill in the ledger names.")
        return "Ready: download the file and import it in Tally (Gateway of Tally → Import → Vouchers)"


def _voucher(kind: str, remote_id: str, day: date, number: str, reference: str, narration: str, debit: str, credit: str, amount: float) -> str:
    """Tally convention: a debit is a negative amount with ISDEEMEDPOSITIVE Yes."""
    e = lambda v: escape(str(v))  # noqa: E731
    return (f'<TALLYMESSAGE xmlns:UDF="TallyUDF"><VOUCHER REMOTEID="{e(remote_id)}" VCHTYPE="{kind}" ACTION="Create" OBJVIEW="Accounting Voucher View">'
            f"<DATE>{day.strftime('%Y%m%d')}</DATE><VOUCHERTYPENAME>{kind}</VOUCHERTYPENAME><VOUCHERNUMBER>{e(number)}</VOUCHERNUMBER>"
            f"<REFERENCE>{e(reference)}</REFERENCE><NARRATION>{e(narration)}</NARRATION>"
            f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{e(debit)}</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-{amount:.2f}</AMOUNT></ALLLEDGERENTRIES.LIST>"
            f"<ALLLEDGERENTRIES.LIST><LEDGERNAME>{e(credit)}</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{amount:.2f}</AMOUNT></ALLLEDGERENTRIES.LIST>"
            "</VOUCHER></TALLYMESSAGE>")


def tally_export(db, org, integ, *, start: date, end: date, branch_id: int | None, include_exported: bool) -> tuple[str, int]:
    """Receipt vouchers for verified payments and Payment vouchers for processed refunds, dated in the clinic's timezone.
    Returns (xml, number of vouchers). Exported items are remembered so the next file has only new ones."""
    from app.core.time import utcnow
    from app.models import Customer, IntegrationSyncItem, Payment, PaymentRefund, PaymentSubmission

    cfg = {**{"bank_ledger": "Bank Account", "cash_ledger": "Cash", "income_ledger": "Consultation Fees"}, **(integ.config or {})}
    tz = org.timezone or "Asia/Kolkata"
    exported = set() if include_exported else {(r.entity_type, r.entity_id) for r in db.scalars(
        select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id, IntegrationSyncItem.status == "synced")).all()}
    out, rows = [], []
    pays = db.scalars(select(Payment).where(Payment.organization_id == org.id, Payment.status == PaymentStatus.VERIFIED, Payment.verified_at.is_not(None))
                      .order_by(Payment.verified_at)).all()
    for p in pays:
        day = _local_date(p.verified_at, tz)
        if not (start <= day <= end) or (branch_id and p.branch_id != branch_id) or ("payment", p.id) in exported:
            continue
        cust = db.get(Customer, p.customer_id) if p.customer_id else None
        utr = db.scalar(select(PaymentSubmission.utr).where(PaymentSubmission.payment_id == p.id, PaymentSubmission.is_superseded.is_(False))
                        .order_by(PaymentSubmission.id.desc()))
        ledger = cfg["cash_ledger"] if p.method in ("cash", "pay_at_clinic") else cfg["bank_ledger"]
        out.append(_voucher("Receipt", p.public_id, day, p.reference, utr or "", f"{cust.full_name if cust else 'Patient'} · {p.reference}",
                            ledger, cfg["income_ledger"], rupees(p.verified_amount_paise or p.amount_paise)))
        rows.append(("payment", p.id))
    refunds = db.scalars(select(PaymentRefund).where(PaymentRefund.organization_id == org.id, PaymentRefund.status == RefundStatus.PROCESSED)).all()
    for r in refunds:
        day = _local_date(r.processed_at, tz)
        pay = db.get(Payment, r.payment_id)
        if not (start <= day <= end) or (branch_id and pay and pay.branch_id != branch_id) or ("refund", r.id) in exported:
            continue
        ledger = cfg["cash_ledger"] if r.refund_method == "cash" else cfg["bank_ledger"]
        out.append(_voucher("Payment", r.public_id, day, r.reference, r.refund_reference or "", f"Refund {r.reference} for {pay.reference if pay else ''}",
                            cfg["income_ledger"], ledger, rupees(r.amount_paise)))
        rows.append(("refund", r.id))
    company = f"<STATICVARIABLES><SVCURRENTCOMPANY>{escape(cfg['company_name'])}</SVCURRENTCOMPANY></STATICVARIABLES>" if cfg.get("company_name") else ""
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>'
           f"<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>{company}</REQUESTDESC><REQUESTDATA>" + "".join(out) +
           "</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>\n")
    now = utcnow()
    for entity_type, entity_id in rows:
        item = db.scalar(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id, IntegrationSyncItem.entity_type == entity_type,
                                                           IntegrationSyncItem.entity_id == entity_id))
        if item is None:
            item = IntegrationSyncItem(organization_id=org.id, integration_id=integ.id, entity_type=entity_type, entity_id=entity_id)
            db.add(item)
        item.status, item.synced_at, item.external_id = "synced", now, "tally-export"
    integ.last_synced_at = now
    db.flush()
    return xml, len(rows)
