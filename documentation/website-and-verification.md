# Clinic website, website builder and multi-channel verification

Status: phase 1 (inspection and plan). Later sections are filled in as each phase lands.

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
