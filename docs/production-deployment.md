# Production deployment (future Hostinger VPS or any Ubuntu 24.04 server)

> Nothing here has been deployed. These scripts were written for a server you will rent later. They were rehearsed
> end to end on a local machine with `DOMAIN=localhost` and a self-signed certificate. Until then, keep using
> `START-APP.bat` on your PC.

```
Internet ──80/443──▶ nginx (unprivileged; TLS 1.2/1.3; Let's Encrypt via certbot)
                       ├── /api, /media, /docs ──▶ api (FastAPI, 2 processes) ──┐
                       └── everything else ─────▶ web (Next.js)                 │   "data" network (internal:
                     worker   reminders, messages, webhooks, unpaid holds ──────┤    no internet, no ports)
                     backup   daily, encrypted, verified, pruned ───────────────┼──▶ postgres 17
                     migrate  once per release, before api/worker start ────────┘──▶ redis 7
                     certbot  renews the certificate twice a day
```

Only Nginx has public ports. The database, Redis, the API port and `/metrics` are reachable only inside Docker.

## 1. What you need

* An Ubuntu 24.04 VPS. **2 vCPU / 8 GB RAM / 80 GB disk** matches the default container limits (for example a
  Hostinger KVM 2). A data centre in India if your patients are in India.
* A domain or subdomain, e.g. `book.sunriseclinic.in`, with an **A record** pointing at the server's IP.
* Message accounts: SMTP for email, and MSG91 or Twilio for SMS (or set a channel to `disabled`).
* Optional: an S3-compatible bucket for off-site backup copies (strongly recommended).

## 2. Prepare the server (once)

Connect from Windows PowerShell with `ssh root@<server-ip>`, then:

```bash
git clone <your repository URL> /opt/appointment
```

```bash
sudo /opt/appointment/deployment/scripts/setup-server.sh --user deploy
```

`setup-server.sh` (safe to run again):
* installs security updates now and switches on automatic security updates;
* installs Docker Engine and the Compose plugin from Docker's official repository;
* configures the firewall: only SSH, 80 and 443 open, plus fail2ban for SSH;
* creates the `deploy` user that runs the app;
* turns off root login and passwords, **but only if that user has an SSH key**, so you cannot lock yourself out;
* adds 2 GB swap.

Then sign in as that user and move the checkout to them:

```bash
sudo chown -R deploy:deploy /opt/appointment
```

```bash
ssh deploy@<server-ip>
```

## 3. First deploy

```bash
cd /opt/appointment
```

```bash
deployment/scripts/deploy.sh --domain book.sunriseclinic.in --email you@sunriseclinic.in
```

The first run only creates `.env` with fresh random secrets (permissions 600), then **stops** and tells you to:

1. **Copy `DATA_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` into your password manager**, off the server. Without them,
   clinical notes and backups cannot be read by anyone, you included.
