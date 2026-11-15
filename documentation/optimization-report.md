# Performance, security and encryption review (November 2026)

The brief asked for a faster, more secure, encrypted and scalable application. It also said to inspect first, change
only what is needed, and claim nothing without test evidence. This report follows that order: what already existed,
what was measured, what changed, and the proof.

Environment: SQLite, one machine with 4 CPU cores, Python 3.13. The load generator, the Next.js server and the API
shared those 4 cores, so the figures are conservative. Nothing was deployed.

## 1. Architecture audit: what already existed

| Area | Already in place (unchanged) | Gap found → done in this review |
|---|---|---|
| HTTPS | Settings come from environment variables only. Production refuses to start with insecure values (non-HTTPS `FRONTEND_URL`/CORS, insecure cookies, `*` hosts, a `*` proxy list). HSTS is sent when cookies are secure. `X-Forwarded-For` is honoured only from `FORWARDED_ALLOW_IPS`. | — |
| Frontend | Charts and the calendar are loaded on demand; API calls are deduplicated by React Query; there is a nonce-based CSP. | zod was loaded on **every** page → now only on the 3 forms that use it |
| Backend | Email, SMS and WhatsApp go through an outbox and are sent by the worker (a booking never waits for them); slow queries are logged; N+1 queries were fixed in an earlier phase. | **SQLite stall at 100 users** (below); CPU-heavy public catalogue → short cache |
| SQLite | WAL mode, `busy_timeout=30000`, `synchronous=NORMAL`, foreign keys on, writers serialised with `BEGIN IMMEDIATE`, partial unique indexes against double booking. | Reads no longer take the write lock; the write lock is held only inside the endpoint |
| PostgreSQL | A migration tool with checksums, the full test suite and parallel race tests on PostgreSQL. | — |
| Concurrency | Holds with expiry, unique constraints, row locks, race tests (exactly one winner). | **Idempotency keys** |
| Encryption | AES-256-GCM fields, Argon2id passwords, hashed OTPs/refresh tokens/API keys, encrypted backups. | **Key ids and rotation**; SQLCipher reviewed (§9) |
| Security | Roles and permissions, tenant isolation, CSRF, CSP, rate limits, SSRF guard on webhooks, upload sniffing, lockout, audit log. | **Administrator MFA** |
| Shopify | Link, Liquid button and allow-listed iframe. URL parameters are hints only; prices and identity always come from the server. | — |
| Monitoring | Liveness `/api/v1/health`, readiness `/api/v1/health/ready`, Prometheus `/metrics`, worker heartbeat, Sentry hook, backup verification. | — |
| Windows | PowerShell scripts and README steps. | `.env.development`, `.env.production.example`, a many-users section |

## 2. Performance bottleneck report

**The main finding.** With 100 simultaneous users the API on SQLite **stopped**. Requests waited 30 s and failed
with `database is locked` (78% errors) while the CPU sat at 4%: waiting, not working. The cause was a deadlock
between two limits:

1. Every request, including plain reads, took SQLite's single write lock (`BEGIN IMMEDIATE`).
2. FastAPI runs each sync dependency, the endpoint and the response validation in separate worker threads (40 per
   process). A request held the write lock while waiting for its next thread. Once all 40 threads were busy waiting
   for that lock, the holder could never get a thread, and nothing moved until SQLite gave up after 30 s.

`tests/test_sqlite_lock_starvation.py` reproduces it: it fails on the old code ("database is locked" after 34 s) and
passes on the new.

Smaller findings:
* The public clinic, doctors and services lists cost 7–14 ms of CPU each and every visitor asks for them.
* Several API processes help, because one Python process uses about one core.
* An in-process waiting line for SQLite writers was tried and **rejected**: it measured about 4× slower.

## 3. Security vulnerability report

No exploitable vulnerability was found in the reviewed areas (authentication, tenant isolation, OTP, payments,
public booking, Shopify links, uploads, webhooks). The gaps against the brief were:

* **No administrator MFA.** Added (authenticator app with backup codes; a clinic can require it).
* **No idempotency on bookings or payment submissions.** Added. Double booking was already impossible; a retry now
  returns the first answer instead of an error.
* **One encryption key with no id**, so rotation meant a stop-the-world migration. Added key ids, a ring of previous
  keys and a rotation command.
* **Decryption returned plain text for any value without the `enc:` prefix.** This was needed for legacy rows. It is
  still accepted on read, but the rotation command now encrypts such values, and an unknown key or a modified value
  is a hard error.

