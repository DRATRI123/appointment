# Environment configuration

The app runs in one of four environments. Each has its own template, its own secrets and its own checks. The API
reads its settings when it starts and **refuses to run** with anything unsafe for its environment, listing every
problem at once. It never quietly falls back to a weaker setting.

| Environment | Where | Template | Copy to | Database |
|---|---|---|---|---|
| `development` | your Windows PC (`START-APP.bat`) | `.env.development.example` | `backend\.env` (done for you) | SQLite file |
| `test` | automated tests, CI, `compose.test.yaml` | `.env.test.example` | used directly | throw-away SQLite or PostgreSQL |
| `staging` | a test server on its own domain | `.env.staging.example` | `.env` on that server | its own PostgreSQL |
| `production` | the real server (e.g. a Hostinger VPS) | `.env.production.example` | `.env` on that server | PostgreSQL |

`.env.example` lists **every** setting with a one-line explanation and tags: `[all]`, `[server]` (staging and
production), `[docker]` (Docker Compose only), `[dev]` (development only). A test (`test_env_templates.py`) fails if
a setting exists in the code but not in `.env.example`.

## Rules that keep environments apart

* **Real `.env` files are never committed.** `.gitignore` ignores `.env` and `.env.*`; only the five `*.example`
  templates are tracked. Gitleaks scans every commit in CI.
* **Servers get their own random secrets.** `deployment/scripts/deploy.sh` (via `scripts/generate_env.py`) creates the
  server `.env` with fresh values. Staging never reuses production secrets.
* **Local runs read only `backend/.env`.** Docker on a server reads the root `.env`. So a production file copied to the
  server's root can never leak into a laptop run, and a laptop's file never reaches a server.
* **deploy.sh refuses example values:** empty or placeholder secrets, `example.com` domains, `DEBUG=true`, console
  message providers, `OTP_TEST_CODE`, and any `APP_ENV` other than `staging` / `production`.
* **On screen:** development, test and staging show a coloured badge in the header ("Development", "Test",
  "Staging · test data only"). Production shows none.

## What the API checks at start

### development
* Real SMS, email or WhatsApp providers are refused unless `DEV_ALLOW_REAL_MESSAGES=true` (on purpose only).
* A database on another machine is refused unless `DEV_ALLOW_REMOTE_DATABASE=true` (never a production database).
  `localhost`, `127.0.0.1` and single-word Docker names such as `postgres` count as local.

### test
* Every message provider must be `console` (nothing can reach a real person).
* The database must be local or a Docker container. There is no override.

### staging and production (servers)
* `SECRET_KEY` random, at least 32 characters. `DATA_ENCRYPTION_KEY` base64 of exactly 32 bytes. Each
  `DATA_ENCRYPTION_PREVIOUS_KEYS` entry valid. `OTP_PEPPER` at least 16 characters.
* `COOKIE_SECURE=true`, `DEBUG=false`, `CORS_ORIGINS` and `FORWARDED_ALLOW_IPS` not `*`.
* `EMAIL_PROVIDER`, `SMS_PROVIDER` and `WHATSAPP_PROVIDER` must not be `console` (use a real provider, or `disabled`).
* **A chosen provider must have its account details:**
  * `smtp` needs `SMTP_HOST` and `SMTP_FROM`;
  * `msg91` needs `MSG91_AUTH_KEY`;
  * `twilio` needs the SID, token and sender;
  * `meta` needs the WhatsApp token and phone number id.

  `OTP_PROVIDER=notifications` needs at least one enabled channel.
* `OTP_TEST_CODE` must be empty. `PLATFORM_ADMIN_REQUIRE_MFA` must be `true`.
* `METRICS_TOKEN`, if set, at least 24 characters. `S3_BUCKET` required when `STORAGE_BACKEND=s3`.

### production only (in addition)
* `TRUSTED_HOSTS` must name the real domains. `FRONTEND_URL` and every `CORS_ORIGINS` entry must be `https://`.
* `OTP_PROVIDER` must not be `console`. `RATE_LIMIT_ENABLED=true`. `WEBHOOK_ALLOW_PRIVATE_TARGETS` off.
* `BACKUP_ENCRYPTION_KEY` must be base64 of 32 bytes (backups hold patient data).

Unknown provider names (for example `OTP_PROVIDER=msg91`, which is not an OTP provider) are refused in every
environment, instead of failing on the first sign-in.

## Settings Docker Compose reads itself (server `.env`)

| Setting | Meaning |
|---|---|
| `COMPOSE_FILE=compose.yaml:compose.production.yaml` | plain `docker compose ps/logs/run` always means this server's stack |
| `COMPOSE_PROJECT_NAME` | `appointment` (production) or `appointment-staging` |
| `DOMAIN`, `LETSENCRYPT_EMAIL` | the site address and the certificate contact |
| `TAG` | the live release; written by deploy.sh and rollback.sh |
| `DOCKER_SUBNET` | the internal network; the API trusts forwarded visitor IPs only from it |
| `API_MEMORY`, `API_CPUS`, `WEB_MEMORY`, `WORKER_MEMORY`, `POSTGRES_MEMORY`, ... | container limits (defaults suit 2 vCPU / 8 GB) |

See also: [production-deployment.md](production-deployment.md), [security.md](security.md),
[encryption.md](encryption.md).