2. Fill in the message settings with `nano .env`:
   * email: `SMTP_HOST`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD`;
   * SMS: `MSG91_AUTH_KEY` and `OTP_SMS_TEMPLATE_ID`.

   Or set a channel to `disabled`.

Then run it again:

```bash
deployment/scripts/deploy.sh
```

What it does, stopping at the first problem:

1. Refuses example or empty values in `.env`. The app then checks its own settings
   ([environment-configuration.md](environment-configuration.md)) **before anything is started or stopped**.
2. Builds the images, tagged with the git commit, and re-pulls base images to pick up security updates.
3. Starts PostgreSQL and Redis. If migrations are pending on an existing database, it takes a **verified backup**
   first. If a migration would remove data, it stops and asks you to type `apply`
   ([database-migrations.md](database-migrations.md)).
4. Starts the release. `migrate` runs first; the API starts only if it succeeds.
5. Gets the Let's Encrypt certificate on the first run. Until then Nginx serves only "this site is being set up" over
   HTTP, never app traffic.
6. Checks health ([§5](#5-check-it)), takes a baseline backup if none exists, and records the release.
7. Reminds you to create the super admin ([superadmin-setup.md](superadmin-setup.md)).

Staging is the same with `--env staging` on its own server and domain (separate secrets, never production's).

## 4. Day to day

| Task | Command |
|---|---|
| Update to the latest code | `deployment/scripts/update.sh` (refuses local edits; shows the incoming commits; then deploy.sh) |
| A specific version | `deployment/scripts/update.sh --ref v1.4.0` |
| Go back one release | `deployment/scripts/rollback.sh` (`--list` shows the releases) |
| Back up now | `deployment/scripts/backup.sh` |
| Restore | `deployment/scripts/restore.sh <backup file>` ([backup-restore.md](backup-restore.md)) |
| Is everything OK? | `deployment/scripts/health-check.sh` |
| Logs | `docker compose logs -f api` (also `web`, `worker`, `nginx`, `postgres`, `backup`, `certbot`) |

`.env` sets `COMPOSE_FILE`, so plain `docker compose ...` always means the production stack, and `TAG` is the live
release.

**Rollback is code only.** Images of earlier releases stay on the server and the database is not touched. If the
newer release changed the database schema, `rollback.sh` stops and explains the choice:
* fix forward (usually best), or
* restore the backup taken just before that release, which loses everything since.

## 5. Check it

`deployment/scripts/health-check.sh` prints one line per check and exits 1 if anything needs attention, so it also
works from cron:
* every container running and healthy (migrate finished);
* API and website answering over HTTPS;
* HTTP redirecting to HTTPS;
* `/metrics` not public;
* certificate valid for 14+ days;
* worker heartbeat recent;
* last backup recent and verified;
* no job failing repeatedly;
* disk below 85%.

```bash
crontab -e
```

Add this line to get an email when a check fails (needs a mail command on the server; otherwise use an uptime
service on `https://<domain>/api/v1/health/ready`):

```
*/5 * * * * cd /opt/appointment && deployment/scripts/health-check.sh --quiet || echo "check the clinic site" | mail -s "Clinic site" you@x.in
```

Monitoring: Super admin → **System health**, and optionally Prometheus with 15 alert rules (including the security
ones: failed sign-ins, lock-outs, code abuse, refused access, rejected payments).

```bash
docker compose --profile monitoring up -d prometheus
```

Prometheus is on the server's localhost only. To view it, open an SSH tunnel with
`ssh -L 9090:127.0.0.1:9090 deploy@<server>`, then go to http://localhost:9090/alerts.

## 6. What protects the server

| Layer | How |
|---|---|
| Network | ufw: only SSH/80/443. Only Nginx publishes ports. PostgreSQL/Redis on an internal network. Prometheus on localhost |
| TLS | TLS 1.2/1.3 only, forward-secret ciphers, HSTS, HTTP→HTTPS, unknown host names refused (no certificate, no content) |
| Proxy | Nginx replaces any client-sent `X-Forwarded-For`; strict per-IP limits on sign-in and code POSTs; slow-client timeouts; 12 MB body limit; access logs without query strings |
| Containers | non-root, no capabilities, no-new-privileges, read-only filesystems, memory/CPU/process limits, no Docker socket, pinned images |
| Secrets | only in `.env` (600) on the server; never in images or git; generated per server |
| App | strict start-up checks, MFA for super admins, branch isolation, rate limits, audit logs ([security.md](security.md)) |

Your part: SSH keys only; keep a copy of `.env` in your password manager; off-site backups with versioning; a
monthly restore drill; review the audit logs. Before claiming compliance with the DPDP Act 2023 or any healthcare
rule, get an independent legal and security review. This software provides controls; it does not make a
deployment compliant by itself.

## 7. Notes

* **Behind Cloudflare or a load balancer:** add their ranges with `set_real_ip_from` in
  `deployment/nginx/snippets/proxy.conf`. Otherwise every visitor appears to come from the proxy.
* **ARM servers:** regenerate the lock for that platform:
  `uv pip compile requirements.txt --python-version 3.13 --python-platform aarch64-manylinux_2_28 --generate-hashes -o requirements.lock`.
* **Uploads in S3** instead of the server disk: `STORAGE_BACKEND=s3` plus the `S3_*` settings.
* **Without Docker:** the services are plain commands, `python -m app.ops.setup`, `uvicorn app.main:app`,
  `python -m app.workers.runner`, `python -m app.ops.backup schedule` and `npm run start`. You then provide HTTPS,
  process supervision and backups yourself.
