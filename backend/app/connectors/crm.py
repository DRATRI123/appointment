"""HubSpot (private app token) and Zoho CRM (OAuth). Patients become contacts; appointments can be logged as notes.

Only the fields the clinic ticks are sent (name always; mobile, email, city optional). Clinical notes, documents, booking
form answers and payment details are never sent. Duplicates: the stored contact id first, then a search by email and
by phone, and only then a new contact.
"""
from __future__ import annotations

from datetime import UTC
from typing import Any
from zoneinfo import ZoneInfo

from app.connectors.base import Adapter, split_name, zoho_access_token, zoho_api_domain
from app.integrations.http import IntegrationAPIError, check, request

HUBSPOT = "https://api.hubapi.com"


def appointment_summary(db, appt) -> tuple[str, str]:
    """Title and body of an appointment note: what, when, with whom, status. Nothing clinical."""
    from app.models import Professional, Service

    svc, pro = db.get(Service, appt.service_id), db.get(Professional, appt.professional_id)
    local = appt.start_at.replace(tzinfo=appt.start_at.tzinfo or UTC).astimezone(ZoneInfo(appt.timezone or "Asia/Kolkata"))
    title = f"Appointment {appt.reference}"
    body = (f"{svc.name if svc else 'Appointment'} with {pro.display_name if pro else 'the clinic'} on "
            f"{local.strftime('%d %b %Y, %H:%M')} ({appt.timezone}). Status: {appt.status.replace('_', ' ')}.")
    return title, body


def ensure_contact(adapter: Adapter, customer) -> str:
    """The contact id for this patient in this system, creating it through the sync queue's mapping if needed."""
    from sqlalchemy import select

    from app.core.time import utcnow
    from app.models import IntegrationSyncItem

    db, integ = adapter.ctx.db, adapter.ctx.integ
    item = db.scalar(select(IntegrationSyncItem).where(IntegrationSyncItem.integration_id == integ.id, IntegrationSyncItem.entity_type == "customer",
                                                       IntegrationSyncItem.entity_id == customer.id))
    if item is not None and item.external_id:
        return item.external_id
    external = adapter.push("customer", customer, None)
    if item is None:
        item = IntegrationSyncItem(organization_id=integ.organization_id, integration_id=integ.id, entity_type="customer", entity_id=customer.id)
        db.add(item)
    item.external_id, item.status, item.synced_at, item.last_error = external, "synced", utcnow(), None
    db.flush()
    return external or ""