## 4. HTTPS readiness report

* **Development:** plain HTTP on `localhost:3000` and `127.0.0.1:8000`, with insecure cookies allowed
  (`.env.development`).
* **Production** (`backend/.env.production.example`): `COOKIE_SECURE=true` (which also adds HSTS), `FRONTEND_URL`
  and `CORS_ORIGINS` must be `https://`, `TRUSTED_HOSTS` is required, and `FORWARDED_ALLOW_IPS` must list the reverse
  proxy. The API refuses to start and lists every violation (verified: the template without secrets is rejected).
* **TLS** 1.2/1.3 is terminated by the reverse proxy of your choice. A Caddy example is in `infrastructure/docker`.
* **No mixed content:** the browser only talks to the Next.js origin, which proxies `/api` server-side.
  `NEXT_PUBLIC_API_URL` stays empty.
* **Shopify links** are built from `booking_url`, which must start with `https://`.

## 5. Frontend optimization report

Measured with Playwright: public pages on a Pixel 7 profile with 4× CPU slowdown, admin pages on desktop.
"Page JS" is the JavaScript fetched before the page's load event; route prefetches are excluded.

| Page | Page JS before | After | Compressed before → after |
|---|---|---|---|
| Public website / booking / my bookings | 864 KB | **760 KB** | 259 → **229 KB** |
| Admin dashboard | 1,178 KB | **1,074 KB** | 355 → **326 KB** |
| Admin appointments / payments / reports | 861 / 829 / 784 KB | **758 / 726 / 680 KB** | −30 KB each |

The change: zod (form validation) was imported for every page by the root providers and by
`instrumentation-client.ts`. It is now imported only by the sign-in, sign-up and onboarding forms, through
`lib/zod-config.ts`, which still turns on its CSP-safe mode first; the CSP audit in the e2e suite confirms this.

Load timings on localhost were already low (largest content: 0.4–0.8 s on the slowed phone, 0.1–0.4 s on desktop)
and stayed within noise. No duplicate API requests were found on any measured page. Nothing else was changed
without a measured reason.

## 6. Backend optimization report

| Change | Why (measured) | Files |
|---|---|---|
| Read requests use deferred transactions (no write lock); write requests read without the lock in their dependencies and take it when the endpoint starts | The 30 s stall at 100 users | `app/core/database.py` |
| Each sync endpoint commits in its own thread before the response is built | The holder must never wait for a thread; a commit error now becomes the request's error response | `app/main.py` (`commit_in_handler`) |
| GET endpoints that write (access audits, exports) are marked and get a write session; any other write in a read request is logged | Correctness of the read path | `writes_on_read` in 5 routers |
| Public clinic, doctors and services lists cached for 5 s per process, emptied at once by catalogue changes in that process | 7–14 ms CPU each on every visit | `app/core/public_cache.py`, `PUBLIC_CACHE_SECONDS` |
| `WORKER_THREADS` setting (8 measured best for one process; the default 40 for several) | Python lock contention in a single process | `app/main.py`, `.env.development` |
| Enough pooled SQLite connections for every worker thread | No waiting for a connection while holding one | `build_engine` |

Notifications were already in the background: after each load test the outbox held the messages for the worker
(e.g. 292 waiting), and no booking waited for them.

## 7. SQLite optimization report

* WAL, `busy_timeout`, `synchronous=NORMAL` and foreign keys were already on, and stay on.
* **New:** read-only requests never take the write lock (WAL readers run in parallel), and the write lock is held
  only for the endpoint's own work. The WAL file measured 4.7 MB after a full 100-user run, so checkpoints keep up.
* Double booking: unique indexes, writer serialisation and holds. Every load-test run checked the database afterwards:
  **0 overlapping active appointments**.
* Limits, honestly: SQLite has **one writer at a time**. At a heavy 13 writes per second (100 users clicking every
  2 s) writes queue to a p95 of about 0.6–0.8 s with 4 processes. For more write traffic or several servers, move
  to PostgreSQL (§8).
* Backups use SQLite's online backup API, are encrypted, and the restore was tested (§16).

## 8. PostgreSQL migration strategy

Already built and tested; nothing was migrated automatically.

* **Data:** `python -m app.ops.migrate_data` copies SQLite to PostgreSQL with row counts and checksums
  (documentation/database.md).
