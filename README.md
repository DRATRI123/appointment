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

* [Architecture, diagrams, workflows and roadmap](documentation/architecture.md)
* [Database design and ER diagram](documentation/database.md)
* [Security architecture](documentation/security.md)
* [API overview](documentation/api.md)
* [Deployment](documentation/deployment.md)

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, project setup, database schema (56 tables), migrations, environment | ✅ done |
| 2 | Authentication (OTP, email/password, Google), users, organizations, staff, RBAC, audit logs, platform admin | ✅ done |
| 3 | Branches, professionals, services | next |
| 4–14 | See roadmap in `documentation/architecture.md` | planned |

## Repository layout

```
appointment-platform/
├── frontend/            Next.js app: (public), (auth), customer, professional, admin, super-admin
├── backend/             FastAPI app: api, core, models, schemas, repositories, services, security,
│                        payments, notifications, integrations, workers; migrations; tests
├── infrastructure/      docker, deployment, monitoring
├── documentation/       architecture, database, api, security, deployment
├── scripts/             seed, backup, dev helpers (PowerShell + bash)
├── docker-compose.yml   postgres + redis + backend + frontend
└── .env.example
```

## Run locally on Windows 10

Prerequisites: [Python 3.11+](https://www.python.org/downloads/windows/) (tick "Add to PATH"),
[Node.js 20+](https://nodejs.org/), Git. Open **PowerShell**.

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
Copy-Item .env.example .env
```

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
Copy-Item .env.example .env.local
npm run dev
```

Open http://localhost:3000. The frontend proxies `/api/*` to the backend
(`API_INTERNAL_URL`, default `http://127.0.0.1:8000`), so the browser only talks to one origin.

### 4. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

```powershell
cd frontend
npm run lint
npm run typecheck
npx playwright install chromium
npm run test:e2e
```

One-shot helpers: `scripts\dev-backend.ps1` and `scripts\dev-frontend.ps1` perform steps 2 and 3.

## First sign-in

* **Mobile OTP**: on the login page enter any mobile number. With the default `OTP_PROVIDER=console`
  the code is printed in the backend terminal and shown on the page in development.
* **Email + password**: use **Get started** to register, then create your organization. You become
  its owner and land in the admin dashboard.
* **Platform console**: sign in with the super admin created above and open `/super-admin`.
* **Google sign-in**: set `GOOGLE_CLIENT_ID` in `backend/.env`; the frontend button is wired in the
  Phase 2 API (`POST /api/v1/auth/google`) and needs the Google Identity Services script on the
  login page, which ships with the public booking site.

## Run with Docker (PostgreSQL + Redis)

```bash
cp .env.example .env   # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```

## Database migrations

```powershell
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
alembic downgrade -1
```

## Switching to PostgreSQL

Set `DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname` in `backend/.env` and run
`alembic upgrade head`. No code changes are needed; see `documentation/database.md`.

## Non-negotiable rules baked into the code

* Payment amounts are calculated on the backend in integer paise. The client never sends an amount.
* A QR code, screenshot or UTR never confirms a payment. Only staff with `payments:verify` can.
* Double booking is blocked by transactional slot holds **and** database partial unique indexes.
* Every tenant table carries `organization_id` and repositories always filter by it.
* No secrets in code. Everything comes from environment variables.
