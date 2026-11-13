# API Reference (overview)

Base URL: `/api/v1`. Interactive docs: `/docs` (Swagger UI) and `/redoc`; OpenAPI JSON at
`/api/v1/openapi.json`.

## Conventions

* JSON everywhere; `Content-Type: application/json` (multipart for uploads).
* Lists: `GET …?page=1&page_size=20&sort=-created_at&<filters>` → `{ "data": [...], "meta": { "page", "page_size", "total" } }`.
* Single resources return the object directly.
* Errors: `{ "detail": "message", "code": "machine_code", "errors": [ ...field errors ] }` with
  proper HTTP status codes (400 validation, 401 unauthenticated, 403 forbidden, 404 not found,
  409 conflict such as slot taken or duplicate UTR, 422 schema validation, 429 rate limited).
* Every response carries `X-Request-ID`.
* Authentication: `Authorization: Bearer <access_token>` or HttpOnly cookies set by `/auth/*`.
* Tenant selection for multi-organization users: `X-Organization-Id: <organization public id>`.

## Module map

| Prefix | Phase | Status |
|---|---|---|
| `/health`, `/health/ready` | 1 | implemented |
| `/meta` | 1 | implemented (version, environment) |
| `/auth` | 2 | implemented |
| `/users/me` | 2 | implemented |
| `/organizations` (+ settings, domains, members, roles, permissions, audit-logs) | 2 | implemented |
| `/platform` (super admin: stats, organizations, users, audit-logs) | 2 | implemented |
| `/branches` | 3 | implemented |
| `/professionals` | 3 | implemented |
| `/service-categories`, `/services`, `/service-packages` | 3 | implemented |
| `/uploads/images`, `/media/*` | 3 | implemented |
| `/public/organizations/{slug}/…` | 3 | implemented |
| `/schedules` (+ exceptions, holidays, leaves), `/availability` | 4 | implemented |
| `/appointments` (+ holds, calendar, recurring, status, reschedule), `/waitlist` | 4 | implemented |
| `/customer/appointments` | 4 | implemented |
| `/public/organizations/{slug}/availability`, `/quote`, `/holds`, `/appointments` | 4 | implemented |
| `/customers` | 5 | planned |
| `/booking-forms` | 5 | planned |
| `/upi-accounts`, `/payments`, `/admin/payments` | 6 | planned |
| `/refunds`, `/bank-statements` | 7 | planned |
| `/notifications` | 8 | planned |
| `/integrations` | 9, 11 | planned |
| `/webhooks` | 11 | planned |
| `/reports`, `/admin` | 10 | planned |
| `/platform` | 10 | planned |

This file is updated at the end of every phase with the concrete endpoints delivered.

## Phase 2 endpoints

