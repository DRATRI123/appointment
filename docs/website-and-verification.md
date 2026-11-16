# Clinic website, website builder and multi-channel verification

Status: implemented and tested (phases 1–8). Sections 1–3 are the original inspection and plan; 4 onwards is the guide.

## 1. What already exists (inspected 2026-11-15)

| Area | Existing implementation | Reused for |
|---|---|---|
| Stack | Next.js 16 / React 19 / TypeScript / Tailwind 4 (`frontend/`), FastAPI + SQLAlchemy 2 + Alembic (`backend/`), SQLite in development, PostgreSQL 17 in production | Unchanged. No new frameworks. |
| Tenancy | `organizations` + `organization_settings` (namespaced key/values), `X-Organization-Id`, permission checks in `app/api/deps.py` | Website document is per organization; new permissions `website:write`, `website:publish` |
| Public booking | `/{clinic}` booking flow, `/embed/{clinic}`, URL hints, holds, row-locked booking, own-UPI payment, status page with reschedule/cancel | Flow moves to `/{clinic}/book`; `/{clinic}` becomes the clinic website |
| Booking verification | `booking_verification_service.py`: SMS code tied to the held slot, JWT token checked by `POST /appointments` | Replaced by the channel-agnostic OTP service (SMS, email, WhatsApp) with the same enforcement point |
| OTP primitives | `app/security/otp.py`: `secrets`-based codes, HMAC-SHA256 hashes with a pepper; `otp_verifications` table | Kept for sign-in; booking OTP gets its own `otp_challenges` table |
| Delivery | `app/notifications/providers.py`: console, SMTP, Twilio (SMS/WhatsApp), MSG91 SMS, Meta WhatsApp Cloud; credentials from environment | Same adapters; organizations can also store their own credentials (encrypted) |
| Encryption | `app/security/crypto.py` AES-GCM with `DATA_ENCRYPTION_KEY` (already used for clinical notes) | Provider secrets |
| Uploads | `POST /uploads/images` (PNG/JPEG/WebP, magic-byte check, size limit, public storage, S3 adapter) | Logos, hero, gallery, doctor photos |
| Audit | `record_audit` with before/after | Every save, publish, restore and settings change |
| Analytics | Bookings, revenue, utilisation dashboards | Adds website traffic and booking-source breakdowns |

## 2. Decisions

1. **One website document per clinic.** Settings, theme, navigation, sections, buttons, footer, custom pages and SEO
   live in one validated JSON document with a *draft* and a *published* copy. Publishing copies draft → published
   and stores a numbered version; restoring copies a version back into the draft. This makes save/publish/restore
   atomic and keeps the public page to one cached read. Every field is validated by Pydantic models (types,
   lengths, allowed section types, colours, fonts from an allow-list, safe links).
2. **Links are data, not HTML.** Buttons store a type (`book`, `call`, `whatsapp`, `maps`, `page`, `url`, …) and
   validated targets; the frontend builds the `href`. Only `https:`, `tel:`, `mailto:`, WhatsApp and internal paths
   are possible. Rich text is a small Markdown subset rendered without `dangerouslySetInnerHTML`.
3. **Doctors, services, branches, hours stay in the catalogue.** Website sections choose *which* to show and how;
   the content comes live from the existing APIs, so a fee change never needs a website edit. Testimonials are
   entered by staff and shown only when marked approved, with the consent date recorded.
4. **URLs.** `/{clinic}` website · `/{clinic}/book` booking · `/{clinic}/{branch}` branch page (booking preselects
   the branch) · `/{clinic}/{page}` custom pages · `/{clinic}/appointments/{ref}` status · `/embed/{clinic}` iframe.
   Old `/{clinic}?service=…` links redirect to `/{clinic}/book?service=…` so Shopify buttons keep working.
   A solo doctor uses their own organization slug (`/dr-meera-joshi`).
5. **Booking order** follows the requested flow: service → doctor (or first available) → branch → date and time →
   details → verification → review → payment → confirmation. Steps with a single choice are skipped.
6. **OTP** gets a challenge model (`challenge_id`), per-clinic policy (namespace `otp`) and per-clinic provider
   settings. Codes are never returned by the API and never logged outside development; tests read them from the
   in-memory development outbox.
7. **Provider testing.** This environment has no real SMS/WhatsApp/email accounts. Providers are tested against
   local servers that implement the providers' HTTP APIs and SMTP, and each channel has a *Send test* button in the
   admin so it can be checked with real credentials after deployment. Nothing is reported as delivered unless the
   provider accepted it.

