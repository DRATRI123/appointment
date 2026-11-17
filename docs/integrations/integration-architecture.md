# Integration Hub: how it is built

Simple version: the appointment app stays the boss. Every outside service (Google, Gmail, WhatsApp, SMS, n8n, CRM,
accounting, storage, analytics) is a plug-in that can be switched on and off, tested, and watched, without changing how
bookings, payments or permissions work.

## Two levels: platform (super admin) and clinic (admin)

| What | Super admin (platform) | Clinic admin (each clinic) |
|---|---|---|
| Google | **Google sign-in only**: the key behind the "Sign in with Google" button | **Google Cloud app** (own client ID and secret) for doctors' Calendar and Meet, Gmail, Contacts, Drive. Required: the platform's key is never used for clinic connections |
| File storage | Platform storage (this server or an S3 bucket) and the off-site backup copy | Optional **own S3 bucket** for the clinic's private files; without it the platform storage is used |
| Email / SMS / WhatsApp | Default providers for clinics without their own account | Own SMTP / MSG91 / Twilio / Meta WhatsApp account (Settings → OTP & verification) and Gmail: they send **all** the clinic's messages; the platform's provider is the fallback |
| Error tracking | Sentry | – |
| n8n, HubSpot, Zoho CRM, Zoho Books, Tally, GA4 / Tag Manager, Zoom, webhooks, API keys, Shopify / website | – | Each clinic its own |
| Admin panel inside the clinic's own app | – | **Panel in your app**: the clinic's app shows the admin panel in an iframe, with its own sign-in ([embedded-admin.md](embedded-admin.md)) |

Rule of thumb: the super admin sets what the platform itself needs; everything that acts for one clinic, with that
clinic's own accounts and data, is set by that clinic.

## Where to find it

| Who | Screen | What |
|---|---|---|
| Clinic admin | **Admin → Integrations** | Every integration of the clinic as a card: status, on/off, Configure, last sync, errors. Filter by category, search. |
| Clinic admin | **Admin → Integrations → (one card)** | Settings, connect / disconnect, test, synchronisation queue, history, setup guide, rotate secrets. |
| Clinic admin | **Admin → Integrations → Calendar & video** | Google Calendar, Google Meet and Zoom for each doctor (existing screen, moved here). |
| Super admin | **Super admin → Integrations** | Platform settings: file storage (S3), backups, Google OAuth client, default email/SMS/WhatsApp, Sentry. |

Categories: Google services, Calendar & video, Email, WhatsApp Business, SMS, n8n automation, Shopify, Website, CRM,
Accounting, Cloud storage, Analytics & monitoring, External API, Webhooks.

## Settings: `.env` or the panel

Platform settings can live in the server's `.env` **or** in Super admin → Integrations. A value saved in the panel wins;
each field shows **saved here**, **from .env** or **default**, and "use .env" removes the panel value. Panel secrets are
encrypted with `DATA_ENCRYPTION_KEY` (AES-256-GCM) in one `system_settings` row and are never shown again (only the last
four characters). Every process re-reads the row every 10 seconds, so no restart is needed (except Sentry).

You can also go the other way: **Download as .env lines** (secrets only if you ask, after confirming it is you), and on a
development computer **Also save into backend/.env** (a copy of the old file is kept as `.env.before-integrations`).

Never in the panel: `DATABASE_URL`, `SECRET_KEY`, `DATA_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY` (the encryption key
protects the panel values themselves).

## Pieces

