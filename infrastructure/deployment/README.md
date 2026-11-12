# Deployment assets

Phase 13 adds: Nginx/Caddy reverse-proxy configs, systemd units for `uvicorn` and the worker,
PostgreSQL backup cron (`pg_dump` + retention), and cloud-agnostic VPS/AWS runbooks.

Until then use `docker compose up --build` from the repository root (see `documentation/deployment.md`).
