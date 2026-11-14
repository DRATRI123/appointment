# Deployment

Two ways to run the platform:

* **Your Windows 10 PC, for development and trying things out**: see the root `README.md` (PowerShell commands,
  SQLite, no Docker needed).
* **Production on a Linux server with Docker**, described here. One `docker compose up -d` starts HTTPS, the
  web app, the API, the background worker, daily encrypted backups, PostgreSQL 17 and Redis.

```
Internet ──443──▶ Caddy (HTTPS, certificates renewed automatically)
                    ├── /api, /media, /docs ──▶ api (FastAPI) ──┬── postgres (PostgreSQL 17)
                    └── everything else ─────▶ web (Next.js)    └── redis
                  worker  (reminders, messages, calendar sync, webhooks)
                  backup  (daily at 02:30 IST: database + uploads, encrypted, verified, pruned)
                  migrate (runs once on every start: schema migrations + new permissions)
                  prometheus (optional, profile "monitoring")
```

Nothing except Caddy is reachable from the internet: the database, Redis, the API port and `/metrics` stay inside
the Docker network.

---

## 1. What you need

* A Linux server (VPS) with Ubuntu 24.04: **2 vCPU, 4 GB RAM, 40 GB disk** is comfortable for one clinic group.
  Choose a data centre in India if your patients are in India.
* A domain or subdomain, e.g. `book.sunriseclinic.in`.
* Accounts for login codes and messages: an SMS provider (MSG91 or Twilio) for OTP, and SMTP for email.
  Production refuses `OTP_PROVIDER=console`.
* Optional: an S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2) for off-site backup copies.

From Windows 10 you connect to the server with the built-in `ssh` command in PowerShell:
`ssh root@<server-ip>`.

## 2. Prepare the server (once)

```bash
apt-get update && apt-get -y upgrade
apt-get install -y ca-certificates curl git ufw unattended-upgrades
curl -fsSL https://get.docker.com | sh
```

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

Point the domain at the server: create an **A record** for `book.sunriseclinic.in` with the server's IP address.
Wait until `ping book.sunriseclinic.in` answers from that IP; Caddy needs it to obtain the certificate.

## 3. Install

```bash
git clone https://github.com/<you>/appointment.git /opt/appointment && cd /opt/appointment
```

```bash
python3 scripts/generate_env.py --domain book.sunriseclinic.in --email-from bookings@sunriseclinic.in
```

This writes `.env` with fresh random secrets (readable only by root). Then:

1. **Copy `DATA_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` into your password manager now.** Without them, clinical
   notes and backups cannot be read, by you or anyone else. Do not keep the only copy on the server.
2. Open `.env` (`nano .env`) and fill in the SMS and email settings (`MSG91_*`, `OTP_SMS_TEMPLATE_ID`, `SMTP_*`).
   Every other option is explained in `backend/.env.example`.

Start everything:

```bash
docker compose up -d --build
```

```bash
docker compose ps
```

All services should show `running`, and `api` and `web` should also be `healthy` (migrate shows `exited (0)`;
that is expected). Create your platform administrator:

```bash
docker compose run --rm api python -m app.ops.platform_admin --email you@example.com
```

Open `https://book.sunriseclinic.in`, sign in, and create the first clinic.

### If the API refuses to start

The API checks its own configuration and refuses unsafe production settings, listing every problem at once:

```bash
docker compose logs api | tail -20
```

For example `Unsafe production configuration: - OTP_PROVIDER cannot be console`. Fix `.env`, then run
`docker compose up -d` again.

## 4. Check the installation

| Check | How |
|---|---|
| HTTPS works, HTTP redirects | open `http://book.sunriseclinic.in`: it should switch to `https://` with a padlock |
| Readiness | `curl https://book.sunriseclinic.in/api/v1/health/ready` → `"status":"ok"`, checks for database, migrations, storage |
| Worker running | Super admin → **System health** → Background worker "Running" |
| Backup | `docker compose run --rm backup python -m app.ops.backup create`, then System health → Last backup |
| Login codes arrive | sign in with your mobile number |
| Payments | add the clinic's own UPI ID under Admin → UPI accounts and preview the QR. Payments are **never** marked paid automatically: staff verify each one against the bank statement |

