# Security Architecture

> This document describes the controls implemented and planned. It is not a legal compliance
> statement. Obtain an independent legal and security review before claiming compliance with the
> Indian DPDP Act 2023 or any healthcare regulation.

## Authentication

| Control | Implementation |
|---|---|
| Password hashing | Argon2id (`argon2-cffi`), per-password salt, tunable cost in settings |
| Access token | JWT (HS256 in dev, RS256/ES256 supported via settings), 15-minute lifetime, `sub` = user public id, `sid` = session id, `typ` = access |
| Refresh token | Opaque 256-bit random, only SHA-256 hash stored in `user_sessions`, rotated on every use, reuse detection revokes the whole session family |
| Browser delivery | `HttpOnly; Secure; SameSite=Lax` cookies (`access_token`, `refresh_token`) scoped to `/api`; bearer header for non-browser clients |
| CSRF | Double-submit cookie (`csrf_token` cookie + `X-CSRF-Token` header) required for cookie-authenticated unsafe methods |
| OTP | 6 digits, HMAC-hashed with server pepper at rest, 5-minute expiry, 60 s resend cooldown, 5 attempts max, then 15-minute lockout; per-mobile and per-IP limits |
| OTP providers | Adapter interface `OTPProvider.send(mobile, code)` with `console` (dev), and pluggable SMS vendors |
| Google login | OAuth 2.0 authorization-code flow with PKCE; ID token verified against Google JWKS; account linking by verified email only |
| Password reset | Single-use, hashed, 30-minute token; all sessions revoked on reset |
| Account lockout | Progressive delays after failed logins; account suspension flag honoured on every request |
| Session management | List and revoke devices; `user_sessions` stores user agent, IP, last seen |

### Implemented in Phase 2

`app/security/passwords.py` (Argon2id), `tokens.py` (JWT + hashed opaque refresh tokens),
`otp.py` (HMAC-hashed codes, provider adapters), `google.py` (JWKS verification),
`identifiers.py` (E.164 / email normalisation), `app/api/deps.py` (bearer/cookie extraction, CSRF
double-submit, session revocation check, tenant resolution, permission guards),
`app/services/auth_service.py` (lockout, rotation, reuse detection, reset and verification flows).

## Authorization

* **RBAC**: permissions are string codes (`module:action`). Roles are system-seeded
  (`platform_super_admin`, `org_owner`, `org_admin`, `branch_manager`, `doctor`, `professional`,
  `receptionist`, `accountant`, `staff`, `customer`) and organization-defined custom roles are
  supported through `roles.organization_id`.
* **Membership scoped**: `organization_memberships(user, organization, role, branch?)`. A user can
  hold different roles in different organizations.
* **Dependencies**: `CurrentUser`, `TenantContext`, `require_permission(code)`,
  `require_branch_access`. Routes declare required permissions explicitly.
* **Tenant isolation**: tested by `tests/test_tenant_isolation.py` in Phase 2; repositories require
  `organization_id`.
* **Platform admin impersonation**: explicit `X-Organization-Id` with `is_platform_admin`, always
  written to `audit_logs`.

## Application security

* Pydantic v2 validation on every input; strict types; max lengths.
* SQLAlchemy parameterised queries only; no string SQL from user input.
* Security headers middleware: `Content-Security-Policy`, `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`.
* CORS: explicit allowlist from `CORS_ORIGINS`.
* Rate limiting: `slowapi` with per-route limits (auth, OTP, payment submission), Redis-backed in
  production.
* Request body size limit and upload validation (MIME sniffing, allowed types: png/jpg/webp/pdf,
  max 5 MB, randomised storage names, served through authenticated endpoints only).
* Secrets only from environment (`.env` locally, secret manager in production); `.env` is
  git-ignored; `SECRET_KEY` must be ≥ 32 bytes and the app refuses to start with the default in
  non-development environments.
* Structured JSON logs with request ids; no secrets, tokens, OTPs or UTR screenshots in logs.
* Audit log for every privileged action (payment verification, refunds, role changes, settings,
  impersonation, exports).

