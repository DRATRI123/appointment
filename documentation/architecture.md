# System Architecture

This document is the master architecture reference for the Appointment Platform: a multi-tenant,
modular-monolith appointment booking and management system with first-party UPI QR payment
collection (no third-party payment gateway).

## 1. Architecture overview

```
                         ┌──────────────────────────────────────────────────┐
                         │                  Next.js 15 (App Router)         │
                         │  (public) │ (auth) │ customer │ professional │    │
                         │  admin │ super-admin   — TanStack Query, RHF+Zod │
                         └───────────────────────┬──────────────────────────┘
                                                 │ HTTPS / REST (JSON), HttpOnly cookies
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   FastAPI backend (modular monolith)                         │
│                                                                                              │
│  api/v1 routers ─▶ services (business rules) ─▶ repositories (SQLAlchemy 2.0) ─▶ database    │
│                                                                                              │
│  core/        config, database, logging, exceptions, pagination, dependencies                 │
│  security/    password hashing, JWT, OTP, RBAC, tenant guard, rate limiting, headers          │
│  payments/    UPI URI builder, QR generator, verification rules, reconciliation parsers       │
│  notifications/  channel adapters (email, sms, whatsapp, in-app, push), templates             │
│  integrations/   google calendar / meet, zoom, webhooks, api-keys                             │
│  workers/     background jobs (hold expiry, reminders, webhook delivery, reconciliation)      │
└───────────────────────────────┬──────────────────────────────────────────────────────────────┘
                                │ SQLAlchemy 2.0 + Alembic
                                ▼
                ┌───────────────────────────────┐        ┌──────────────┐  ┌───────────────────┐
                │  SQLite (dev)  →  PostgreSQL  │        │ Redis (opt.) │  │ Object storage    │
                │  (prod)                       │        │ cache/locks/ │  │ local disk → S3   │
                └───────────────────────────────┘        │ queues       │  └───────────────────┘
                                                         └──────────────┘
```

Why a modular monolith:

* One deployable backend, one database, one migration history.
* Every module has its own `models`, `schemas`, `repositories`, `services`, and `api` router, so a
  module can be extracted into a separate service later without rewriting its internals.
* Avoids distributed transactions for the two places where correctness matters most: slot
  reservation and payment verification.

## 2. Backend layering rules

| Layer | Responsibility | Must not |
|---|---|---|
| `api/` | Parse request, call dependencies (auth, tenant, permission), call one service, serialize response | Contain business rules or run queries |
| `services/` | Business rules, transactions, cross-module orchestration, domain events | Know about HTTP |
| `repositories/` | Query construction, persistence, locking | Contain business decisions |
| `models/` | SQLAlchemy tables, constraints, indexes | Contain logic beyond simple properties |
| `schemas/` | Pydantic v2 request/response contracts | Leak ORM objects to the client |

Every write that spans more than one row runs inside one database transaction opened by the
service layer (`UnitOfWork` pattern through the request-scoped session).

## 3. Multi-tenancy model

```
Platform (super admin)
└── Organization (tenant boundary: organizations.id)
    ├── organization_settings / organization_domains / subscriptions
    ├── Branch *
    │   ├── branch_settings
    │   ├── professional_branches (fees + schedule per branch)
    │   └── upi_accounts (branch-specific QR)
    ├── Professionals *  ── schedules, exceptions, leaves
    ├── Service categories * ── services * ── pricing, packages
    ├── Customers * ── dependents, notes, documents
    ├── Appointments * ── status history, holds, reschedules, cancellations, form responses
    ├── Payments * ── submissions, verification logs, refunds, bank imports, bank transactions
    ├── Notifications, templates, logs
    ├── Integrations, api keys, webhook endpoints/events, integration logs
    └── Staff memberships (user × organization × role, optional branch scope)
```

Tenant isolation is enforced in the backend in three layers:

1. **Every tenant-owned table carries `organization_id`** (indexed, non-nullable).
2. **`TenantContext` dependency** resolves the acting organization from the authenticated
   membership (or `X-Organization-Id` header for multi-org users) and rejects access when the user
   has no active membership. Platform super admins must explicitly impersonate an organization and
   the action is audit-logged.
3. **Repositories accept `organization_id` as a mandatory filter** for tenant-scoped entities. There
   is no "get by id" without a tenant filter outside the platform admin module.

Frontend route guards are only a UX convenience. Authorization is never trusted from the client.

## 4. Module breakdown (API)

All endpoints are versioned under `/api/v1`.