## 3. Phases

| Phase | Content |
|---|---|
| 1 | This document |
| 2 | Clinic website at `/{clinic}` (hero, about, doctors, services, categories, facilities/gallery, branches + hours + map links, testimonials, FAQ, contact, footer), sticky mobile *Book* button, booking at `/{clinic}/book` in the new order, branch and custom pages, SEO metadata |
| 3 | Website Management admin: settings, homepage builder (add/edit/delete/enable/reorder sections from templates), header & navigation, per-section editors, gallery, testimonials, FAQ, contact, footer, custom pages, buttons, SEO, device preview, draft/publish/restore with history |
| 4 | OTP service package, `otp_challenges`, OTP policy and provider settings with encrypted secrets and test sends, verification screen with channel choice, booking API enforcement |
| 5 | WhatsApp booking link, campaign/source tracking (`utm_*`, `ref`) stored on the appointment |
| 6 | Website analytics (cookie-free daily counts) and booking-source reports in the admin |
| 7 | Backend tests (SQLite + PostgreSQL), Liquid tests, unit tests, e2e on desktop and phone, accessibility/CSP audit |
| 8 | Configuration and deployment guide, sample environment, changed files and migrations |

## 4. Public website

| Address | What it shows |
|---|---|
| `/{clinic}` | Clinic website (published version; before the first publish, a starter site built from the clinic profile, branches, services and doctors, with no invented content) |
| `/{clinic}/book` | Booking steps: service → doctor (or first available) → location → date and time → details → verification → review → payment → confirmation. Steps with one option are skipped |
| `/{clinic}/{page}` | A custom page; else a policy page (`privacy`, `terms`, `refund-policy` from Organization settings → Legal); else a location page (`/{clinic}/{branch}`) |
| `/{clinic}/appointments/{reference}?t=…` | The patient's own booking: status, UPI payment, reschedule, cancel |
| `/embed/{clinic}` | The booking steps for iframes (see `integrations/shopify-integration.md`) |
| `/{clinic}?service=…` | Old booking links forward to `/{clinic}/book?service=…` |

A doctor practising alone uses their own organization name: `booking.mydomain.com/dr-meera-joshi`.

Website content comes from `GET /api/v1/public/organizations/{slug}/website` (the published document) and the live
catalogue APIs, so prices, durations, doctors and opening hours are never typed twice. Sections without real content
(no approved testimonials, no FAQ, no photos) are not shown to visitors; the admin preview marks them instead.
Titles, descriptions, social-sharing images and favicon are rendered on the server for search engines.

## 5. Website Management (Admin → Website)

Permissions: `website:write` (edit the draft, upload images and PDFs) and `website:publish` (publish, restore). Clinic
owners and admins have both; other roles have neither unless given through a custom role.

| Menu | Purpose |
|---|---|
| Website settings | Names, logo, favicon, brand / secondary / background colours (with a readability warning), font, phone, WhatsApp, email, address, social links |
| Homepage builder | Add sections from 16 templates, edit, duplicate, switch on/off, reorder (drag or arrow buttons), delete with confirmation |
| Header & navigation | Sticky header, logo, phone, up to 10 menu links (section, page, booking page or https address) |
| Hero / About / Doctors / Services / Gallery / Testimonials / FAQ / Contact | Editors for the first section of each type (create it if missing) |
| Footer | About text, copyright, up to 4 link columns, social / locations / policy toggles |
| Custom pages | Title, address, Markdown content, sections, menu visibility, search title and description |
| Custom links & buttons | Book, Call, WhatsApp, Contact, View services, External, Custom URL, Google Maps, Download PDF, Custom page; style, colour, icon, new tab, visibility and positions (header, hero, service cards, contact, footer, sticky phone bar) |
| SEO settings | Title, description, social image, hide from search engines, Google preview |
| Preview & publish | Desktop / tablet / phone preview of the unsaved draft, publish with a note, version history with restore, discard draft |

How saving works: edits stay in the browser until **Save draft** or **Publish**. Each save carries the version the
admin loaded; if a colleague saved in between, the server refuses (`409 website_edit_conflict`) instead of
overwriting. Every save, publish, restore and discard is in the audit log. The last 50 published versions are kept.