## Payment security

* Payment amounts computed server-side in integer paise; the client never sends an amount.
* Unique payment reference (`PAY-<orgcode>-<ULID>`) per intent, embedded in the UPI `tn` field.
* UTR uniqueness per organization (`uq_payment_submissions_org_utr`); duplicate attempts are
  recorded and surfaced to the verifier.
* Only `payments:verify` can move a payment to VERIFIED/REJECTED; every transition is written to
  `payment_verification_logs` with actor, timestamp, previous and next status, reason.
* Screenshots stored outside the web root with randomised names; access requires permission and is
  logged.
* No automatic success: QR scans, screenshots, UTR entry and deep-link returns never change a
  payment to VERIFIED.
* Refunds: `requested → approved → processed` (or `rejected` / `cancelled`). The platform never moves
  money. `processed` requires `refunds:approve`, an explicit "money sent" confirmation and the refund
  UTR/bank reference (or a cash note); a reference can be recorded once per organization. Until then
  customers see "requested" or "approved, not yet sent", never "refunded". Optional maker-checker
  (`cancellation.refund_requires_second_approver`) stops a requester approving their own refund.
  Refund amounts can never exceed the verified amount minus refunds already open or sent.
* Bank reconciliation: statements are stored privately; matching a bank credit to a payment is recorded
  as evidence (`bank_matched` in the payment log) and never verifies the payment. Exported reports
  neutralise spreadsheet formulas (`=`, `+`, `-`, `@` prefixes).

## Notification security

* Provider credentials only come from environment variables; the provider status endpoint shows which
  adapter is active and whether it is configured, never a secret.
* Templates cannot run code: only `{{name}}` placeholders from the event's variable list are accepted
  (unknown names are rejected on save); email HTML escapes every value and only links http(s) URLs.
* WhatsApp messages go only to customers who opted in (time and source recorded); customers can turn
  email, SMS, WhatsApp and reminders off per clinic. Changes are audit-logged.
* Messages carry the minimum needed (service, time, amount). Clinical notes and form answers are never
  included. Customers see message status only through their own appointments.
* Real OTP delivery never returns the code in the API response (only the console provider in
  development does); a delivery failure returns 503 `otp_delivery_failed`.

## Integration security (calendars and video)

* Google OAuth uses the server-side web flow with offline access; the `state` is a signed, 10-minute,
  single-use token bound to the organization, integration and user (a hash of its nonce is stored and
  cleared on use), so callbacks cannot be replayed or forged. Only the `calendar.events` scope plus
  `openid email` is requested.
* Refresh/access tokens and Zoom client secrets are stored with AES-256-GCM (`credentials_encrypted`) and
  never returned by the API. Disconnecting revokes the Google token and deletes stored credentials.
* Admins (`integrations:write`) manage all connections; a professional can manage only the profile linked
  to their own account. Other organizations get 404.
* Imported busy time stores only start and end ("Busy"), never event titles or attendees. Events we create
  carry a private marker so they are never re-imported as busy time.
* Patient names in Google Calendar events can be turned off per calendar. Zoom meeting topics never
  contain patient names.
* Private calendar feeds use an unguessable token (`<professional id>.<32-byte secret>`) compared in constant
  time; replacing the link invalidates the old one. Feeds are `noindex` and cached privately.
* External API calls never run inside a booking request: a provider outage delays a calendar event, never a
  booking, and failures are retried with exponential backoff and shown under Sync problems.

## Reports and exports

* Reports check every permission they need (e.g. the appointments report needs `appointments:read`
  as well as `reports:read`); exports also need `reports:export` and are audit-logged with filters, row
  count, format and whether the report contains personal data.
* CSV cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with `'`; Excel text cells
  are written as strings so they never become formulas.
* Professionals without `reports:read` only ever see their own numbers; the server forces the filter.

## Developer API keys and webhooks

