# Deployment

## Local development (Windows 10)

See the root `README.md` for the exact PowerShell commands. Summary:

1. Install Python 3.11+ and Node.js 20+.
2. `backend`: create a venv, `pip install -r requirements.txt`, copy `.env.example` to `.env`,
   `alembic upgrade head`, `uvicorn app.main:app --reload`.
3. `frontend`: `npm install`, copy `.env.example` to `.env.local`, `npm run dev`.

## Docker (optional)

`docker-compose.yml` at the repository root starts `backend`, `frontend`, `postgres` and `redis`.

```bash
docker compose up --build
```

Set `DATABASE_URL=postgresql+psycopg://app:app@postgres:5432/appointments` in the compose
environment (already defaulted in the compose file).

## Production checklist (Phase 13)

* Reverse proxy (Nginx/Caddy) terminating TLS, forwarding `/api` to FastAPI and `/` to Next.js.
* `APP_ENV=production`, strong `SECRET_KEY`, `CORS_ORIGINS` set to the real domains,
  `COOKIE_SECURE=true`.
* PostgreSQL with daily `pg_dump` backups, point-in-time recovery when possible.
* Redis for rate limiting, caching and job queues.
* Object storage (S3-compatible) for uploads via `STORAGE_BACKEND=s3`.
* Centralised logs (JSON), uptime monitoring on `/health/ready`, error tracking.
* Run workers (`python -m app.workers.runner`) as a separate process.

## Environment variables

All variables are documented in the root `.env.example` and loaded by `app/core/config.py`.
