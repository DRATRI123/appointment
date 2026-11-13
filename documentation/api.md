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
| `/customers` (+ dependents, notes, documents, export), `/customer/organizations/{id}/…` | 5 | implemented |
| `/booking-forms` (+ templates, publish, assign, responses), `/public/…/booking-form` | 5 | implemented |
| `/upi-accounts`, `/payments`, `/admin/payments`, `/coupons`, `/customer/payments` | 6 | implemented |
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

## Phase 5 endpoints

### Customers (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/customers?search&tag&segment&is_guest&page&page_size` | `customers:read` | Segments: `new_30d`, `upcoming`, `returning`, `inactive_90d` |
| GET | `/customers/export.csv` | `customers:export` | Audit-logged |
| POST / GET / PATCH / DELETE | `/customers[/{id}]` | `customers:write` / `customers:read` | Sequential `customer_code` per organization; mobile unique per organization; delete blocked while appointments are upcoming |
| GET / POST / PATCH / DELETE | `/customers/{id}/dependents[/{dep_id}]` | read / write | Family members usable as `dependent_id` on bookings |
| GET / POST / DELETE | `/customers/{id}/notes[/{note_id}]` | `customers:clinical_read` / `customers:clinical_write` | Bodies encrypted with AES-GCM (`DATA_ENCRYPTION_KEY`); every list is audit-logged with `purpose` |
| GET / POST / DELETE | `/customers/{id}/documents[/{doc_id}]` | clinical read / write | Private storage, PNG/JPEG/WebP/PDF sniffed, retention from `privacy.document_retention_days` |
| GET | `/customers/{id}/documents/{doc_id}/download?purpose` | `customers:clinical_read` | Streams with `Cache-Control: private, no-store`; audit-logged |

Customer self-service (signed-in users, per organization, gated by `privacy.allow_customer_self_update`):
`GET /customer/organizations`, `GET/PATCH /customer/organizations/{org_id}/profile`,
`GET/POST/PATCH/DELETE /customer/organizations/{org_id}/dependents[/{id}]`.

### Booking forms (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/booking-forms?include_templates&all_versions` | `booking_forms:read` | Latest version per slug by default |
| GET | `/booking-forms/templates` | read | Built-in starting points (patient intake, skin consultation, consent) |
| POST | `/booking-forms` | `booking_forms:write` | `clone_from` accepts a template slug or a form id; field keys unique; option types need options; conditions must reference known fields |
| GET / PATCH / DELETE | `/booking-forms/{id}` | read / write | Editing fields of a published form creates a new draft version; delete blocked while assigned to services |
| POST | `/booking-forms/{id}/publish` | write | Unpublishes earlier versions and re-points their services |
| POST | `/booking-forms/assign` | write | `{service_id, form_id|null}` |
| GET | `/booking-forms/responses/by-appointment/{appointment_id}` | `appointments:read` | |
| GET | `/public/organizations/{slug}/booking-form?service_id&branch_id` | public | Resolution: service form → branch form → organization default; `null` when none |
| POST | `/public/organizations/{slug}/booking-form-files` | public, rate limited | Private upload for file fields; returns `{key, name, mime_type, size_bytes}` |

Field types: text, textarea, number, email, mobile, dropdown, radio, checkbox, date, file, multi_select.
Validation (`validation`): min/max length, min/max, regex, max_files, accept, min/max date (`today`).
Conditions (`conditions`): equals, not_equals, in, not_in, is_true, is_false, is_empty, is_not_empty, gt, lt.
Booking requests include `form_answers`; the server validates against the resolved form (hidden fields are
skipped), returns 422 `form_invalid` with per-field `errors`, and stores a `booking_form_responses` row
tied to the appointment and form version.

## Phase 6 endpoints: own UPI QR payments

No payment gateway is involved. Customers pay the organization's own UPI ID; staff confirm each payment
against the bank before the booking is confirmed.