* API keys (`ak_live_<id>_<secret>`) are shown once; only an HMAC-SHA256 (peppered with `SECRET_KEY`) is
  stored. A key acts as its creator, in one organization, with permissions = key scopes ∩ the creator's
  current role ∩ the API scope catalogue. Removing or demoting the creator immediately narrows or stops the key.
* The scope catalogue never includes recording or verifying payments, refunds, roles, staff, settings,
  integrations or key management. Keys only reach an allowlist of path prefixes (appointments,
  availability, catalogue, customers, payments read, booking forms, reports, analytics); everything else,
  including user, platform, organization-admin and developer routes, returns 403 `api_key_not_allowed`.
  Platform admins get no special powers through a key.
* Optional expiry, IP/CIDR allowlist and per-key rate limit (429 with `Retry-After`); daily usage counts
  include failed and rate-limited calls. Creation and revocation are audit-logged.
* `X-Forwarded-For` is honoured only from `FORWARDED_ALLOW_IPS`, so callers cannot spoof their IP to
  bypass allowlists, per-IP rate limits or audit records. The general rate limiter keys on the same address.
* Webhooks: per-endpoint secret (encrypted at rest, shown once, rotatable); every delivery is signed
  `X-Webhook-Signature: t=…,v1=HMAC-SHA256("t.body")` with an event id for idempotency. URLs must be https
  and resolve only to public addresses (checked when saved and again before each delivery, so DNS changes
  cannot reach internal services or cloud metadata). Redirects are not followed; responses are truncated.
* Events are written to an outbox in the business transaction (no event for rolled-back work), retried with
  backoff for about two days, and an endpoint is switched off after 50 consecutive failures. Payloads carry
  public ids only and never clinical notes, form answers, documents or payment screenshots.

## Phase 12 hardening and testing

What changed, and the test that keeps each fix in place (`backend/tests/test_security.py` unless noted):

