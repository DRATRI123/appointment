# Appointment Platform

Enterprise-ready, multi-tenant appointment booking and management platform for doctors, clinics,
hospitals, Ayurvedic and dermatology practices, wellness centres, physiotherapists, nutritionists,
consultants, salons and independent professionals.

Payments are collected through the **organization's own UPI QR code** (Google Pay, PhonePe, Paytm,
BHIM and any UPI app). There is no Razorpay, Stripe, Cashfree or PayU. Staff verify each UTR before an
appointment is confirmed.

| Layer | Stack |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, shadcn/ui, Radix, TanStack Query, React Hook Form, Zod, Framer Motion, FullCalendar, Recharts |
| Backend | Python, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, structlog, slowapi |
| Database | SQLite for development, PostgreSQL for production (same models and migrations) |
| Optional | Redis, ARQ/Celery workers, S3-compatible storage, Docker |

## Documentation

* [Architecture, diagrams, workflows and roadmap](docs/architecture.md)
* [Database design and ER diagram](docs/database.md)
* [Security architecture](docs/security.md)
* [API overview](docs/api.md)
* [Developer guide: API keys, webhooks, code samples, go-live checklist](docs/developer-guide.md) (also in the admin under **Developer docs**)
* [Public booking API with example requests](docs/public-booking-api.md)
* [Integration Hub: Google, Gmail, WhatsApp, SMS, n8n, CRM, accounting, S3, analytics](docs/integrations/integration-architecture.md) · [Shopify and website integration (no app needed)](docs/integrations/shopify-integration.md)
* [Clinic website, website builder, OTP & verification, analytics](docs/website-and-verification.md)
* [Local development on Windows](docs/local-development.md) and [with Docker](docs/docker-development.md)
* [Environment configuration: templates and the checks per environment](docs/environment-configuration.md)
* [Production deployment (future VPS): setup, deploy, update, rollback](docs/production-deployment.md)
* [Super admin setup and recovery](docs/superadmin-setup.md) · [Who may do what (permissions matrix)](docs/permissions-matrix.md)
* [Backups and restore](docs/backup-restore.md) · [Database migrations](docs/database-migrations.md) · [Encryption and keys](docs/encryption.md) · [Privacy and data protection](docs/privacy-and-data-protection.md)
* [Security and load testing report, remaining risks](docs/security-testing-report.md) · [Troubleshooting](docs/troubleshooting.md)
* [Performance, security and encryption review: audit, load tests, before/after](docs/optimization-report.md)

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, project setup, database schema (56 tables), migrations, environment | ✅ done |
| 2 | Authentication (OTP, email/password, Google), users, organizations, staff, RBAC, audit logs, platform admin | ✅ done |
| 3 | Branches, professionals, service categories, services, packages, image uploads, public catalogue pages | ✅ done |
| 4 | Schedules, exceptions, holidays, leave; availability engine; slot holds; booking wizard; appointment lifecycle, reschedule, recurring, waitlist; calendar | ✅ done |
| 5 | Customer management, family members, encrypted notes, private documents with retention, CSV export, no-code booking form builder with versions, templates, conditional fields and server-side validation | ✅ done |
| 6 | Own UPI QR payments: UPI accounts, dynamic QR, app deep links, UTR and screenshot submission, verification queue with audit trail, cash and bank transfers, balance payments, coupons | ✅ done |
| 7 | Refunds (request → approve → record the transfer you sent, with proof and maker-checker option) and bank statement reconciliation (CSV import with bank presets or custom column mapping, UTR/reference/amount matching suggestions, unmatched report with CSV export) | ✅ done |
| 8 | Notifications: email (SMTP), SMS (MSG91, Twilio), WhatsApp (Meta Cloud API, Twilio), in-app bell; outbox with retries and backoff; reminders; editable templates with live preview; per-event channel settings; customer message preferences and WhatsApp opt-in; OTP delivery | ✅ done |
| 9 | Google Calendar per professional (events, Google Meet links, busy time blocks slots), Zoom meetings (Server-to-Server OAuth), manual video links, background sync with retries, .ics downloads and private calendar feeds, Join / Add-to-calendar for customers | ✅ done |
| 10 | Admin dashboard (KPIs vs previous period, daily trends, utilization, busiest times, needs-attention list), professional stats, 10 reports with CSV/Excel export (audit-logged), platform dashboard, subscription plans with enforced limits, organization detail, platform settings and announcement | ✅ done |
| 11 | Developer portal: scoped API keys (hashed, IP allowlist, per-key rate limit, usage), signed webhooks with outbox delivery, retries, SSRF protection and delivery logs, API docs; platform API usage; trusted-proxy client IPs | ✅ done |
| 12 | Security hardening and testing: security counters survive failed requests, cross-tenant sweep of every ID route, forwarded-IP spoofing fix, no input echo in errors, generic 500s, CSP and safe post-login redirects, accessibility (axe) and CSP checks in the browser suite, customer data erasure, bandit / pip-audit / npm audit / ruff / coverage gates in CI | ✅ done |
| 13 | Production: Docker stack with automatic HTTPS (now Nginx + Let's Encrypt, see 17), PostgreSQL 17, Redis, worker and one-shot migrations; startup refuses unsafe settings; encrypted, verified, pruned daily backups with restore and off-site copy; S3-compatible uploads; System health page, Prometheus metrics and alert rules, optional Sentry (scrubbed); nonce-based CSP; shared Redis rate limits; deployment runbook | ✅ done |
| 14 | PostgreSQL and performance: whole suite runs on PostgreSQL in CI; real concurrency races fixed with row locks (payments verified twice, refunds beyond the amount paid, coupon limits, double cancel) and proven by parallel tests; commit before the response is sent; SQLite → PostgreSQL migration tool with checksum verification; N+1 queries removed; indexes; multi-process API; load-tested to 150 simultaneous users on 2 cores (`docs/performance.md`) | ✅ done |
| 15 | Public booking page and Shopify: premium mobile-first booking at `/{clinic}` (doctor profiles, services with prices, branch choice, day strip and grouped times, mobile one-time code, review with server price, own UPI QR + UTR, clear success/pending/failed screens); preselection by URL (`?service=&branch=&doctor=&date=`), validated and never trusted for price; embeddable `/embed/{clinic}` with per-clinic allowed websites (`frame-ancestors`, fail closed) and auto-resize; Shopify Liquid button snippet and theme section; admin *Booking page & Shopify* screen with generated code (`docs/integrations/shopify-integration.md`) | ✅ done |
| 16 | Clinic website and builder: a full public website per clinic at `/{clinic}` (hero, about, services, doctors, categories, facilities, gallery, approved testimonials, FAQ, locations with hours, contact, custom pages, policy and location pages, SEO), booking at `/{clinic}/book` (service → doctor → location → time); Website Management with templates, drag-and-drop, buttons, pages, device preview, draft/publish/restore; OTP by SMS, WhatsApp or email with clinic-owned encrypted provider accounts and test sends; campaign tracking, WhatsApp links and cookie-free website analytics (`docs/website-and-verification.md`) | ✅ done |
| 17 | Enterprise hardening: four environments with strict per-environment checks; branch isolation for single-branch staff; super admin MFA, IP allow-list and recovery (no public sign-up); permissions matrix tested for every role; Docker for dev/test/production with non-root, read-only, capability-free containers and internal database network; Nginx + Let's Encrypt; deploy/update/rollback/backup/restore/health scripts for a future Ubuntu VPS (rehearsed, not deployed); Semgrep, Gitleaks, Trivy, ZAP in CI; abuse tests (same-slot race, duplicate UTR, code guessing, 100 users) (`docs/security-testing-report.md`) | ✅ done |

## Repository layout

```
appointment-platform/
├── frontend/            Next.js app: (public), (auth), customer, professional, admin, super-admin
├── backend/             FastAPI app: api, core, models, schemas, repositories, services, security,
│                        payments, notifications, integrations, workers; migrations; tests
├── deployment/          docker (Dockerfiles), nginx, scripts (setup/deploy/update/rollback/backup/restore/health), monitoring
├── docs/                all documentation
├── scripts/             seed, backup, dev helpers (PowerShell + bash)
├── compose.yaml         Docker: shared + compose.dev / compose.test / compose.production.yaml
└── .env.*.example       one template per environment (.env.example documents every setting)
```

## Run locally on Windows 10

**Easiest:** install Python 3.11+ and Node.js 22, then double-click **`START-APP.bat`** in this folder. The first
time it installs everything; every time it updates the database and opens the API, the worker and the website
(http://localhost:3000). Close its 3 windows to stop. The steps below do the same by hand.

Prerequisites: [Python 3.11+](https://www.python.org/downloads/windows/) (tick "Add to PATH"),
[Node.js 22 LTS](https://nodejs.org/) (22.12 or newer), Git. Open **PowerShell**.

### 1. Clone

```powershell
git clone <your-repo-url> appointment-platform
cd appointment-platform
```

### 2. Backend (FastAPI)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item ..\.env.development.example .env
```

`.env.development.example` holds safe local defaults (SQLite, plain HTTP on localhost, messages printed instead of
sent). `.env.example` documents every option; staging and production have their own templates
([docs/environment-configuration.md](docs/environment-configuration.md)).

Generate a secret and paste it into `.env` as `SECRET_KEY` (required outside development, recommended
always):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create the SQLite database and apply migrations, then seed roles and permissions:

```powershell
alembic upgrade head
python ..\scripts\seed.py
```

Create the platform super admin (prompts for a password):

```powershell
python ..\scripts\create_platform_admin.py --email you@example.com --name "Your Name"
```

Start the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

* API: http://localhost:8000/api/v1/health
* Swagger docs: http://localhost:8000/docs
* OpenAPI JSON: http://localhost:8000/api/v1/openapi.json

If PowerShell blocks the activation script, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### 3. Frontend (Next.js)

Open a second PowerShell window:

```powershell
cd appointment-platform\frontend
npm install
npm run dev
```

The website needs no env file locally (defaults point at the API on port 8000); put personal overrides in `frontend/.env.local`.

Open http://localhost:3000. The frontend proxies `/api/*` to the backend
(`API_INTERNAL_URL`, default `http://127.0.0.1:8000`), so the browser only talks to one origin.

### 4. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest --cov=app
ruff check app tests
bandit -q -r app
pip-audit -r requirements.txt
```

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm audit --audit-level=high
npx playwright install chromium
npm run test:e2e
```

`npm test` runs fast unit tests (Vitest). `npm run test:e2e` drives a real browser through booking, payments,
refunds and the admin pages, and fails on any Content-Security-Policy violation, console error or serious
accessibility problem (axe, WCAG 2.1 AA rules).

The end-to-end suite registers several accounts in quick succession, so start the backend it talks to
with rate limiting off (`RATE_LIMIT_ENABLED=false` in `backend/.env`, or set it for that terminal
session). Keep rate limiting on everywhere else.

One-shot helpers: `scripts\dev-backend.ps1` and `scripts\dev-frontend.ps1` perform steps 2 and 3.

### 5. Many users on one Windows PC (for example the clinic's reception computer)

`--reload` runs a single process for development. To serve many people at once, run several API processes (one per
CPU core), the background worker, and the built frontend, each in its own PowerShell window:

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
```

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
python -m app.workers.runner
```

```powershell
cd frontend
npm run build
npm run start
```

Remove the `WORKER_THREADS=8` line from `backend/.env` when you use `--workers` (8 threads suit one process; with
several processes the default of 40 measured best). SQLite works with several processes (WAL mode); keep the database
on the PC's own disk, never on a network drive.
Measured results and limits: [`docs/optimization-report.md`](docs/optimization-report.md).

## First sign-in

* **Mobile OTP**: on the login page enter any mobile number. With the default `OTP_PROVIDER=console`
  the code is printed in the backend terminal and shown on the page in development.
* **Email + password**: use **Get started** to register, then create your organization. You become
  its owner and land in the admin dashboard.
* **Platform console**: sign in with the super admin created above and open `/super-admin`.
* **Public booking page**: every organization gets `/o/<slug>` listing branches, services and
  professionals. The slug is shown under Organization settings → Profile.
* **UPI payments**: add the clinic's UPI ID under Payments → UPI accounts and scan the test QR. Bookings
  that need an advance then show a QR to the customer. After they submit the UTR, approve it under
  Payments → Verification once you see the credit in the bank.
* **Google sign-in**: set `GOOGLE_CLIENT_ID` in `backend/.env`; the frontend button is wired in the
  Phase 2 API (`POST /api/v1/auth/google`) and needs the Google Identity Services script on the
  login page, which ships with the public booking site.

## Background jobs

The worker expires holds and unpaid bookings, schedules reminders, **delivers notifications** (email, SMS,
WhatsApp) and **syncs calendars and video meetings** and **delivers webhooks**. Run it alongside the API; a short interval keeps messages prompt:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.workers.runner --interval 20
```

(`--once` runs a single pass.) Without the worker, messages wait in the outbox (Admin → Notifications);
in-app bell notifications appear immediately either way.

### Sending real email, SMS and WhatsApp

Development uses `console` providers: every message is written to the API/worker log and shown in the
outbox. To deliver for real from your PC, set `DEV_ALLOW_REAL_MESSAGES=true` (the app refuses real providers in
development otherwise, so a copied production file cannot message real patients by accident), then these in
`backend/.env`, and restart the API and worker:

* Email: `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls`, `ssl` or `none`),
  `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`.
* SMS: `SMS_PROVIDER=msg91` with `MSG91_AUTH_KEY`, `MSG91_SENDER_ID`, or `SMS_PROVIDER=twilio` with
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SMS_FROM`. In India every SMS must match a
  DLT-registered template: put the DLT/flow id on each SMS template (Admin → Notifications → Templates).
* WhatsApp: `WHATSAPP_PROVIDER=meta` with `WHATSAPP_CLOUD_TOKEN`, `WHATSAPP_CLOUD_PHONE_NUMBER_ID`, or
  `twilio` with `TWILIO_WHATSAPP_FROM`. Business-initiated messages need templates approved by Meta;
  put the template name on each WhatsApp template. Only customers who opted in receive WhatsApp.
* Login codes: `OTP_PROVIDER=notifications` sends OTPs through the SMS/email provider
  (`OTP_SMS_TEMPLATE_ID` for the DLT template).

Then turn the channels on in Admin → Notifications → Settings and use **Delivery setup → Send a test
message**.

### Google Calendar, Google Meet and Zoom (optional)

* **Google Calendar / Meet**: in Google Cloud Console create an OAuth client of type *Web application*,
  enable the *Google Calendar API*, and add the redirect URI shown on Admin → Integrations (by default
  `<FRONTEND_URL>/api/v1/integrations/google/callback`). Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
  in `backend/.env` and restart. Each professional then clicks **Connect Google Calendar** (Admin →
  Integrations, or Calendar & video in the professional dashboard). While the Google app is in *testing*
  mode only the test users you list can connect; publish it for wider use.
* **Zoom**: in the Zoom App Marketplace create a *Server-to-Server OAuth* app with the scopes
  `meeting:write:meeting:admin` and `user:read:user:admin`, then paste the account ID, client ID and
  secret on Admin → Integrations (stored encrypted, checked with Zoom before saving).
* **No accounts needed**: each professional can set a fixed meeting-room link, staff can add a link to a
  single appointment, customers get **Add to calendar** files, and professionals can subscribe to a
  private calendar feed from any calendar app.

Calendar events and meetings are created by the worker, so keep it running.

## Run in production (Docker, HTTPS, backups, monitoring)

Not deployed yet. When you have an Ubuntu 24.04 VPS and a domain pointing at it:

```bash
sudo deployment/scripts/setup-server.sh --user deploy
```

```bash
deployment/scripts/deploy.sh --domain book.yourclinic.in --email you@yourclinic.in
```

The first deploy creates `.env` with fresh secrets and stops so you can add your email/SMS details; the next run
builds, backs up before migrations, gets the HTTPS certificate, starts Nginx, the website, API, worker, daily
encrypted backups, PostgreSQL 17 and Redis, and checks health. Updates: `update.sh`; going back: `rollback.sh`.
Full guide: [docs/production-deployment.md](docs/production-deployment.md).

## Database migrations

```powershell
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
alembic downgrade -1
```

## Switching to PostgreSQL

Set `DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname` in `backend/.env` and run
`alembic upgrade head`. No code changes are needed; see `docs/database.md`.

## Non-negotiable rules baked into the code

* Payment amounts are calculated on the backend in integer paise. The client never sends an amount.
* A QR code, screenshot or UTR never confirms a payment. Only staff with `payments:verify` can.
* Double booking is blocked by transactional slot holds **and** database partial unique indexes.
* Every tenant table carries `organization_id` and repositories always filter by it.
* No secrets in code. Everything comes from environment variables.