### UPI accounts (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET / POST | `/upi-accounts` | `upi_accounts:read` / `upi_accounts:write` | UPI ID validated and lower-cased, unique per organization; optional branch scope; first account in a scope becomes its default; one default per scope |
| GET / PATCH / DELETE | `/upi-accounts/{id}` | read / write | Static-QR accounts need an uploaded image (`/uploads/images`) |
| GET | `/upi-accounts/{id}/preview?amount_paise=100` | read | Test QR and `upi://` URI |
| POST | `/upi-accounts/assign` | write | `{service_id, upi_account_id|null}` |

Account selection for a booking: service account → branch default → any active branch account →
organization default → any active organization account.

UPI request format (all values percent-encoded, `@` kept literal):
`upi://pay?pa=<upi_id>&pn=<merchant>&tr=<payment ref>&tn=<appointment ref>&am=<rupees.paise>&cu=INR`.
QR codes are PNGs rendered by `qrcode` (error correction M). A QR is a request, never proof of payment.

### Payments (tenant routes)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/payments?status&method&search&appointment_id&customer_id&from_at&to_at` | `payments:read` | Search matches reference, UTR, customer name or mobile |
| POST | `/payments` | `payments:record` (cash) | `{appointment_id, kind: advance|balance|full, method: upi_qr|cash|bank_transfer, utr?}`; amount always computed (advance = advance due − paid, balance/full = total − paid); cash is recorded as verified by the recorder and cancels unpaid UPI requests; bank transfer creates a submission needing verification |
| GET | `/payments/{id}` | read | Submissions and the immutable verification log |
| GET | `/payments/{id}/checkout` | read | QR for the reception desk |
| GET | `/payments/{id}/submissions/{sid}/screenshot` | read | Private file, `no-store`, audit-logged |

### Verification queue

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/admin/payments/stats` | `payments:read` | Counts and amounts |
| GET | `/admin/payments/queue?status=submitted,under_review` | `payments:verify` | Oldest submission first |
| POST | `/admin/payments/{id}/review` | verify | Marks under review |
| POST | `/admin/payments/{id}/verify` | verify | `{bank_credit_confirmed: true, verified_amount_paise, amount_mismatch_reason?, notes?}`; a different amount needs a reason; confirms the appointment when the advance is covered |
| POST | `/admin/payments/{id}/reject` | verify | `{reason}`; reopens the payment with a fresh window and returns the appointment to pending payment |
| POST | `/admin/payments/{id}/notes` | verify | Adds a note to the log |

### Public checkout

| Method | Path | Notes |
|---|---|---|
| GET | `/public/organizations/{slug}/appointments/{reference}/payment?access_token` | QR data URL, UPI ID, merchant, instructions, app deep links (generic `upi://`, Google Pay, PhonePe, Paytm, BHIM), status and message; `null` when nothing is due |
| POST | `…/payment/submit?access_token` | multipart `utr` (required), `transaction_reference`, `paid_at`, `payer_upi_id`, `notes`, `screenshot` (PNG/JPEG/WebP/PDF); rate limited; moves the appointment to pending verification and never confirms it |

### Coupons

`GET/POST /coupons`, `PATCH/DELETE /coupons/{id}` (`services:read` / `services:write`). Percent (with optional
cap) or flat, minimum amount, validity window, total and per-customer limits, optional service list.
Redemptions are counted from non-cancelled, non-expired appointments, so cancelling returns the use.
`GET /public/organizations/{slug}/quote?coupon_code=` previews; bookings send `coupon_code` and the server
re-validates. Invalid codes return 422 `coupon_invalid`.

### Payment lifecycle

`initiated → awaiting_payment → submitted → under_review → verified`; `rejected` (customer may resubmit),
`expired` (appointment expired), `cancelled` (appointment cancelled or replaced by cash). Requests already
submitted stay open on cancellation so staff can still verify and then refund them. Every change writes
`payment_verification_logs` and `audit_logs`. A UTR can back only one payment per organization; a repeat
attempt returns 409 `duplicate_utr` and is flagged on both payments.

## Phase 7: refunds and bank reconciliation