| Module | Prefix | Highlights |
|---|---|---|
| Auth | `/auth` | OTP request/verify, email+password login, Google login, refresh rotation, logout, sessions, password reset, email verification |
| Organizations | `/organizations` | CRUD, settings, branding, domains, business hours, booking/cancellation/payment/notification settings |
| Branches | `/branches` | CRUD, settings, hours, holidays |
| Professionals | `/professionals` | CRUD, branch assignment with per-branch fees, services, leaves, calendar |
| Services | `/services`, `/service-categories` | Categories, services, pricing per branch, packages, add-ons, follow-ups, booking rules |
| Customers | `/customers` | Customer CRUD, dependents, notes, documents, search, export |
| Schedules | `/schedules` | Weekly schedules, exceptions, holidays |
| Availability | `/availability` | Slot computation per professional/branch/service/date (timezone-aware) |
| Appointments | `/appointments` | Holds, booking, reschedule, cancel, status transitions, waitlist, recurring, group |
| Booking forms | `/booking-forms` | Form builder, versions, responses |
| UPI accounts | `/upi-accounts` | Organization/branch UPI accounts, static QR upload, default selection |
| Payments | `/payments` | Payment intents, dynamic QR, customer submission (UTR, screenshot), status |
| Payment verification | `/admin/payments` | Review queue, approve/reject, duplicate UTR detection, audit history |
| Refunds | `/refunds` | Refund request, approval, rejection, proof, history |
| Bank reconciliation | `/bank-statements` | CSV import with configurable parsers, matching, unmatched report |
| Notifications | `/notifications` | In-app list, templates, logs, reminder rules |
| Integrations | `/integrations` | Google Calendar/Meet, Zoom, SMTP, WhatsApp, SMS providers, connection status |
| Webhooks | `/webhooks` | Outgoing endpoints, event subscriptions, incoming webhooks, delivery logs |
| Reports | `/reports` | Appointment, financial, customer reports with CSV/XLSX export |
| Admin | `/admin` | Staff, roles, permissions, audit logs, dashboard analytics |
| Platform | `/platform` | Super admin: organizations, subscriptions, system settings, job monitoring |

Common conventions: cursor/offset pagination (`page`, `page_size`), `sort`, filter query params,
consistent envelope `{ "data": ..., "meta": ... }` for lists and `{ "detail": ... }` for errors,
request ids in every response (`X-Request-ID`).

## 5. Security architecture (summary)

See `security.md` for details.

* Argon2id password hashing; access tokens (JWT, 15 min) + rotating refresh tokens (opaque, hashed
  at rest, 30 days, per-session revocation).
* Tokens delivered as `HttpOnly; Secure; SameSite=Lax` cookies for browsers and as bearer headers
  for API clients. CSRF double-submit token for cookie-authenticated unsafe methods.
* OTP: 6 digits, hashed at rest, 5-minute expiry, 60-second resend cooldown, max 5 attempts,
  per-mobile and per-IP rate limits, provider adapters (`console`, `msg91`, `twilio`, ...).
* RBAC: roles → permissions (string codes like `appointments:write`), membership-scoped per
  organization with optional branch scope. `require_permission("payments:verify")` dependencies.
* Tenant guard on every tenant-scoped route; repository filters by `organization_id`.
* Security headers middleware (CSP, HSTS, X-Frame-Options, Referrer-Policy, nosniff), strict
  CORS allowlist, request size limits, upload type/size validation, structured audit log.
* Payments: unique payment reference per intent, UTR uniqueness per organization, approval only
  by `payments:verify` permission with an immutable verification log, server-side amount
  calculation in integer paise, QR is a request not a proof.

## 6. Appointment booking workflow

```
Customer                 Frontend                 Backend (appointments)                 Backend (payments)
   │  choose org/branch/service/professional/date  │                                        │
   ├──────────────────────────────────────────────▶│ GET /availability  (slots)             │
   │◀──────────────────────────────────────────────┤ computed from schedule − exceptions    │
   │  pick slot                                     │ − leaves − holidays − booked − holds   │
   ├──────────────────────────────────────────────▶│ POST /appointments/holds               │
   │                                                │  ▸ SELECT … FOR UPDATE / tx           │
   │                                                │  ▸ unique(professional, branch, start)│
   │                                                │  ▸ hold expires in N minutes          │
   │◀──────────────────────────────────────────────┤ 201 hold_id, expires_at                │
   │  enter details + booking form                  │                                        │
   ├──────────────────────────────────────────────▶│ POST /appointments (hold_id, form)     │
   │                                                │  ▸ validates hold, creates appointment │
   │                                                │    status = PENDING_PAYMENT (or        │
   │                                                │    CONFIRMED when free / pay-at-clinic)│
   │                                                │  ▸ creates Payment (INITIATED) ───────▶│ amount computed server-side (paise)
   │◀──────────────────────────────────────────────┤ 201 appointment + payment reference    │
   │  pay via own UPI QR, submit UTR/screenshot      │                                        │
   ├──────────────────────────────────────────────▶│ POST /payments/{id}/submit ───────────▶│ SUBMITTED, appointment PENDING_VERIFICATION
   │                                                │                                        │
   │   staff approves in verification dashboard ───▶│ POST /admin/payments/{id}/verify ─────▶│ VERIFIED (audit log)
   │                                                │  appointment → CONFIRMED, notifications│
```

