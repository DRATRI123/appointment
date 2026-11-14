# Deployment assets

The supported production setup is Docker Compose with Caddy for HTTPS:

* `../../docker-compose.yml`: the stack (Caddy, web, api, worker, backup, migrate, PostgreSQL 17, Redis, optional Prometheus)
* `../docker/Dockerfile.backend`, `../docker/Dockerfile.frontend`: the two images
* `../docker/Caddyfile`: HTTPS and routing
* `../monitoring/`: Prometheus scrape config and alert rules
* `../../scripts/generate_env.py`: creates the production `.env` with fresh secrets

Step-by-step guide (server preparation, install, backups and restore drills, updates and rollback, monitoring,
security checklist): `documentation/deployment.md`.