Validation (server side, `app/schemas/website.py`): links must be `https://` (no credentials or spaces) or this site's
`/media/…`; PDFs must end in `.pdf`; colours are `#RRGGBB`; fonts come from an allow-list served by the site itself (no
third-party font requests); page addresses cannot be `book`, `appointments`, `embed`… or a location's address;
testimonials can be approved only with the patient's consent recorded. Errors name the item, e.g.
`Facilities › item 2 › title: cannot be empty`. Text fields use a Markdown subset rendered without HTML.

## 6. OTP & verification (Admin → Settings → OTP & verification)

General settings (namespace `otp`, defaults in brackets): on/off [on], required before booking [on], allowed methods
[SMS], default method [SMS], 4 or 6 digits [6], expiry 60–900 s [300], resend cool-down 20–600 s [60], wrong attempts
3–10 [5], resends per request 1–10 [3], per hour: codes per number/email 1–10 [5], requests per IP 5–200 [20], requests
per booking session 2–30 [8]. A platform-wide ceiling of 10 codes per destination per hour also applies, plus per-IP
request limits on the routes.

Delivery: each method uses the clinic's own account if one is set up and enabled, otherwise the platform account from
the environment. A half-configured clinic account never falls back silently. Methods without a working account are
hidden from patients.

| Method | Providers | What to prepare |
|---|---|---|
| SMS | MSG91 (India), Twilio | MSG91: DLT-registered sender ID and a DLT flow whose variables are `var1` = code, `var2` = minutes, plus the auth key. Twilio: Account SID, sender number or Messaging Service SID, auth token |
| WhatsApp | WhatsApp Business Platform (Meta Cloud API), Twilio | Meta: phone number ID, a template approved in the **Authentication** category (body `{{1}}` = code, copy-code button) and its language, a permanent system-user access token. Twilio: approved content template SID (`{{1}}` = code). Personal WhatsApp numbers cannot send automated codes |
| Email | SMTP | Server, port, security (STARTTLS/SSL), user name, password, sender address and name; optional subject and text with `{{code}}`, `{{clinic}}`, `{{minutes}}` |

Secrets (auth keys, tokens, passwords) are encrypted with `DATA_ENCRYPTION_KEY` (AES-256-GCM), never sent back to the
browser (only "saved …1234"), and audit entries list which secrets are set, not their values. Leaving a secret field
empty keeps the stored one. **Send test** sends a sample code through the account and records the provider's answer.

Patient flow: choose a method → Send code → enter the code (auto-submits) → verified. The screen offers resend with a
countdown, change number/email, another method, and explains incorrect (with attempts left), expired, superseded,
locked and delivery-failure states.

API (all under `/api/v1/public/organizations/{slug}`):

| Endpoint | Notes |
|---|---|
| `GET /verification` | `{required, channels, default_channel, code_length, resend_cooldown_seconds}` |
| `POST /verification/start` | `{channel, destination, hold_id, session_key}` → `{challenge_id, channel, destination (masked), code_length, expires_in_seconds, resend_after_seconds, resends_left}`. Never contains the code |
| `POST /verification/{challenge_id}/resend` | `{session_key}`; cool-down `429 otp_cooldown` with `Retry-After`, cap `429 otp_resend_limit` |
| `POST /verification/{challenge_id}/verify` | `{code, session_key}` → `{verification_token, channel, destination, expires_in_seconds}` |
| `POST /appointments` | Send `verification_token`. Refused with `422 contact_not_verified` without a token, or when the token's clinic, slot, browser session or destination differs from the booking's mobile (SMS/WhatsApp) or email |

Security properties (tests in `backend/tests/test_otp.py`): codes from `secrets`; only an HMAC-SHA256 with the server
pepper, bound to the challenge and destination, is stored; single use; expiry; wrong attempts are saved even though the
request fails, then the code locks; a new request replaces earlier open codes; challenges belong to one browser
session (another session gets `404`); signed-in patients with an already verified mobile skip the code for that
number; codes never appear in API responses or logs. In development and test, the console provider keeps messages in
memory and `GET /api/v1/dev/outbox/latest-code?destination=` returns the latest code for automated tests. That route
does not exist in staging or production, and those environments refuse console providers at startup.

## 7. Links, WhatsApp and campaigns

Admin → Booking page & Shopify builds links with optional preselection (`service`, `branch`, `doctor`) and campaign
labels (`utm_source`, `utm_medium`, `utm_campaign`); the Liquid snippet takes `source` and `campaign`. The WhatsApp tab
creates a share link (`https://wa.me/?text=…` with the booking link) and a click-to-chat link to the clinic's number.
Labels are cleaned on the server (known keys, short lower-case values) and stored with the appointment for reporting
only. They never change price, availability or permissions.

