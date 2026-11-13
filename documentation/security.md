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
* Refunds are status-tracked with proof; never reported complete without staff confirmation.

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
