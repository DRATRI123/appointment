"""Gmail (send only), Google Contacts (People API) and Google Drive (files this app created only, drive.file scope).

All three use the clinic's own Google account, connected with OAuth 2.0 through the platform's Google Cloud client
(Super admin → Integrations → Google). Tokens are stored encrypted and refreshed automatically.
"""
from __future__ import annotations

import json
import secrets as pysecrets
from typing import Any
from urllib.parse import quote

from app.connectors.base import Adapter, google_access_token, split_name
from app.integrations import google_calendar as gcal
from app.integrations.http import IntegrationAPIError, check, request

PEOPLE = "https://people.googleapis.com/v1"
DRIVE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"


class _Google(Adapter):
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {google_access_token(self.ctx)}"}

    def test(self) -> str:
        email = gcal.account_email(google_access_token(self.ctx))
        return f"Connected as {email}"


class Gmail(_Google):
    def provider(self):
        from app.notifications.providers import GmailProvider

        return GmailProvider(lambda: google_access_token(self.ctx), self.ctx.integ.external_account_id or "")


class Contacts(_Google):
    def _body(self, customer) -> dict[str, Any]:
        cfg = self.ctx.config
        given, family = split_name(customer.full_name)
        body: dict[str, Any] = {"names": [{"givenName": given or family, "familyName": family if given else ""}]}
        if cfg.get("include_mobile") and customer.mobile:
            body["phoneNumbers"] = [{"value": customer.mobile, "type": "mobile"}]
        if cfg.get("include_email") and customer.email:
            body["emailAddresses"] = [{"value": customer.email}]
        return body

    def _find(self, customer) -> str | None:
        """Duplicate check before creating: a contact with the same number or email."""
        h = self.headers()
        check(request("GET", f"{PEOPLE}/people:searchContacts", params={"query": "", "readMask": "names"}, headers=h), "Search contacts")  # warm-up
        for q in (customer.mobile, customer.email):
            if not q:
                continue
            data = check(request("GET", f"{PEOPLE}/people:searchContacts", params={"query": q, "readMask": "phoneNumbers,emailAddresses"}, headers=h),
                         "Search contacts")
            for hit in data.get("results") or []:
                person = hit.get("person") or {}
                numbers = {p.get("value", "").replace(" ", "") for p in person.get("phoneNumbers", [])}
                emails = {e.get("value", "").lower() for e in person.get("emailAddresses", [])}
                if (customer.mobile and customer.mobile in numbers) or (customer.email and customer.email.lower() in emails):
                    return person.get("resourceName")
        return None

    def push(self, entity_type: str, customer, external_id: str | None) -> str | None:
        h = self.headers()
        body = self._body(customer)
        resource = external_id or self._find(customer)
        if resource:
            try:
                current = check(request("GET", f"{PEOPLE}/{resource}", params={"personFields": "metadata"}, headers=h), "Read contact")
            except IntegrationAPIError as exc:
                if exc.status != 404:
                    raise
                resource = None  # deleted in Google: create it again
            else:
                fields = ",".join(body)  # only the fields this clinic sends; others the clinic added in Google stay as they are
                check(request("PATCH", f"{PEOPLE}/{resource}:updateContact", params={"updatePersonFields": fields},
                              json={**body, "etag": current.get("etag")}, headers=h), "Update contact")
                return resource
        created = check(request("POST", f"{PEOPLE}/people:createContact", params={"personFields": "names"}, json=body, headers=h), "Create contact")
        return created.get("resourceName")

    def remove(self, entity_type: str, external_id: str) -> None:
        try:
            check(request("DELETE", f"{PEOPLE}/{external_id}:deleteContact", headers=self.headers()), "Delete contact")
        except IntegrationAPIError as exc:
            if exc.status != 404:
                raise


class Drive(_Google):
    def _folder(self) -> str:
        folder = self.ctx.state("folder_id")
        if folder:
            return folder
        meta = {"name": self.ctx.config.get("folder_name") or "Patient documents", "mimeType": "application/vnd.google-apps.folder"}
        created = check(request("POST", f"{DRIVE}/files", params={"fields": "id"}, json=meta, headers=self.headers()), "Create folder")
        self.ctx.set_state(folder_id=created["id"])
        return created["id"]

    def push(self, entity_type: str, document, external_id: str | None) -> str | None:
        from app.core.storage import get_storage
        from app.models import Customer

        if external_id:
            return external_id  # documents do not change after upload
        customer = self.ctx.db.get(Customer, document.customer_id)
        with get_storage().open(document.storage_path) as fh:
            data = fh.read()
        ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(document.mime_type, "bin")
        name = f"{(customer.customer_code or customer.full_name) if customer else 'patient'} - {document.title}.{ext}"[:200]
        for attempt in (1, 2):
            metadata = {"name": name, "parents": [self._folder()], "appProperties": {"appointment_platform_document": document.public_id}}
            boundary = f"=={pysecrets.token_hex(12)}"
            body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\nContent-Type: {document.mime_type}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
            try:
                created = check(request("POST", DRIVE_UPLOAD, params={"uploadType": "multipart", "fields": "id"}, content=body,
                                        headers={**self.headers(), "Content-Type": f"multipart/related; boundary={boundary}"}), "Upload to Drive")
                return created.get("id")
            except IntegrationAPIError as exc:
                if exc.status == 404 and attempt == 1:  # the folder was deleted in Drive: make a new one
                    self.ctx.set_state(folder_id=None)
                    continue
                raise
        return None

    def remove(self, entity_type: str, external_id: str) -> None:
        try:
            check(request("DELETE", f"{DRIVE}/files/{quote(external_id, safe='')}", headers=self.headers()), "Delete from Drive")
        except IntegrationAPIError as exc:
            if exc.status != 404:
                raise