## 8. Website analytics (Admin → Website analytics, permission `reports:read`)

The website counts page views, Book clicks and booking-page views per day, page and source (`website_daily_stats`).
No cookies, IP addresses or visitor identifiers are stored, and browsers sending Do Not Track or Global Privacy
Control are not counted. The report combines these counts with real holds and online bookings: totals, a daily
chart, top pages, traffic sources, bookings by source and campaign. "Bookings per 100 views" uses bookings made through
the website or its embed.

## 9. Setup and deployment

1. Pull the code and run migrations: `python -m app.ops.setup` (Docker: the `migrate` service runs it). It also adds the
   new permissions to the system roles.
2. Environment (see `backend/.env.example` and the root `.env.example`): `DATA_ENCRYPTION_KEY` (required outside
   development; encrypts provider secrets), `OTP_PEPPER`, and optionally platform accounts: `SMS_PROVIDER`,
   `MSG91_*` / `TWILIO_*`, `OTP_SMS_TEMPLATE_ID`, `WHATSAPP_PROVIDER`, `WHATSAPP_CLOUD_*`, `OTP_WHATSAPP_TEMPLATE`, `SMTP_*`.
3. In the admin: Website → edit and **Publish**; Settings → OTP & verification → choose methods, connect accounts,
   **Send test** for each; Booking page & Shopify → copy links and code.
4. Check on a phone: website, Book, verification code arrives, booking confirmed, UPI payment screen.

Windows 10 (development): the commands in the main README work in PowerShell; use `.venv\Scripts\activate` instead
of `source .venv/bin/activate`.

## 10. Testing done and its limits

| Area | Tests |
|---|---|
| Website document, publish, versions, conflicts, permissions, isolation, validation | `backend/tests/test_website.py` (18) |
| OTP (all channels, security rules, limits, clinic accounts, exact provider requests) | `backend/tests/test_otp.py` (32) |
| Campaigns and analytics | `backend/tests/test_website_analytics.py` (4) |
| Links, Markdown safety, embed code | `frontend/tests/unit/website.test.tsx`, `embed-code.test.ts`, `booking-params.test.ts` |
| Browser: website editing → preview → publish → restore; unsafe link refused; email verification; analytics; booking on desktop and phone; embed; accessibility (axe) and CSP on every new page | `frontend/e2e/website.spec.ts`, `public-booking.spec.ts`, `quality.spec.ts` and the existing specs |

All suites run on SQLite and PostgreSQL. **Real provider delivery was not tested here:** this environment has no MSG91,
Twilio, WhatsApp Business or SMTP account. The tests check the exact HTTP requests sent to MSG91, the WhatsApp Cloud API
and SMTP (including the template and copy-code button parameters) and how provider errors are handled. After
connecting real accounts, use **Send test** for each channel and make one test booking per channel before going live.

## 11. Changed files and migrations

Migrations (run in order by `alembic upgrade head`):

| Revision | Adds |
|---|---|
| `0e800c38ccce` | `websites`, `website_versions` |
| `a39ceac72a9d` | `otp_challenges`, `messaging_provider_configs` |
| `12b230352120` | `website_daily_stats` |

Backend: `app/schemas/website.py`, `app/models/{website,verification,analytics}.py`,
`app/services/website_service.py`, `app/services/website_analytics_service.py`, `app/services/otp/*` (new package;
replaces `booking_verification_service.py`), `app/api/v1/{website,verification,dev}.py`, changes in `public.py`,
`uploads.py` (PDF upload), `appointment_service.py` (attribution), `organization_service.py` (`otp` settings),
`notifications/providers.py` (per-clinic credentials, copy-code button, hidden codes), `security/permissions.py`.

Frontend: `components/website/*` (public site), `components/website-admin/*` (builder), `app/(booking)/[slug]/*`
(website, `book`, `[page]`), `app/admin/website/*`, `app/admin/settings/verification`, `app/admin/website-analytics`,
`app/website-preview`, `components/public-booking/contact-verification.tsx`, `lib/{site-links,campaign,site-events,site-metadata,website-templates}.ts`,
`types/website.ts`, `services/{website,verification}.ts`, `proxy.ts` (same-origin framing for the preview only).

Shopify: `integrations/shopify/snippets/appointment-booking-button.liquid` and `sections/appointment-booking.liquid`
(link to `/{clinic}/book`, `source` / `campaign`).