| Area | Control | Regression test |
|---|---|---|
| Brute force | Failed-login counters, OTP attempt counts, refresh-token reuse revocation and duplicate-UTR flags are committed even though the request ends in an error (`AppError(persist=True)`); every other error still rolls back | `test_security_counters_survive_the_failing_request`, `test_unrelated_errors_still_roll_back` |
| Tenant isolation | Every GET route that takes an ID is swept with another tenant's credentials (generated from the OpenAPI schema, so new routes are covered automatically); the tenant header cannot be pointed at another organization | `test_every_id_route_refuses_another_tenants_resources` |
| Patient lists | Reading your own profile or family at a clinic no longer creates a customer record there (opening a booking page used to add the visitor to that clinic's patient list) | same sweep, `test_dependents_and_dependent_booking_via_customer_self_service` |
| Tokens | `alg=none`, wrong key, expired, wrong token type and forged-subject tokens are rejected | `test_tampered_access_tokens_are_rejected`, `test_token_for_another_user_signed_correctly_still_needs_a_live_session` |
| CSRF | Header must equal the cookie; missing or forged values fail. Logout is deliberately exempt so a broken session can always sign out (SameSite=Lax already blocks cross-site POSTs) | `test_csrf_token_must_match_cookie` |
| Client IP | `X-Forwarded-For` is read right-to-left from a trusted proxy, skipping our own proxies; the client-controlled left-most entries are ignored, invalid entries fall back to the proxy address | `test_client_ip_cannot_be_spoofed_through_forwarded_for` |
| Mass assignment | `is_platform_admin`, verification and lockout fields cannot be set through register or profile updates; customers cannot choose the payable amount or payment status | `test_privileged_fields_cannot_be_set_by_users`, `test_payment_amount_cannot_be_chosen_by_the_customer` |
| Error responses | 422 responses never echo the submitted value (passwords, OTPs, UTRs); unexpected errors return a generic message with a request id and log the traceback server-side; caller-supplied `X-Request-ID` is accepted only if short and plain, so it cannot forge log lines | `test_validation_errors_do_not_echo_submitted_values`, `test_unexpected_errors_return_a_generic_message_with_request_id`, `test_request_id_header_is_sanitised` |
| Headers | API responses carry `nosniff`, `DENY`, `frame-ancestors 'none'` CSP and Referrer-Policy, including on errors; the `/media` mount serves only public files | `test_api_responses_carry_security_headers`, `test_media_mount_does_not_serve_private_files` |
| Web app | Content-Security-Policy, COOP, Permissions-Policy and optional HSTS on every page (`frontend/next.config.ts`); post-login `?next=` accepts same-site paths only | `frontend/tests/unit/safe-redirect.test.ts`; `e2e/quality.spec.ts` fails on any CSP violation |
| Accessibility | Admin, booking and auth pages are scanned with axe (WCAG 2.1 A/AA); serious or critical issues fail the build | `e2e/quality.spec.ts` |

Automated gates in CI (`.github/workflows/ci.yml`): ruff, bandit (no findings; the five `nosec` markers are
documented false positives), pip-audit, npm audit (high and above), backend coverage at least 88 %, Vitest
unit tests, production build, and the full Playwright suite against real servers.

Known limits, not yet addressed:

* Bank transactions are addressed by integer IDs in reconciliation URLs. Lookups are scoped to the
  organization (the sweep confirms it), but the IDs are guessable within a tenant.
* `style-src` keeps `'unsafe-inline'` (component libraries set inline styles; styles cannot run code).
  `script-src` no longer does: see Phase 13.

## Healthcare privacy

* Customer notes and documents are restricted to clinical roles (`customers:clinical_read`).
* Clinical note bodies are encrypted with AES-256-GCM (`app/security/crypto.py`, key from
  `DATA_ENCRYPTION_KEY`, derived from `SECRET_KEY` only in development/test). Documents live in private
  storage and are streamed only to `customers:clinical_read` holders; every note view and document download is
  written to `audit_logs` with the stated purpose. Retention: `privacy.document_retention_days` drives the
  `purge_expired_documents` job.
* Access to customer records is written to `audit_logs` with purpose.
* Retention: `privacy.document_retention_days` drives the `purge_expired_documents` job. Other data has no
  automatic expiry yet; the clinic decides when to erase a customer (below).
* Erasure on request: owners and admins (`customers:erase`) can erase a customer from their profile page
  (`POST /customers/{id}/anonymize`, reason and confirmation required). It removes the name, contact details,
  date of birth, address, family members, clinical notes, uploaded document files, booking-form answers,
  appointment notes, the personal details held in notification records, and the link to the login account. It
  keeps appointments, payments, UTRs, verification logs and refunds, attached to an anonymous record, so the
  accounts still reconcile. It is refused while the customer has upcoming visits or payments/refunds awaiting
  staff action. The audit log records who erased whom and why, not the erased values. Whether this meets a
  particular legal obligation needs your own legal review.
* Consent flags captured at booking (`customers.consent_json`).

## Backup and recovery

`python -m app.ops.backup` (Docker: the `backup` service, daily). One file per backup containing the database
(SQLite online backup or `pg_dump` custom format), the uploads and a manifest of SHA-256 checksums. With
`BACKUP_ENCRYPTION_KEY` the file is encrypted with AES-256-GCM in 1 MiB chunks whose nonces encode their position and
whose last chunk is marked, so truncation, reordering or any altered byte makes the whole file fail rather than
restore partially. Every backup is verified after writing; restore verifies again, refuses a backup for the other
database kind, and keeps the previous data aside. Archive extraction uses Python's `data` filter (no absolute paths,
`..` or links outside the folder). Retention: daily/weekly/monthly. Optional off-site copy to S3-compatible storage.
Outcomes are recorded for the System health page and the `BackupMissing` alert. Details: `deployment.md` section 5.

## Phase 13: production hardening

