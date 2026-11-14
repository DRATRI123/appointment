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

## Healthcare privacy

* Customer notes and documents are restricted to clinical roles (`customers:clinical_read`).
* Clinical note bodies are encrypted with AES-256-GCM (`app/security/crypto.py`, key from
  `DATA_ENCRYPTION_KEY`, derived from `SECRET_KEY` only in development/test). Documents live in private
  storage and are streamed only to `customers:clinical_read` holders; every note view and document download is
  written to `audit_logs` with the stated purpose. Retention: `privacy.document_retention_days` drives the
  `purge_expired_documents` job.
* Access to customer records is written to `audit_logs` with purpose.
* Retention: `organization_settings.retention_days_*` drive scheduled purge jobs (Phase 12).
* Consent flags captured at booking (`customers.consent_json`).

## Backup and recovery

* SQLite: `scripts/backup_sqlite.py` performs an online backup via the SQLite backup API.
* PostgreSQL: `pg_dump` scheduled job in `infrastructure/deployment`, retention policy documented in
  `deployment.md`.