Double-booking prevention stack:

1. Slot capacity check + `SELECT ... FOR UPDATE` on the professional's day row (PostgreSQL) /
   `BEGIN IMMEDIATE` serialized transaction (SQLite).
2. Partial unique index on `appointments (professional_id, branch_id, start_at)` for active
   statuses, and unique index on `booking_holds (professional_id, branch_id, start_at)` for
   unexpired holds.
3. Hold expiry worker releases abandoned holds; expired `PENDING_PAYMENT` appointments transition
   to `EXPIRED` which frees the slot.
4. All times stored in UTC; organization/branch timezone used only for presentation and slot
   generation.

## 7. Own UPI QR payment workflow

```
1. Backend computes payable amount in paise (service price, discounts, coupons, advance rules).
2. Backend selects the UPI account by rule: service-specific → branch default → organization default.
3. Backend creates Payment{reference=PAY-<org>-<ulid>, status=INITIATED → AWAITING_PAYMENT}.
4. Backend builds   upi://pay?pa=<upi_id>&pn=<merchant>&am=<amount>&cu=INR&tn=<reference>
   (URL-encoded) and renders a PNG QR (python `qrcode`). Static uploaded QR is served when the
   account has no dynamic QR enabled.
5. Checkout shows QR, UPI ID copy button, download button, and deep links (GPay/PhonePe/Paytm/BHIM
   intent URLs) plus a countdown to payment expiry.
6. Customer pays in their UPI app, then submits UTR / reference, payment date, screenshot, notes.
   → PaymentSubmission row, Payment.status = SUBMITTED, appointment = PENDING_VERIFICATION.
   The UTR is checked for duplicates within the organization at submission time (soft warning)
   and again at verification time (hard block unless overridden with a reason).
7. Staff with `payments:verify` reviews bank credit and approves/rejects.
   → PaymentVerificationLog (immutable), Payment.status = VERIFIED | REJECTED, appointment
   CONFIRMED | back to PENDING_PAYMENT with reason. Notifications fire.
8. Bank statement reconciliation (CSV import, configurable parsers) suggests matches by UTR,
   amount and date; staff confirm matches; unmatched report is produced.
9. Refunds are manual: request → approve/reject → processed with UPI/bank reference + proof.
   Status is REFUND_PROCESSED only after staff mark it with proof; the system never claims a
   refund succeeded on its own.
```

Rules that are never bypassed: a screenshot or UTR never confirms a payment; QR is a request not a
receipt; amounts are never trusted from the client; every status change is logged with actor.

### SQLite write serialisation

In development every session begins with `BEGIN IMMEDIATE`, so one writer at a time holds the database
and slot reservation cannot race. Reads inside a request also run under that lock, which is fine for a
single clinic on one machine but is the main reason PostgreSQL is required before multi-instance or
high-traffic deployment (Phase 14).

## 8. Background jobs

Phase 1 ships an in-process scheduler abstraction (`app/workers`) with a synchronous runner; later
phases plug in ARQ/Celery via the same `JobQueue` interface. Jobs: expire booking holds, expire
unpaid appointments, send scheduled reminders, deliver webhooks with retry, parse bank statement
imports, sync calendar events.

## 9. Development roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| 1 | Architecture, project setup, database schema, migrations, environment, CI skeleton | `alembic upgrade head` on SQLite; `/health` live; tests pass; frontend builds |
| 2 | Auth (OTP, email/password, Google), users, organizations, RBAC, sessions | Auth + RBAC + tenant isolation tests pass |
| 3 | Branches, professionals, services, categories, pricing | CRUD + admin pages |
| 4 | Scheduling engine, availability, holds, appointment lifecycle | Concurrency tests prove no double booking |
| 5 | Customers, dependents, documents, booking form builder | Form versioning + responses |
| 6 | UPI accounts, dynamic QR, payment submission, verification dashboard | Duplicate UTR + approval audit tests |
| 7 | Refunds, bank statement reconciliation | CSV parsers + matching |
| 8 | Notifications: email, SMS, WhatsApp, in-app, reminders | Adapter tests + worker |
| 9 | Google Calendar / Meet, Zoom | OAuth + idempotent event sync |
| 10 | Admin dashboards, analytics, reports, exports | Charts + CSV/XLSX |
| 11 | Developer API keys, webhooks, external integrations | Signed deliveries + retries |
| 12 | Security hardening, full test suites, Playwright e2e | Security checklist passes |
| 13 | Production deployment, backups, monitoring | Docker + runbooks |
| 14 | PostgreSQL migration, performance tuning | Load test targets met |

## 10. Project folder structure

See the repository root `README.md`; the layout follows the agreed structure:
`frontend/` (Next.js), `backend/` (FastAPI), `infrastructure/`, `documentation/`, `scripts/`.
