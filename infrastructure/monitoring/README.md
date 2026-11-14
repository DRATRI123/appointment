# Monitoring

Three layers, from simplest to most complete. Start with the first; add the others when you have them.

1. **Uptime check (everyone).** Point any uptime service (UptimeRobot, Better Stack, Uptime Kuma) at
   `https://<your-domain>/api/v1/health/ready`. It returns 200 when the database is reachable, the schema is
   migrated and uploads can be written, and 503 otherwise.
2. **System status page (platform admins).** Super admin → System status shows the worker heartbeat, every
   background job's last success and error, messages/webhooks waiting, payments awaiting verification, and the
   last backup. No extra software needed.
3. **Prometheus + alerts (optional).** Set `METRICS_TOKEN` and start the stack with the `monitoring` profile
   (`docker compose -f docker-compose.prod.yml --profile monitoring up -d`). `prometheus.yml` scrapes
   `backend:8000/metrics` inside the Docker network (never exposed publicly); `alerts.yml` holds the rules, each
   with a plain-language action. Route alerts to email/Slack/WhatsApp with Alertmanager or Grafana.

Error tracking: set `SENTRY_DSN` to send unexpected errors to Sentry. Request bodies, cookies, auth headers,
query strings, user details and local variables are stripped before anything leaves the server
(`backend/app/core/observability.py::scrub_event`).