| Area | Control | Test |
|---|---|---|
| Unsafe configuration | Staging/production refuse to start with default or short secrets, missing `DATA_ENCRYPTION_KEY`/`OTP_PEPPER`, `DEBUG`, wildcard CORS/hosts/proxies, non-HTTPS URLs, console OTP, rate limiting off, private webhook targets; all problems listed at once | `tests/test_production_config.py` |
| Script injection | Per-request CSP nonce (`frontend/proxy.ts`): `script-src 'self' 'nonce-…' 'strict-dynamic'`, no `'unsafe-inline'`; every page renders per request so it can carry the nonce | `frontend/tests/unit/csp.test.ts`; `e2e/quality.spec.ts` fails on any violation |
| Shared rate limits | API-key limits are counted in Redis when configured, so several API containers share one limit; Redis outages fall back to in-memory counting instead of failing requests (route limits likewise) | `tests/test_rate_limit_redis.py` (real Redis in CI) |
| Images | `.dockerignore` keeps `.env`, databases, uploads and virtualenvs out of images (previously `COPY . .` could include them); non-root users; exec-form commands for clean shutdown | CI `docker` job checks the built image |
| Network exposure | Only Caddy publishes ports; database, Redis, API and `/metrics` stay on the internal network; Caddy replaces client-supplied `X-Forwarded-For`; the API trusts forwarded IPs only from the Docker subnet | verified on the running stack: a spoofed `X-Forwarded-For` was ignored in audit logs |
| Monitoring data | `/metrics` needs a bearer token and uses route templates, never raw paths, so IDs and personal data never become labels; Sentry events are stripped of bodies, cookies, auth headers, query strings, user and local variables | `tests/test_monitoring.py` |
| Uploads in S3 | Private bucket, server-side encryption, keys validated against `..`; public files streamed by the API so no public bucket policy is needed | `tests/test_storage_s3.py` |
| Configuration isolation | The backend reads only `backend/.env`; the root `.env` (Docker, production values) never applies to a local run | |

## Public booking page, embedding and Shopify

| Area | Control | Test |
|---|---|---|
| Fake bookings / OTP abuse | Online bookings need a one-time code for the customer's mobile (setting `booking.require_mobile_verification`, on by default). The token is a signed JWT bound to clinic, held slot, session key and number, valid 30 minutes. Per-IP limits (5/min, 20/h send; 10/min confirm), 60 s resend cooldown, 5 codes per number per hour, 5 wrong attempts lock the code; attempts persist even though the request fails | `tests/test_public_booking.py` |
| Hold hijacking | Code requests and bookings must present the session key that created the hold | `test_codes_need_the_customers_own_live_reservation` |
| URL parameters | `service`, `branch`, `doctor`, `date` are parsed against a strict pattern and matched to the real catalogue; unknown values are ignored; they never reach price or permission logic. The server recalculates price and ignores client amount fields | `frontend/tests/unit/booking-params.test.ts`, `test_prices_come_from_the_server_never_from_the_request` |
| Click-jacking | Normal pages: `frame-ancestors 'none'` + `X-Frame-Options: DENY`. `/embed/{clinic}`: `frame-ancestors 'self'` plus the clinic's allowed websites (exact `https://` origins, max 20, validated server-side), fetched by the web server with a short cache; on any error the header is `'none'` (fail closed) | `frontend/tests/unit/csp.test.ts`, `frontend/e2e/public-booking.spec.ts` |
| CORS | Unchanged: only the booking site's own origins. Shopify stores never call the API, so their domains must not be added | |
| Shopify theme code | Contains only the public booking address. Every merchant value is cleaned separately (`handleize`), the link must be `https://`, output is escaped | `tests/test_shopify_liquid.py` (renders with python-liquid, injection cases) |
| iframe messages | The embed page only posts `{type: "appointment-booking:resize", height}`; the generated listeners check `event.origin` and bound the height | `frontend/tests/unit/embed-code.test.ts` |
| Slug squatting | Organization slugs cannot take top-level app routes (`admin`, `embed`, `api`, `login`, …) | `test_reserved_web_addresses_cannot_be_taken` |
| Patient data in URLs | Public URLs carry only clinic/service/doctor slugs. The appointment page needs a reference and a random token, is `noindex`, and sends `Referrer-Policy: strict-origin-when-cross-origin` | |