* **Proof:** the whole test suite passes on PostgreSQL (**310 passed** in this review), including the parallel race
  tests that prove exactly one winner per slot under real concurrency.
* **Compatibility:** the same Alembic migrations run on both. Times are stored as UTC with time zone. The partial
  unique indexes exist on both. On PostgreSQL, row locks (`SELECT … FOR UPDATE`) replace SQLite's writer
  serialisation.
* **Rollback:** keep the SQLite file and an encrypted backup. Switching back is `DATABASE_URL` plus a restart.
  Every migration has a downgrade (both new ones were tested up and down).

## 9. Encryption architecture

| Data | Protection |
|---|---|
| In transit | TLS 1.2/1.3 at the reverse proxy; HSTS; secure cookies |
| Clinical notes, integration/provider credentials, webhook secrets, MFA secrets, stored idempotent responses | AES-256-GCM: random 96-bit nonce per value, key id bound as associated data, `enc:v2:<kid>:…` |
| Passwords | Argon2id (never reversible) |
| One-time codes, refresh tokens, API keys, MFA backup codes | Keyed hashes (HMAC/SHA-256), never plain text |
| Backups | AES-256-GCM in 1 MiB chunks with `BACKUP_ENCRYPTION_KEY`, kept off the server |
| Uploaded documents | Private storage, content-sniffed types, `no-store` downloads, audit-logged |
| Keys | Environment variables, separate from the database file; `DATA_ENCRYPTION_PREVIOUS_KEYS` plus `python -m app.ops.rotate_keys` |
| Whole database file | SQLCipher reviewed and **not adopted** (fragile native driver, not applicable to PostgreSQL). Use BitLocker on Windows and encrypted volumes or LUKS on servers. Details: security.md |

## 10. Load-testing report

Tool: `scripts/perf/load_test.py` (async httpx; Locust/k6 were not needed, and this script also checks the database
for double bookings afterwards).

* **Data:** an isolated, freshly copied SQLite database for every run: 3 clinics, 9,000 patients, 69,201
  appointments, 41,567 payments.
* **Patient journey:** booking page HTML → clinic → doctors → services → free times → hold → one-time code (console
  mock provider) → verify → book → UPI payment page → UTR submission → status page.
* **Staff:** day list, verification queue, patient search, dashboard, and **verifying submitted payments**.
* **No real side effects:** no real message or payment. Each virtual user has its own client address (through the
  trusted local proxy), so rate limits stayed **on**.

## 11. Before-and-after benchmarks (100 simultaneous users)

| Setup | Requests in ~100 s | Errors | "database is locked" | Double bookings |
|---|---|---|---|---|
| **Before**, 1 process, a click every 2 s | 494 | **77.5%** | 332 | 0 |
| **After**, 1 process (8 threads), a click every 2 s | 4,268 | **0%** | 0 | 0 |
| **After**, 4 processes, a click every 2 s | **8,513** | **0%** | 0 | 0 |
| **Before**, 1 process, a click every 5 s | 3,835 | 0% | 0 | 0 |
| **After**, 1 process (8 threads), a click every 5 s | 3,872 | 0% | 0 | 0 |
| **After**, 4 processes, a click every 5 s | 3,890 | 0% | 0 | 0 |

p95 in milliseconds, after, 4 processes:

| Action | Click every 5 s | Click every 2 s |
|---|---|---|
| Booking page HTML | 41 | 144 |
| Clinic | 20 | 158 |
| Doctors | 30 | 127 |
| Free times | 72 | 201 |
| Hold | 91 | 665 |
| Send code | 48 | 654 |
| Verify code | 43 | 772 |
| Book | 95 | 566 |
| Submit UTR | 84 | 785 |
| Status | 39 | 102 |
| Staff verifies payment | 99 | 791 |
| Dashboard | 446 | 2,385 |

At a click every 5 s, every target in performance.md is met. At a click every 2 s (about 81 requests per second),
three targets are missed:
* the staff dashboard: p95 2.4 s against 1.5 s;
* hold: 665 ms against 500 ms;
* verify code: 772 ms against 500 ms.

All other targets are met. The two write misses come from SQLite's single writer. CPU averaged 54% at 5 s
and 154% at 2 s (of 400% available); peak memory was 0.7–0.9 GB for 4 processes.

## 12. Exact changed files

Backend:
* Core and wiring: `app/core/database.py`, `app/main.py`, `app/core/config.py`, `app/core/exceptions.py`,
  `app/core/public_cache.py` (new), `app/api/deps.py`.