## 5. Backups

**What is backed up.** Every night at `BACKUP_AT` (02:30 India time by default) the `backup` service writes one file
to the `backups` volume: a PostgreSQL dump, every uploaded file (logos, payment screenshots, patient documents) and
a manifest with SHA-256 checksums. The file is:

* **encrypted** with `BACKUP_ENCRYPTION_KEY` (AES-256-GCM, in authenticated chunks, so a damaged or tampered file is
  rejected rather than half-restored);
* **verified** straight after writing (decrypted, checksums compared, dump readable);
* **pruned**: the newest of each of the last 7 days, 4 weeks and 6 months are kept (`BACKUP_KEEP_*`);
* **copied off-site** when `BACKUP_S3_BUCKET` is set. Do set it: a backup on the same server is lost with the server.
  Turn on versioning or object lock on the bucket so a compromised server cannot delete old copies.

The result of every run (success or the error) appears on **System health** and in `/metrics`, and the
`BackupMissing` alert fires when there has been no good backup for 26 hours.

```bash
docker compose run --rm backup python -m app.ops.backup list
```

```bash
docker compose run --rm backup python -m app.ops.backup verify /data/backups/backup-20261114-210000.tar.gz.enc
```

To copy a backup to your own computer (PowerShell on Windows):

```powershell
scp root@<server-ip>:/var/lib/docker/volumes/appointment_backups/_data/backup-20261114-210000.tar.gz.enc .
```

### Restore (and practise it)

A backup you have never restored is a hope, not a backup. Practise once a month on a spare server or a local copy.

```bash
docker compose stop api worker backup web
```

```bash
docker compose run --rm backup python -m app.ops.backup restore /data/backups/backup-20261114-210000.tar.gz.enc --yes
```

```bash
docker compose up -d
```

`restore` first verifies the file, takes a safety backup of the current data, then replaces the database and
uploads; the previous uploads folder is kept beside it as `uploads.before-restore-<time>`. The `migrate` step then
brings the schema up to the current release. To restore on a **new** server: install as in section 3 but put your
saved `.env` (or at least the same `DATA_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY` and `SECRET_KEY`) in place
before the first start, copy the backup file into the `backups` volume, then restore.

## 6. Updating

```bash
cd /opt/appointment
docker compose run --rm backup python -m app.ops.backup create
git pull
docker compose up -d --build
```

The `migrate` service applies database migrations and grants any new permissions before the API and worker start;
if it fails, the old containers keep running and `docker compose logs migrate` shows why.

**Rolling back**: before updating, tag the running images (`docker tag appointment-api:latest appointment-api:previous`
and the same for `appointment-web`). To go back, set `TAG=previous` in `.env` and `docker compose up -d`. If the new
release had already migrated the database, restore the backup taken just before the update.

## 7. Monitoring

| Layer | Set up | Tells you |
|---|---|---|
| Uptime check | point UptimeRobot / Better Stack / Uptime Kuma at `https://<domain>/api/v1/health/ready` | the site is down, the database is unreachable, migrations are pending, uploads cannot be written |
| System health page | nothing, built in (Super admin → System health) | worker heartbeat, each job's last success and error, messages and webhooks waiting, payments awaiting verification, last backup |
| Prometheus + alerts | `docker compose --profile monitoring up -d` | 9 alert rules with plain-language actions (`infrastructure/monitoring/alerts.yml`) |
| Error tracking | set `SENTRY_DSN` | unexpected errors with stack traces; bodies, cookies, auth headers, query strings, user details and local variables are removed first |

