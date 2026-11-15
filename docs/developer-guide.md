# Developer guide

How to connect a website, app, CRM, accounting or automation tool to a clinic on this platform. The same
content, with live code samples in curl, Python, Node.js and PHP that use your own address, is in the admin under
**Developer docs** (`/admin/developers/docs`). Every sample there was run against a real server before release.

| You want to… | Use | Section |
|---|---|---|
| Put booking on a website, Shopify, Instagram or WhatsApp | Booking link or iframe | [Links and embed](#links-and-embed) |
| Hear about new, changed, paid or cancelled bookings | Webhooks | [Webhooks](#webhooks) |
| Book or read appointments from your own server | REST API with an API key | [REST API](#rest-api) |
| Build your own patient app or kiosk | Public booking API (no key) | [Public booking API](#public-booking-api) |
| Pull numbers into accounting or BI | Reports API | [Reports](#reports) |

Related references: [`api.md`](api.md) (every endpoint by module), [`public-booking-api.md`](public-booking-api.md)
(public endpoints with recorded examples), [`shopify-integration.md`](shopify-integration.md), and the generated
OpenAPI reference at `/docs` and `/api/v1/openapi.json`.

## Rules the server always enforces

* **No double booking.** Two requests for one slot: exactly one succeeds, the other gets `409 slot_unavailable`.
* **Server-side prices.** Amounts in requests are ignored; the price comes from the catalogue, branch pricing,
  doctor fee, coupon and tax.
* **API keys never touch money.** Recording, verifying and refunding payments is staff-only (`403 api_key_not_allowed`
  or `403 permission_denied` for keys). Only a payment with status `verified` is paid.
* **One clinic per key**, and no clinical notes, documents or form uploads through keys or webhooks.

## REST API

Base URL `https://<booking-site>/api/v1`. JSON in and out.

### API keys

Create keys under **Admin → Developers → API keys** (permission `api_keys:manage`). The key is shown once.

```
Authorization: Bearer ak_live_<8-char id>_<secret>     (or X-API-Key: …)
```

* A key acts inside one organization; no `X-Organization-Id` is needed (a different one gives `403 wrong_organization`).
* Effective access = key scopes ∩ the creator's current role permissions. If the creator leaves, the key stops
  (`401 api_key_owner_removed`). Create integration keys from a long-lived administrator.
* Optional allowed IPs / CIDR ranges (`403 ip_not_allowed`), expiry date, and rate limit (default 120/min, 1–1,200;
  `429 rate_limited` with `Retry-After`). Up to 25 active keys per clinic.
* Only a peppered HMAC of the key is stored. Never put a key in a browser, mobile app or theme.
* Rotate: create a second key, deploy it, check usage, revoke the old one.

| Scope | Allows |
|---|---|
| `appointments:read` | Appointments, calendar, availability, waitlist |
| `appointments:write` | Book, hold, reschedule, cancel, confirm, expire |
| `appointments:checkin` | Check in, start, complete, no-show |
| `customers:read` / `customers:write` | Customers and family members (no clinical notes or documents) |
| `services:read`, `branches:read`, `professionals:read` | Catalogue, doctors and schedules |
| `payments:read` | Payment status only |
| `booking_forms:read` | Booking forms |
| `reports:read` | Dashboard and report previews |

Keys can only call: appointments, availability, waitlist, branches, professionals, schedules, services,
service-categories, service-packages, customers, payments, booking-forms, reports, analytics.

### Conventions

* IDs are UUID strings; appointments, payments and refunds also have a human `reference`.
* Timestamps are ISO 8601; responses are UTC. Dates in query strings are in the clinic time zone (`timezone`).
* Money is integer paise (`80000` = ₹800.00).
* Paged lists return `{"data": [...], "meta": {"page", "page_size", "total"}}`; appointments use `from_at`/`to_at`.
* Errors: `{"detail", "code", "request_id", "errors"?}`. Branch on `code`; quote `request_id` for support.
* Retrying: GETs are safe. Send `Idempotency-Key: <uuid>` on `POST /appointments`; repeating the same request with
  the same key returns the first response (`Idempotent-Replayed: true`) and books nothing twice (24 h; a different
  body with the same key is `422 idempotency_key_reused`). Without a key, a repeat for the same slot returns
  `409 slot_unavailable` instead of a duplicate. Back off on `5xx`; honour `Retry-After` on `429`.

### Booking from your server

```bash
# 1. ids
curl "$BASE/services" -H "Authorization: Bearer $API_KEY"
# 2. free times
curl "$BASE/availability?service_id=…&branch_id=…&date=2026-11-20" -H "Authorization: Bearer $API_KEY"
# 3. (optional) hold while you talk to the patient
curl -X POST "$BASE/appointments/holds" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"professional_id":"…","branch_id":"…","service_id":"…","start_at":"2026-11-20T05:30:00Z"}'
# 4. book (with hold_id, or the four fields directly)
curl -X POST "$BASE/appointments" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"hold_id":"…","customer":{"full_name":"Asha Patel","mobile":"9812345678"},"source":"api"}'
```

An existing customer with the same mobile is linked; otherwise one is created. With an advance due the
appointment is `pending_payment`; the clinic's own notifications (with the UPI payment link) go out as configured.
`confirm_without_payment: true` confirms without recording any payment.

Status actions (`POST /appointments/{id}/status` with `{"action", "reason"?}`):

| action | scope | from |
|---|---|---|
| `confirm` | write | pending_payment, pending_verification |
| `cancel` | write | pending_payment, pending_verification, confirmed, checked_in |
| `expire` | write | pending_payment |
| `check_in` | checkin | confirmed, pending_payment |
| `start` | checkin | confirmed, checked_in |
| `complete` | checkin | confirmed, checked_in, in_progress |
| `no_show` | checkin | confirmed, pending_payment, checked_in |

Other changes return `409 invalid_transition`. Reschedule: `POST /appointments/{id}/reschedule` with `start_at`
(+ `professional_id`) or `hold_id`.

### Reports

`GET /analytics/dashboard?from&to&branch_id&professional_id&service_id`, `GET /reports` (what this key may run),
`GET /reports/{key}?from&to&page&page_size` for `appointments`, `payments`, `refunds`, `daily_summary`,
`professionals`, `services`, `customers`, `cancellations`, `tax_summary`, `coupons`. Some reports also need
`payments:read` or `customers:read`. File exports are staff-only.

## Webhooks

Add endpoints under **Admin → Developers → Webhooks** (HTTPS, public address, no credentials in the URL; up to
20). The `whsec_…` signing secret is shown once. **Send test** delivers a signed `ping` at once.

Request: `POST` JSON `{id, type, api_version: "2026-11", created_at, organization: {id, slug}, data}` with headers
`X-Webhook-Id`, `X-Webhook-Event`, `X-Webhook-Timestamp`, `X-Webhook-Signature: t=<unix>,v1=<hex>`.

`v1 = hex(HMAC-SHA256(secret, "<t>." + raw_body))`. Verify on the raw body with a constant-time compare and reject
timestamps older than five minutes:

```python
import hashlib, hmac, time

def valid(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))
```

Node.js (Express with `express.raw`) and PHP receivers are in the in-app docs; all three were tested against
real deliveries, including rejection of a forged signature.

| Behaviour | Detail |
|---|---|
| Success | any 2xx within 10 s; redirects are not followed |
| Retries | 8 attempts: after 1 m, 5 m, 30 m, 2 h, 6 h, 12 h, 24 h; then dead (can be resent by hand) |
| Duplicates | retries keep the same `X-Webhook-Id`; de-duplicate on it |
| Order | not guaranteed; compare `created_at` or fetch the object |
| Auto-pause | after 50 consecutive failures; Resume resets the counter; events while paused are not stored |
| Log | every attempt for 30 days, with payload, status and response; Resend available |
| Rotation | Rotate secret: the new secret applies immediately; failed deliveries in between are retried |

Events: `appointment.created`, `.confirmed`, `.rescheduled` (adds `previous_start_at`), `.cancelled`, `.expired`,
`.checked_in`, `.completed`, `.no_show`; `payment.submitted` (**not** paid), `payment.verified` (paid),
`payment.rejected`; `refund.processed`; `ping`. Payloads hold public ids and contact details only.

Tip: run a nightly job that lists yesterday's appointments and fixes any differences: webhooks are a fast path,
not a database.

## Public booking API

`/api/v1/public/organizations/{slug}/…`. No key, rate limited, safe for browsers and apps. Flow: catalogue →
`availability/summary` → `availability` → `quote` → `holds` (with a random `session_key`) → `verification/start` →
`verification/{id}/verify` → `appointments` (with `verification_token`) → `appointments/{ref}/payment`. The token is
bound to the clinic, hold, session and the exact mobile or email, for 30 minutes. Codes are never returned or logged.
Details and recorded examples: [`public-booking-api.md`](public-booking-api.md).

## Links and embed

```
https://<booking-site>/<clinic>/book?service=<slug>&branch=<slug>&doctor=<slug>&date=YYYY-MM-DD&utm_source=…
https://<booking-site>/embed/<clinic>     iframe version; add your site under Allowed websites first
```

Parameters are hints only; unknown values are ignored and they never change prices or permissions. The iframe posts
`{type: "appointment-booking:resize", height}` to the parent. Shopify: [`shopify-integration.md`](shopify-integration.md).

## Go-live checklist

* One key per system, minimum scopes, allowed IPs on production keys, expiry for contractors.
* Keys and webhook secrets only in server-side secret storage.
* Receiver verifies signatures on the raw body, rejects old timestamps, de-duplicates `X-Webhook-Id`, answers in 10 s.
* Handle `409 slot_unavailable`, `429` + `Retry-After`, `5xx` with backoff.
* Show money from paise and times in the clinic time zone; treat only `verified` payments as paid.
* Nightly reconciliation against `GET /appointments`; someone watches key usage and webhook failures in Developers.
