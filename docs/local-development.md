# Local development (Windows, no Docker needed)

## The easy way: double-click `START-APP.bat`

Install once: [Python 3.11+](https://www.python.org/downloads/windows/) (tick "Add to PATH") and
[Node.js 22 LTS](https://nodejs.org/). Then double-click **`START-APP.bat`** in the project folder.

* **First time:** it installs the backend and the website (a few minutes, needs internet), and copies
  `.env.development.example` to `backend\.env`.
* **Every time:** it updates the database (safe to repeat), then opens 3 windows (API, worker, website) and the app
  at http://localhost:3000.
* **To stop:** close the 3 windows.

What runs where:

| Window | What it is | Address |
|---|---|---|
| API | FastAPI with auto-reload | http://localhost:8000/docs |
| worker | background jobs: reminders, messages, releasing unpaid holds | (no page) |
| website | Next.js with auto-reload | http://localhost:3000 |

Local settings (`backend\.env`): SQLite file in `backend\data\`, plain HTTP on localhost, and messages and sign-in
codes **printed in the API window instead of sent**. Two-step sign-in is optional for the super admin on your PC.
See [environment-configuration.md](environment-configuration.md) for every check.

## First account

Create your super admin (from `backend\`, virtual environment active):

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.ops.platform_admin --email you@example.com
```

Or fill the app with clearly marked **sample data**: a "Demo Clinic (sample data)" at `/demo-clinic` with 2 doctors,
3 services and 5 "Sample Patient" bookings. The owner's password is printed once.

```powershell
python -m app.ops.seed_demo
```

`seed_demo` refuses to run outside development/test, so sample data can never reach a real database.

## By hand (what START-APP.bat does)

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\.env.development.example .env
alembic upgrade head
python ..\scripts\seed.py
uvicorn app.main:app --reload --port 8000
```

A second window for the worker (from `backend\`, virtual environment active):

```powershell
python -m app.workers.runner --interval 20
```

A third window for the website:

```powershell
cd frontend
npm install
npm run dev
```

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Tests

Backend (from `backend\`, virtual environment active):

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
ruff check app tests
```

Website (from `frontend\`):

```powershell
npm run lint
npm run typecheck
npm test
```

End-to-end browser tests: `npx playwright test` with the app running.

## Moving your local data to PostgreSQL

Super admin → **Database** does it from the browser: pause saving, copy, verify, switch, with an undo button. See
[database-migrations.md](database-migrations.md).

## Exact package versions

Docker images install `backend/requirements.lock` (exact versions with hashes, for Linux x86-64 servers). Your PC
uses `requirements.txt` (compatible version ranges), because the lock's hashes are for Linux wheels. CI runs the
tests against the lock, so the versions that ship are the versions that are tested.