### Refunds

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/refunds?status&search&from_at&to_at` | `refunds:request` or `refunds:approve` | Search matches refund/payment reference, refund UTR, customer name or mobile |
| GET | `/refunds/stats` | same | Requested, approved, processed this month and amounts |
| GET | `/refunds/for-payment/{payment_id}` | same | Verified, refunded, in-progress and refundable amounts plus a policy-based suggestion |
| POST | `/refunds` | `refunds:request` | `{payment_id, amount_paise?, reason, destination?, refund_method?}`; only verified payments; amount defaults to the refundable balance; destination defaults to the payer UPI ID (submission, then matched bank line) |
| POST | `/refunds/{id}/approve` | `refunds:approve` | Maker-checker when `refund_requires_second_approver` is on (403 `second_approver_required`) |
| POST | `/refunds/{id}/reject` | `refunds:approve` | `{reason}` |
| POST | `/refunds/{id}/cancel` | requester or approver | Withdraw a requested/approved refund |
| POST | `/refunds/{id}/process` | `refunds:approve` | `{refund_method: upi|bank_transfer|cash, refund_reference (required for upi/bank), destination?, processed_at?, money_sent_confirmed: true, notes (required for cash)}`; records a transfer staff already made; duplicate references 409 |
| POST/GET | `/refunds/{id}/proof` | approve / view | Private PNG/JPEG/WebP/PDF; viewing is audit-logged |
| GET | `/customer/refunds` | signed-in customer | Status, amount and, once processed, the transfer reference. No internal notes or staff names |

Cancelling a paid appointment inside the free-cancellation window opens a refund **request** for the
eligible amount (`cancellation.auto_request_refund`, default on). The payment moves to
`refund_requested` while a refund is open, `refund_processed` when fully refunded, otherwise back to
`verified`. Processing reduces the appointment's `paid_amount_paise`.

### Bank reconciliation (`reconciliation:manage`)

| Method | Path | Notes |
|---|---|---|
| GET | `/reconciliation/presets` | Column mappings for HDFC, ICICI, SBI, Axis, Kotak and a generic layout |
| POST | `/reconciliation/preview` | multipart `file`, `delimiter`; first rows and the detected preset |
| GET/POST | `/reconciliation/imports` | POST multipart `file` (CSV), `parser_code` (preset or `custom`), `mapping` (JSON, overrides the preset), `upi_account_id?`. Only credits are stored; rows already imported (same fingerprint) are skipped and counted; unreadable rows are reported by line |
| DELETE | `/reconciliation/imports/{id}` | Refused while any line is matched |
| GET | `/reconciliation/transactions?status&import_id&search&from_date&to_date` | `status` is a comma list of `unmatched,suggested,matched,ignored`; search covers UTR, narration and amount |
| GET | `/reconciliation/transactions/{id}/candidates` | Scored payments with reasons: UTR equals the customer's submission (70), payment reference in the narration (60, tolerant of truncation), appointment reference (50), same amount within 3 days (30–40), payer UPI ID matches (+10) |
| POST | `/reconciliation/transactions/{id}/match` | `{payment_id, notes?}`; one bank credit per payment; amount differences need a note; writes `bank_matched` to the payment log; does **not** verify |
| POST | `/reconciliation/transactions/{id}/unmatch` · `/ignore` · `/restore` | Dismiss a suggestion or undo a match; ignore needs a reason |
| POST | `/reconciliation/suggest` | Re-run suggestions (e.g. after new UTR submissions) |
| GET | `/reconciliation/stats` · `/report` · `/report.csv` | Unmatched credits, and verified UPI/bank payments with no matched credit |

`GET /payments/{id}` now includes `bank_evidence` (statement lines carrying the submitted UTR or matched to
the payment) and `refund` (the refund summary) so the verifier sees the bank line next to the customer's claim.

## Phase 8: notifications

### Organization (`notifications:read` / `notifications:write`)

| Method | Path | Notes |
|---|---|---|
| GET | `/notifications?status&channel&event&search` | Outbox. Status: `pending`, `scheduled`, `sending`, `sent`, `failed`, `cancelled`, `read` |
| GET | `/notifications/stats` · `/notifications/{id}` | Detail includes every delivery attempt (provider, message id, error) |
| POST | `/notifications/{id}/retry` · `/cancel` | Write. Retry failed/cancelled; cancel pending/scheduled |
| GET/PUT | `/notifications/settings` | `{email_enabled, sms_enabled, whatsapp_enabled, in_app_enabled, notify_staff_on_booking, reminder_hours (≤3, 0.25–336), reply_to_email, events: {code: {enabled, channels}}}`; staff events allow only email and in-app |
| GET | `/notifications/events` | Catalogue: audience, variables, default and effective channels |
| GET | `/notifications/templates` | Effective template per event and channel, with the default text |
| PUT/DELETE | `/notifications/templates/{event}/{channel}` | `{subject (email), body, provider_template_id, is_active}`; unknown variables 422; DELETE resets to default |
| POST | `/notifications/templates/{event}/{channel}/preview` | Rendered with sample data; email HTML; SMS segment count |
| GET | `/notifications/providers` | Adapter per channel, configured or not, on for this organization |
| POST | `/notifications/test` | `{channel, to}` sends a test through the real provider |

Events: `appointment.pending_payment`, `appointment.confirmed`, `appointment.reminder`,
`appointment.rescheduled`, `appointment.cancelled`, `appointment.expired`, `payment.submitted`,
`payment.rejected`, `payment.verified`, `refund.processed`, and for staff `staff.new_booking`,
`staff.payment_to_verify`, `staff.appointment_cancelled`, `staff.refund_requested`.

### Personal

| Method | Path | Notes |
|---|---|---|
| GET | `/me/notifications?unread_only&limit` | In-app inbox across organizations, with unread count |
| POST | `/me/notifications/read` | `{ids?}`; no ids marks everything read |
| GET | `/customer/notification-preferences` | Per clinic: `email`, `sms`, `whatsapp`, `reminders`, `whatsapp_available` |
| PATCH | `/customer/notification-preferences/{organization_id}` | Records opt-in/opt-out time for WhatsApp |

Public booking accepts `customer.whatsapp_opt_in`; `GET /public/organizations/{slug}` exposes only
`settings.messaging.whatsapp_enabled` from the notification settings.

## Phase 9: calendars and video meetings

### Integrations (tenant)

Admins need `integrations:read` / `integrations:write`; a professional linked to the signed-in user can use the
professional-scoped endpoints for their own profile.

| Method | Path | Notes |
|---|---|---|
| GET | `/integrations` | Google configured?, redirect URI, Zoom, and per professional: Google connection, meeting preference, effective provider, feed URL |
| POST | `/integrations/google/connect` | `{professional_id, return_to}` → `{authorization_url}`; 422 `google_not_configured` |
| GET | `/integrations/google/callback?code&state` | Redirects to `return_to?google=connected|denied|failed|invalid_state` |
| POST | `/integrations/zoom` | `{account_id, client_id, client_secret, default_user?}`; verified with Zoom, 422 `zoom_rejected` |
| PATCH | `/integrations/{id}` | Google: `calendar_id`, `create_meet`, `block_busy`, `show_patient_names`; Zoom: `default_user`; both: `is_enabled` |
| POST | `/integrations/{id}/test` · `/sync` | Check the connection · re-read busy time now |
| GET | `/integrations/{id}/logs` | Recent API calls (no request secrets) |
| DELETE | `/integrations/{id}` | Disconnect (Google token revoked) |
| GET/PUT | `/integrations/professionals/{id}/meeting` | `{provider: auto|google_meet|zoom|manual|none, manual_url (https), zoom_user}` |
| POST/DELETE | `/integrations/professionals/{id}/feed` | Create/replace or turn off the private feed URL |
| GET | `/integrations/sync-issues` · POST `/integrations/sync-issues/{id}/retry` | Failed or retried calendar/meeting syncs |

### Appointments and calendars

| Method | Path | Notes |
|---|---|---|
| PUT | `/appointments/{id}/meeting` | `{meeting_link: https://… | null}` (`appointments:write`); notifies the customer of a new link |
| GET | `/appointments/{id}/calendar.ics` | Staff calendar file |
| GET | `/customer/appointments/{id}/calendar.ics` | Signed-in customer |
| GET | `/public/organizations/{slug}/appointments/{reference}/calendar.ics?access_token` | Guest |
| GET | `/calendar-feeds/{token}.ics` | Private subscription feed (30 days back, 180 ahead) |

`AppointmentRead.meeting_link` carries the video link; new notification event `appointment.meeting_link`.

