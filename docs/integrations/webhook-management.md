# Webhook management

Admin → **Developers → Webhooks** (n8n uses the same system).

* **Endpoints**: name, https URL (private and local addresses are refused on servers, re-checked at send time), events
  (or `*`), on/off. Up to 20 per clinic.
* **Secrets**: `whsec_…`, shown once, encrypted; **Rotate secret**.
* **Signing**: `X-Webhook-Signature: t=<unix>,v1=<HMAC-SHA256 of "<t>.<raw body>">`; reject anything older than 5
  minutes. Reference code: `backend/app/webhooks/security.py` (`verify`).
* **Outbox**: an event is stored in the same transaction as the change, so a rolled-back booking never sends one.
* **Delivery**: the worker sends with a 10-second timeout; retries after 1 min, 5 min, 30 min, 2 h, 6 h, 12 h, 24 h
  (`WEBHOOK_MAX_ATTEMPTS`), then "dead". 50 failures in a row switch the endpoint off (audit-logged).
* **No duplicate processing**: each event has one `X-Webhook-Id` (the same on retries and redelivery); store it and
  ignore repeats.
* **Logs**: status, attempts, response code and first 1,000 characters of the response; kept 30 days.
* **Redeliver**: any delivery can be sent again safely (same id).
* **Test**: sends a signed `ping` immediately.

Incoming webhooks this app accepts: WhatsApp delivery reports (`/api/v1/webhooks/whatsapp`, Meta signature) and n8n
actions (`/api/v1/automation/n8n/<id>`, signature + timestamp + one-time request id).