### Authentication `/auth`

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/otp/request` | Send a 6-digit code to a mobile (SMS) or email. 60 s resend cooldown, 5/min per IP. In development/test with the console provider the response includes `debug_code`. |
| POST | `/auth/otp/verify` | Verify the code; creates the account on first sign-in. Sets `access_token`, `refresh_token` (HttpOnly) and `csrf_token` cookies and returns the tokens for API clients. |
| POST | `/auth/register` | Email + password registration (Argon2id, policy: 8+ chars, letters and digits). |
| POST | `/auth/login` | Email + password login. 5 failures lock the account for 15 minutes. |
| POST | `/auth/google` | Sign in with a Google ID token (verified against Google JWKS, `GOOGLE_CLIENT_ID` audience). |
| POST | `/auth/refresh` | Rotate the refresh token (cookie or body). Reuse of a rotated token revokes the whole session family. |
| POST | `/auth/logout` | Revoke the current session and clear cookies. |
| GET | `/auth/sessions` | List signed-in devices. |
| DELETE | `/auth/sessions/{id}` | Revoke one device. |
| POST | `/auth/sessions/revoke-all` | Sign out everywhere. |
| POST | `/auth/password/change` | Change or set a password. |
| POST | `/auth/password/forgot` | Request a reset token (30 minutes, single use; response never reveals whether the email exists). |
| POST | `/auth/password/reset` | Reset with token; revokes all sessions. |
| POST | `/auth/email/verify/request`, `/auth/email/verify/confirm` | Email verification. |

Cookie-authenticated unsafe requests must send `X-CSRF-Token` equal to the `csrf_token` cookie.
Bearer-authenticated requests are exempt.

### Users

| Method | Path | Purpose |
|---|---|---|
| GET | `/users/me` | Current user, memberships (organization, role, branch, permissions) and platform-admin flag. |
| PATCH | `/users/me` | Update profile. |

### Organizations (tenant routes, `organization_id` = public id)

| Method | Path | Permission |
|---|---|---|
| GET | `/organizations` | any user (own memberships) |
| POST | `/organizations` | any user; creator becomes `org_owner`, default settings are seeded |
| GET | `/organizations/by-slug/{slug}` | public (active organizations only) |
| GET / PATCH | `/organizations/{id}` | `organization:read` / `organization:write` |
| GET | `/organizations/{id}/settings` | `organization:read` (all namespaces merged with defaults) |
| GET / PUT | `/organizations/{id}/settings/{namespace}` | namespaces: booking, cancellation, payment, notification, branding, legal, general |
| GET / POST / DELETE | `/organizations/{id}/domains[/{domain_id}]` | `organization:read` / `organization:write` |
| GET / POST | `/organizations/{id}/members` | `staff:read` / `staff:write` (invite by mobile or email; membership is `invited` until first sign-in) |
| PATCH / DELETE | `/organizations/{id}/members/{membership_id}` | `staff:write`; owner role only assignable by owners; last owner protected |
| GET | `/organizations/{id}/roles`, `/permissions` | `staff:read` |
| POST / PATCH / DELETE | `/organizations/{id}/roles[/{role_id}]` | `roles:write`; cannot grant permissions you do not hold; platform permissions never grantable |
| GET | `/organizations/{id}/audit-logs?page=&page_size=&action=&entity_type=` | `audit_logs:read` |

Multi-organization users send `X-Organization-Id` on routes without the path parameter. Platform admins
may access any organization; each such access is written to the audit log as `platform.impersonate`.

### Platform (super admin only)

`GET /platform/stats`, `GET /platform/organizations`, `GET /platform/organizations/{id}`,
`POST /platform/organizations/{id}/status`, `GET /platform/users`, `POST /platform/users/{id}/status`,
`GET /platform/audit-logs`.

## Phase 3 endpoints

All catalogue routes are tenant routes: send `X-Organization-Id` (the frontend does this
automatically for the active organization). Soft-deleted rows never appear.

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET / POST | `/branches` | `branches:read` / `branches:write` | First branch becomes default; `business_hours` is `{mon: [["09:00","13:00"],…]}`; code unique per organization |
| GET / PATCH / DELETE | `/branches/{id}` | read / write | Last branch cannot be deleted; default moves automatically |
| GET / POST | `/service-categories` | `services:read` / `services:write` | Returns `service_count`; optional `parent_id` |
| PATCH / DELETE | `/service-categories/{id}` | `services:write` | Deleting uncategorises services |
| GET / POST | `/services` | `services:read` / `services:write` | Filters: `category_id`, `branch_id` (honours availability overrides), `kind`, `search`; validates payment mode (partial advance needs amount or percent, free means zero price, discount ≤ price) |
| GET / PATCH / DELETE | `/services/{id}` | read / write | `pricing` replaces all per-branch overrides; `professional_ids` replaces organization-wide assignments; follow-up linkage with self-reference guard |
| GET / POST / PATCH / DELETE | `/service-packages[/{id}]` | `services:read` / `services:write` | Items are `{service_id, quantity}`; duplicates rejected |
| GET / POST | `/professionals` | `professionals:read` / `professionals:write` | Filters: `branch_id`, `service_id`, `search`; `branches` carry per-branch fee/duration/buffer/room; `services` carry optional branch and fee override |
| GET / PATCH / DELETE | `/professionals/{id}` | read / write | `user_id` links a staff account (must already be a member); slug unique per organization |
| POST | `/uploads/images` | any catalogue write permission | multipart `file`; PNG/JPEG/WebP sniffed by content, max `MAX_UPLOAD_SIZE_MB`; returns `/media/...` URL |
| GET | `/public/organizations/{slug}` | public | Organization, active branches, active categories and public settings (branding, booking, cancellation, legal, general) |
| GET | `/public/organizations/{slug}/branches` | public | Active branches |
| GET | `/public/organizations/{slug}/services[/{id}]` | public | Active, online-bookable services; filters `branch_id`, `category_id` |
| GET | `/public/organizations/{slug}/professionals[/{id}]` | public | Active, online-bookable professionals with contact details stripped; filters `branch_id`, `service_id` |

## Phase 4 endpoints

### Scheduling (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET / PUT | `/schedules` | `professionals:read` / `professionals:schedule` | PUT replaces the weekly windows for one professional at one branch; windows carry `weekday` (0 = Monday), local `start_time`/`end_time`, optional `slot_minutes`, `capacity`, validity dates; overlaps rejected; professional must be assigned to the branch |
| GET / POST / DELETE | `/schedules/exceptions[/{id}]` | read / `professionals:schedule` | A date override: `is_available=false` blocks the day, `true` with times opens extra hours |
| GET / POST / DELETE | `/schedules/holidays[/{id}]` | read / `branches:write` | Organization-wide or per branch, optional yearly recurrence |
| GET / POST / PATCH / DELETE | `/schedules/leaves[/{id}]` | read / `professionals:schedule` | Approved leave removes availability (all branches or one) |
| GET | `/availability?service_id&branch_id&date[&professional_id]` | `appointments:read` | Slots per professional for one day, in the branch timezone |
| GET | `/availability/summary?service_id&branch_id&from_date&to_date[&professional_id]` | `appointments:read` | Per-day slot counts, max 31 days |

Availability = weekly windows (overridden by date exceptions) − holidays − approved leave − active
appointments − unexpired holds, stepped by the slot grid (`schedule.slot_minutes` → branch assignment
duration → professional default). Appointment length = service duration (professional override) and the
buffer is the larger of service and professional buffers. Min notice and max advance days come from the
service or, failing that, organization booking settings. Capacity > 1 lets several bookings share an
identical start time.

### Appointments (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST / DELETE | `/appointments/holds[/{id}]` | `appointments:write` | Staff holds ignore minimum notice |
| GET | `/appointments?from_at&to_at&professional_id&branch_id&status&customer_id&search` | `appointments:read` or `appointments:read_own` (own profile only) | |
| GET | `/appointments/calendar?from_at&to_at[&professional_id&branch_id]` | same | Compact events for FullCalendar |
| POST | `/appointments` | `appointments:write` | Direct booking without a hold; `confirm_without_payment` confirms immediately; `source` reception / walk_in / professional |
| POST | `/appointments/recurring` | `appointments:write` | `occurrences` (2–26) every `interval_days`; blocked dates are reported in `skipped` |
| GET | `/appointments/{id}` | read / read_own | Includes status history and pricing snapshot |
| POST | `/appointments/{id}/status` | `appointments:write` for confirm/cancel/expire, `appointments:checkin` for check_in/start/complete/no_show | Invalid transitions return 409 `invalid_transition` |
| POST | `/appointments/{id}/reschedule` | `appointments:write` | `start_at` (+ optional `professional_id`) or a `hold_id` |
| GET / POST / DELETE | `/waitlist[/{id}]` | read / write | |

Lifecycle: `pending_payment` (advance due) or `confirmed` (nothing due now / staff override) →
`checked_in` → `in_progress` → `completed`; `cancelled`, `no_show`, `expired` are terminal. Pending
appointments expire after the organization's payment window (`expire_unpaid_appointments` job) and
their slot is released. Every change is written to `appointment_status_history` and the audit log.

### Public booking flow

| Method | Path | Notes |
|---|---|---|
| GET | `/public/organizations/{slug}/availability`, `/availability/summary` | Same engine as staff, public data only |
| GET | `/public/organizations/{slug}/quote?service_id&branch_id[&professional_id]` | Server-side price: professional fee override → branch price → service price, discount, tax, advance by payment mode |
| POST | `/public/organizations/{slug}/holds` | Reserve a slot for `booking.hold_minutes` (default 10); `session_key` owns the hold; 409 `slot_unavailable` if taken |
| DELETE | `/public/organizations/{slug}/holds/{id}?session_key` | Release |
| POST | `/public/organizations/{slug}/appointments` | Requires `hold_id` + matching `session_key`; guest bookings need `booking.allow_guest_booking`, otherwise sign in; response carries a one-time `access_token` |
| GET | `/public/organizations/{slug}/appointments/{reference}?access_token` | Status page (or signed-in owner) |
| POST | `…/appointments/{reference}/cancel`, `…/reschedule` | Honour the cancellation policy (`customer_can_cancel`, `cancel_before_hours`, `max_reschedules`, service overrides) |

### Customer

`GET /customer/appointments`, `GET /customer/appointments/{id}`, `POST …/cancel`, `POST …/reschedule`
(needs a `hold_id` from the public hold endpoint).

### Double-booking guarantees

1. Holds and appointments are inserted inside a SAVEPOINT; the partial unique indexes
   `uq_booking_holds_active_slot` and `uq_appointments_active_slot` on
   `(professional_id, branch_id, start_at, slot_sequence)` reject a second active row.
2. SQLite writers are serialised with `BEGIN IMMEDIATE`; PostgreSQL takes a `SELECT … FOR UPDATE` on the
   professional row before checking availability.
3. `tests/test_concurrency.py` races eight sessions for one slot and asserts exactly one winner, and
   proves the index alone rejects a bypassing insert.