| Piece | File | Job |
|---|---|---|
| Platform settings | `backend/app/services/platform_config.py` | Field definitions, panel/env resolution, encryption, `.env` export |
| Platform tests | `backend/app/services/platform_tests.py` | Real checks: S3 write/read/delete, Google token endpoint, test message, DSN |
| Storage switch | `backend/app/services/storage_migration.py` | Copy + verify every file, then switch, with fallback reads |
| Connector catalogue | `backend/app/connectors/registry.py` | One entry per clinic integration: category, sign-in type, fields, scopes, what it syncs |
| Adapters | `backend/app/connectors/{google,crm,accounting,n8n,analytics}.py` | `test()`, `push()`, `remove()` for each provider |
| Sync queue | `backend/app/connectors/sync.py` | Pending → sent, with retries and backoff, run by the worker |
| Hub service / API | `backend/app/services/connector_service.py`, `backend/app/api/v1/integration_hub.py` | Overview, settings, OAuth, tests, logs, retry |
| Message providers | `backend/app/notifications/providers.py` | SMTP, Brevo, Amazon SES, Gmail, MSG91, Twilio, 2Factor, Amazon SNS, Meta WhatsApp, fallback |
| Provider callbacks | `backend/app/api/v1/provider_webhooks.py` | WhatsApp delivery/read reports and STOP replies |
| n8n incoming | `backend/app/services/automation_service.py` | Signed, replay-protected actions |

Adding a provider = one catalogue entry + one adapter class. Booking, payment and permission code is not touched.

## Database

The master prompt listed tables; existing tables were reused where they already did the job.

| Asked for | Here |
|---|---|
| integrations, integration_credentials, oauth_connections, integration_settings | `integrations` (one row per clinic and provider; settings in `config`, secrets and OAuth tokens encrypted in `credentials_encrypted`) |
| integration_logs, sync_logs | `integration_logs` (tests, sign-ins, every sync attempt; kept 30 days) |
| sync_jobs, integration_events | `integration_sync_items` (new): one row per record and system, with `external_id`, status, attempts, next try |
| webhook_endpoints, webhook_subscriptions, webhook_deliveries | `webhook_endpoints` (events list = subscriptions), `webhook_events` (deliveries) |
| notification_templates, notification_jobs, notification_logs | `notification_templates`, `notifications` (the job queue), `notification_logs` |
| storage_providers, storage_objects | platform settings (provider) + the storage itself; file keys and metadata stay on each record (documents, payments) |
| api_keys, api_access_logs | `api_keys`, `api_key_usage` (daily counts), `api_access_logs` (new: one row per request, 30 days) |
| (extra) | `automation_requests` (n8n replay protection), `follow_up_tasks` (tasks from staff or n8n) |

Migration `09efabf3a653` only adds the four new tables.

## Status rules

* **Connected**: only after a real successful test with the saved settings, or a completed OAuth sign-in whose account
  was read back. Changing a setting or secret makes it **Not tested yet** again.
* **Active**: configured, but the provider cannot be checked from the server (GA4 / Tag Manager IDs).
* **Needs attention**: the last test or sync failed, or the access was revoked (reconnect).
* **Not connected / Not set up / Switched off**.

## Reliability and security

* External calls never happen inside a booking request. Changes are queued (sync queue, notification queue, webhook
  outbox) and the worker sends them. A provider being down delays a copy, never a booking.
* Timeouts on every call (`INTEGRATION_HTTP_TIMEOUT_SECONDS`), retries with growing waits (1 min, 5 min, 30 min, 2 h,
  6 h, 12 h, 24 h), a retry limit per integration (1–20), then "stopped" with a Retry button (dead-letter).
* Idempotency: one sync row per record and system, the external id is reused (no duplicate contacts or invoices),
  multi-step pushes save each step at once, unchanged data is not re-sent.
* OAuth state is signed, expires in 10 minutes and works once. Tokens are encrypted and refreshed automatically.
* Every change is audit-logged without secret values. Saving settings asks to confirm it is you.
* Tenant and branch checks: each integration belongs to one clinic; Tally export respects a branch-limited account.
* Integrations never bypass booking rules, payment verification or permissions: only verified payments reach accounting,
  n8n cannot book, confirm, cancel or verify anything.

## Testing

`backend/tests/test_platform_integrations.py`, `backend/tests/test_integration_hub.py`, `frontend/e2e/integration-hub.spec.ts`.
All providers are simulated (httpx MockTransport or fake clients). **These integrations have not been tried against
real Google, Zoho, HubSpot, n8n, Meta, AWS, Brevo or 2Factor accounts in this project.** Before relying on one, connect
a test account and run its Test button.