class HubSpot(Adapter):
    def headers(self) -> dict[str, str]:
        token = self.ctx.secrets().get("access_token")
        if not token:
            raise IntegrationAPIError("Enter the HubSpot private app access token.", reconnect=True)
        return {"Authorization": f"Bearer {token}"}

    def test(self) -> str:
        check(request("GET", f"{HUBSPOT}/crm/v3/objects/contacts", params={"limit": 1}, headers=self.headers()), "HubSpot contacts")
        return "Connected to HubSpot (contacts readable and writable)"

    def _properties(self, customer) -> dict[str, Any]:
        cfg = self.ctx.config
        first, last = split_name(customer.full_name)
        props: dict[str, Any] = {"firstname": first, "lastname": last}
        if cfg.get("include_email") and customer.email:
            props["email"] = customer.email
        if cfg.get("include_mobile") and customer.mobile:
            props["phone"] = customer.mobile
        if cfg.get("include_city") and (customer.address or {}).get("city"):
            props["city"] = customer.address["city"]
        return props

    def _search(self, customer) -> str | None:
        groups = []
        if customer.email:
            groups.append({"filters": [{"propertyName": "email", "operator": "EQ", "value": customer.email}]})
        if customer.mobile:
            groups.append({"filters": [{"propertyName": "phone", "operator": "EQ", "value": customer.mobile}]})
        if not groups:
            return None
        data = check(request("POST", f"{HUBSPOT}/crm/v3/objects/contacts/search", json={"filterGroups": groups, "properties": ["email"], "limit": 1},
                             headers=self.headers()), "Search HubSpot contacts")
        results = data.get("results") or []
        return str(results[0]["id"]) if results else None

    def push(self, entity_type: str, obj, external_id: str | None) -> str | None:
        if entity_type == "appointment":
            return self._note(obj, external_id)
        props = self._properties(obj)
        contact = external_id or self._search(obj)
        if contact:
            try:
                check(request("PATCH", f"{HUBSPOT}/crm/v3/objects/contacts/{contact}", json={"properties": props}, headers=self.headers()), "Update HubSpot contact")
                return contact
            except IntegrationAPIError as exc:
                if exc.status != 404:
                    raise
        created = check(request("POST", f"{HUBSPOT}/crm/v3/objects/contacts", json={"properties": props}, headers=self.headers()), "Create HubSpot contact")
        return str(created.get("id"))

    def _note(self, appt, external_id: str | None) -> str | None:
        from app.core.time import utcnow
        from app.models import Customer

        if not self.ctx.config.get("log_appointments"):
            return external_id
        title, body = appointment_summary(self.ctx.db, appt)
        props = {"hs_note_body": f"{title}: {body}", "hs_timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        if external_id:
            check(request("PATCH", f"{HUBSPOT}/crm/v3/objects/notes/{external_id}", json={"properties": {"hs_note_body": props["hs_note_body"]}},
                          headers=self.headers()), "Update HubSpot note")
            return external_id
        contact = ensure_contact(self, self.ctx.db.get(Customer, appt.customer_id))
        created = check(request("POST", f"{HUBSPOT}/crm/v3/objects/notes", json={"properties": props, "associations": [
            {"to": {"id": contact}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]},
            headers=self.headers()), "Create HubSpot note")
        return str(created.get("id"))

    def remove(self, entity_type: str, external_id: str) -> None:
        kind = "notes" if entity_type == "appointment" else "contacts"
        try:
            check(request("DELETE", f"{HUBSPOT}/crm/v3/objects/{kind}/{external_id}", headers=self.headers()), "Delete in HubSpot")
        except IntegrationAPIError as exc:
            if exc.status != 404:
                raise


def _zoho_result(data: dict[str, Any], what: str) -> str:
    rows = data.get("data") or []
    if not rows or rows[0].get("code") != "SUCCESS":
        detail = rows[0] if rows else data
        raise IntegrationAPIError(f"{what} failed: {str(detail.get('message') or detail)[:200]}", body=data)
    return str(rows[0]["details"]["id"])


class ZohoCRM(Adapter):
    def base(self) -> str:
        return f"{zoho_api_domain(self.ctx)}/crm/v7"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Zoho-oauthtoken {zoho_access_token(self.ctx)}"}

    def test(self) -> str:
        data = check(request("GET", f"{self.base()}/users", params={"type": "CurrentUser"}, headers=self.headers()), "Zoho CRM user")
        users = data.get("users") or [{}]
        return f"Connected as {users[0].get('email') or users[0].get('full_name') or 'Zoho user'}"

    def _record(self, customer) -> dict[str, Any]:
        cfg = self.ctx.config
        first, last = split_name(customer.full_name)
        rec: dict[str, Any] = {"First_Name": first, "Last_Name": last}
        if cfg.get("include_email") and customer.email:
            rec["Email"] = customer.email
        if cfg.get("include_mobile") and customer.mobile:
            rec["Mobile"] = customer.mobile
        if cfg.get("include_city") and (customer.address or {}).get("city"):
            rec["Mailing_City"] = customer.address["city"]
        return rec

    def _search(self, customer) -> str | None:
        for param, value in (("email", customer.email), ("phone", customer.mobile)):
            if not value:
                continue
            data = check(request("GET", f"{self.base()}/Contacts/search", params={param: value, "fields": "id"}, headers=self.headers()), "Search Zoho contacts")
            rows = data.get("data") or []  # 204 No Content when nothing matches
            if rows:
                return str(rows[0]["id"])
        return None

    def push(self, entity_type: str, obj, external_id: str | None) -> str | None:
        if entity_type == "appointment":
            return self._note(obj, external_id)
        rec = self._record(obj)
        contact = external_id or self._search(obj)
        if contact:
            try:
                return _zoho_result(check(request("PUT", f"{self.base()}/Contacts/{contact}", json={"data": [rec]}, headers=self.headers()),
                                          "Update Zoho contact"), "Update Zoho contact")
            except IntegrationAPIError as exc:
                if exc.status not in (400, 404):
                    raise
        return _zoho_result(check(request("POST", f"{self.base()}/Contacts", json={"data": [rec]}, headers=self.headers()), "Create Zoho contact"),
                            "Create Zoho contact")

    def _note(self, appt, external_id: str | None) -> str | None:
        from app.models import Customer

        if not self.ctx.config.get("log_appointments"):
            return external_id
        title, body = appointment_summary(self.ctx.db, appt)
        if external_id:
            _zoho_result(check(request("PUT", f"{self.base()}/Notes/{external_id}", json={"data": [{"Note_Title": title, "Note_Content": body}]},
                                       headers=self.headers()), "Update Zoho note"), "Update Zoho note")
            return external_id
        contact = ensure_contact(self, self.ctx.db.get(Customer, appt.customer_id))
        return _zoho_result(check(request("POST", f"{self.base()}/Contacts/{contact}/Notes", json={"data": [{"Note_Title": title, "Note_Content": body}]},
                                          headers=self.headers()), "Create Zoho note"), "Create Zoho note")

    def remove(self, entity_type: str, external_id: str) -> None:
        module = "Notes" if entity_type == "appointment" else "Contacts"
        try:
            check(request("DELETE", f"{self.base()}/{module}/{external_id}", headers=self.headers()), "Delete in Zoho CRM")
        except IntegrationAPIError as exc:
            if exc.status != 404:
                raise