* Routers: `app/api/v1/{auth,appointments,public,customers,integrations,platform,reports}.py`.
* Models and schemas: `app/models/{auth,__init__}.py`, `app/models/idempotency.py` (new),
  `app/schemas/{auth,user}.py`.
* Security: `app/security/crypto.py`, `app/security/totp.py` (new).
* Services: `app/services/{auth_service,organization_service}.py`, `app/services/mfa_service.py` (new),
  `app/services/idempotency.py` (new), `app/services/otp/otp_generator.py`.
* Workers and operations: `app/workers/jobs.py`, `app/ops/rotate_keys.py` (new).
* Env templates: `.env.development` and `.env.production.example` (new).

Frontend:
* Pages: `app/(auth)/{login/login-form,register/page,onboarding/page}.tsx`, `app/providers.tsx`,
  `app/admin/settings/page.tsx`, `app/customer/profile/page.tsx`.
* Components: `components/auth/two-step-card.tsx` (new), `components/public-booking/booking-flow.tsx`.
* Library and services: `lib/{api-client,zod-config}.ts`, `services/{auth,booking,payments}.ts`,
  `types/{api,auth}.ts`; `instrumentation-client.ts` removed.
* Env templates: `.env.development`, `.env.example` and `.env.production.example`, now committed (no secrets).

Tests:
* Backend: `test_sqlite_lock_starvation.py`, `test_idempotency.py`, `test_mfa.py`, `test_key_rotation.py`,
  `test_public_cache.py`, plus updates to `conftest.py`, `test_models.py` and `test_production_config.py`.
* Frontend: `e2e/mfa.spec.ts`.

Tooling and docs: `scripts/perf/load_test.py` (`--full-flow`, `--otp-code`, CPU/RAM sampling, queue backlog),
`scripts/dev-*.ps1|sh`, `README.md`, `documentation/security.md`, this report.

## 13. Database migrations

* `f2fcbd0ec3d6` adds the `idempotency_keys` table: a unique key per clinic, operation and caller, plus an expiry
  index.
* `5ab13cfee58d` adds `users.mfa_secret`, `mfa_enabled_at`, `mfa_last_step` and `mfa_recovery_hashes`.

Both are additive (no data rewritten) and were tested upgrade → downgrade → upgrade on SQLite. The PostgreSQL suite
builds the schema from them. Apply with `alembic upgrade head` (or `python -m app.ops.setup`).

## 14. Windows local setup

See README → *Run locally on Windows 10*: Python venv, `pip install -r requirements.txt`,
`Copy-Item .env.development .env`, `alembic upgrade head`, seed, `uvicorn … --reload`, then `npm install` and
`npm run dev` (`frontend/.env.development` loads automatically). The new section *Many users on one Windows PC*
covers running with `--workers 4`, the background worker, and `npm run build; npm run start`.

## 15. Future deployment preparation

Provider-neutral. Copy `backend/.env.production.example` and `frontend/.env.production.example`, fill the secrets
(the API lists anything missing), and put any TLS reverse proxy in front. Run one API process per core, plus the
worker. Use PostgreSQL for more than one server or heavy write traffic. The Docker stack in `infrastructure/docker`
is one option; documentation/deployment.md covers it and running without Docker.

## 16. Backup and recovery (tested in this review)

On a copy of the development database:
1. `python -m app.ops.backup create` wrote an encrypted archive (`APBACKUP` header) and verified it.
2. `verify` reported schema `5ab13cfee58d` and the row counts.
3. All appointments were deleted to simulate loss (171 → 0).
4. `restore <file> --yes` brought back all 171.
5. `python -m app.ops.rotate_keys` then re-encrypted the 11 old-format secrets with the current key, and a second
   dry run reported nothing left.

Keep `BACKUP_ENCRYPTION_KEY` and `DATA_ENCRYPTION_KEY` off the server: without them, a backup cannot be read.

## Test evidence

| Suite | Result |
|---|---|
| Backend on SQLite | 298 passed (7 PostgreSQL-only skipped) |
| Backend on PostgreSQL | 310 passed |
| Frontend unit (Vitest) | 61 passed; TypeScript and ESLint clean |
| Browser end-to-end (Playwright, incl. CSP and accessibility audits) | 30 passed, plus the new MFA flow test (passed after fixing a selector in the test itself); 1 platform-admin test skipped, as before: it needs admin credentials |
| Load tests | Above |