Prometheus listens only on the server's localhost. View it from your PC through an SSH tunnel:
`ssh -L 9090:127.0.0.1:9090 root@<server-ip>`, then open `http://localhost:9090/alerts`. Connect Alertmanager or
Grafana to deliver alerts by email, Slack or WhatsApp.

**Logs**: `docker compose logs -f api` (JSON lines with a request id; the id is also shown to users on error
messages, so a support request can be traced). Docker keeps 5 × 10 MB per service.

## 8. Security checklist

Enforced by the software (the API will not start otherwise): random `SECRET_KEY`, `DATA_ENCRYPTION_KEY`,
`OTP_PEPPER`; secure cookies; HTTPS `FRONTEND_URL` and `CORS_ORIGINS`; named `TRUSTED_HOSTS`; trusted proxies limited
to the Docker network; real OTP provider; rate limiting on; webhooks cannot reach private addresses.

Your part:

* SSH with keys only (`PasswordAuthentication no` in `/etc/ssh/sshd_config`); keep `unattended-upgrades` on.
* Keep `.env` out of git (it is ignored) and keep a copy of it in your password manager.
* Off-site backups with versioning; a monthly restore drill.
* Review Super admin → Platform audit logs and each clinic's audit log regularly.
* Before advertising compliance with the DPDP Act 2023 or any healthcare rule, get an independent legal and security
  review. This software provides controls; it does not make a deployment compliant by itself.

## 9. Other options

* **Uploads in S3 instead of the server disk**: set `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`,
  `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (and `S3_ENDPOINT_URL` for R2/B2/MinIO). The bucket stays private:
  objects are encrypted at rest and `/media` is streamed through the API. Back up the bucket with the provider's
  versioning; the nightly backup then contains the database only.
* **Behind Cloudflare or a load balancer**: add their address ranges to Caddy's `trusted_proxies` (see the comment in
  `infrastructure/docker/Caddyfile`), otherwise every visitor appears to come from the proxy.
* **SQLite**: fine for development and trials on your PC (backups work the same way:
  `python ..\scripts\backup.py create`). The Docker stack uses PostgreSQL, the supported production database;
  Phase 14 covers moving existing SQLite data across.
* **Building behind a corporate proxy** that inspects TLS: pass its CA bundle as a build secret,
  `docker build --secret id=extra_ca,src=corp-ca.pem ...`; it is used only during the build.

## 10. Running without Docker

Everything above is plain Python and Node; the Docker services are just these commands:

| Service | Command (from `backend/`) |
|---|---|
| migrate | `python -m app.ops.setup` |
| api | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers` |
| worker | `python -m app.workers.runner --interval 20` |
| backup | `python -m app.ops.backup schedule` (or `create` from cron / Windows Task Scheduler) |
| web (from `frontend/`) | `npm run build` then `npm run start` |

## Environment variables added in Phase 13

| Variable | Default | Purpose |
|---|---|---|
| `METRICS_TOKEN` | unset (`/metrics` off) | bearer token for Prometheus; at least 24 characters |
| `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` | unset, `0` | optional error tracking (personal data scrubbed) |
| `BACKUP_DIR` | `/data/backups` in Docker | where backups are written |
| `BACKUP_ENCRYPTION_KEY` | unset (not encrypted) | base64 of 32 random bytes; **set it in production** |
| `BACKUP_AT`, `BACKUP_TIMEZONE` | `02:30`, `Asia/Kolkata` | daily schedule |
| `BACKUP_KEEP_DAILY` / `_WEEKLY` / `_MONTHLY` | 7 / 4 / 6 | retention |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX` | unset, `backups/` | off-site copy (uses the `S3_*` credentials) |
| `S3_PREFIX` | empty | folder inside the uploads bucket |
| `DOMAIN`, `ENABLE_HSTS`, `DOCKER_SUBNET`, `TAG` | | Docker Compose only (root `.env`) |

The backend reads only `backend/.env` when run directly; the root `.env` belongs to Docker Compose, so production
values never leak into a local development run.
