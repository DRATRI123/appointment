# Monitoring

Four layers, from simplest to most complete. Start with the first; add the others when you have them.

1. **Uptime check (everyone).** Point any uptime service (UptimeRobot, Better Stack, Uptime Kuma) at
   `https://<your-domain>/api/v1/health/ready`. It returns 200 when the database is reachable, the schema is
   migrated and uploads can be written, and 503 otherwise.
2. **System status page (platform admins).** Super admin → System status shows the worker heartbeat, every
   background job's last success and error, messages/webhooks waiting, payments awaiting verification, and the
   last backup. No extra software needed.
3. **Prometheus + alerts (optional).** Set `METRICS_TOKEN` in `.env`, then
   `docker compose --profile monitoring up -d prometheus`. `prometheus.yml` scrapes `api:8000/metrics` inside the
   Docker network (Nginx never serves `/metrics`); Prometheus itself listens only on the server's localhost
   (`ssh -L 9090:127.0.0.1:9090 deploy@<server>`). `alerts.yml` holds 15 rules, each with a plain-language action:
   availability, worker, jobs, messages, payments, backups, errors and slow pages, plus security (many failed
   sign-ins, accounts being locked, one-time-code abuse, refresh-token reuse, bursts of refused access, rejected
   payments). Route alerts to email/Slack/WhatsApp with Alertmanager or Grafana.
4. **Scripted check.** `deployment/scripts/health-check.sh` (containers, HTTPS, certificate expiry, worker, backups,
   disk) exits non-zero when something needs attention; run it from cron.

Error tracking: set `SENTRY_DSN` to send unexpected errors to Sentry. Request bodies, cookies, auth headers,
query strings, user details and local variables are stripped before anything leaves the server
(`backend/app/core/observability.py::scrub_event`).
