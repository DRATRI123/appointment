# Deployment

## Local development (Windows 10)

See the root `README.md` for the exact PowerShell commands. Summary:

1. Install Python 3.11+ and Node.js 22 LTS (22.12 or newer; Node 20 is end-of-life).
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

- Set `FORWARDED_ALLOW_IPS` to the address (or network) of whatever sits in front of the API (the Next.js
  server, nginx, the load balancer). Only those peers may set `X-Forwarded-For`; otherwise every user would
  share the proxy's rate-limit bucket, or clients could spoof IPs past API-key allowlists.
- Behind HTTPS, set `ENABLE_HSTS=true` for the Next.js server (adds `Strict-Transport-Security`; the API adds it
  itself when `COOKIE_SECURE=true`). Only turn it on once every subdomain is served over HTTPS.
- After upgrading to a release that adds permissions (Phase 12 adds `customers:erase`), run
  `python ../scripts/seed.py` once from `backend/`. It is idempotent and grants new permissions to the built-in roles.
- Leave `WEBHOOK_ALLOW_PRIVATE_TARGETS` unset in production so webhooks cannot reach internal addresses.
- Run the worker (`python -m app.workers.runner --interval 20`): it delivers notifications and webhooks and
  syncs calendars.

## Environment variables

All variables are documented in the root `.env.example` and loaded by `app/core/config.py`.
