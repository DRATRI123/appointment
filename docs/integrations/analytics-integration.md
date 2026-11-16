# Analytics and monitoring

## Built in (no setup)

Admin → **Website analytics**: page views, Book clicks, booking page views, booking starts (time held), completed
bookings and the difference (abandoned), by day, page and campaign source. No cookies, no visitor identifiers; Do Not
Track / Global Privacy Control are honoured.

## Google Analytics 4 / Google Tag Manager (clinic, optional)

Admin → Integrations → **Google Analytics 4 / Tag Manager**: measurement ID (`G-…`) and/or container ID (`GTM-…`) →
Save → Test (checks the format; GA4 cannot be checked from the server, so the status is "Active").

* Visitors of the clinic's public pages see a small banner; nothing loads until they press **Allow**. Do Not Track /
  Global Privacy Control visitors never see it. Advertising storage stays denied (Consent Mode v2).
* Events: `page_view`, `booking_start`, `booking_complete`, `booking_abandoned`, with the clinic and the campaign source.
* Page addresses are cleaned: no query strings (access tokens, campaign values) and no booking reference.
* Never sent: names, numbers, emails, notes or the service booked.
* Never loaded on staff screens.

## Server monitoring (platform)

* **Sentry**: Super admin → Integrations → Error tracking (or `SENTRY_DSN`). Personal data is removed before sending.
  Takes effect after the API and worker restart.
* **Prometheus**: `/metrics` with `METRICS_TOKEN`; alert rules in `deployment/monitoring/alerts.yml` cover API errors,
  failing background jobs (including the integration sync job) and messages piling up. Integration failures themselves
  are shown in Admin → Integrations (recent errors, failed records). Grafana can read the same Prometheus.
* **System health**: Super admin → System health (worker, jobs, backups).
