# Performance

## Targets

95% of requests (p95) must finish within these times, with no errors and no double bookings:

| Action | p95 target |
|---|---|
| Clinic page | 300 ms |
| Availability for a day | 300 ms |
| Booking (reserve slot + confirm) | 800 ms |
| Staff: day's appointments, payment verification queue, patient search | 500 ms |
| Staff: dashboard | 1,500 ms |

## Results

Measured on 14 Nov 2026 with `scripts/perf/load_test.py` against the API (2 worker processes, pinned to 2 CPU
cores to approximate the recommended 2 vCPU server) and PostgreSQL 16 on the same machine, filled by
`scripts/perf/seed_volume.py` with 5 clinics, 20,000 patients, 115,000 appointments, 69,000 payments,
231,000 notifications and 222,000 status-history rows (a busy year plus two months ahead).

Simultaneous users, each pausing about 2 seconds between clicks (patients browse, search availability and book;
one in five users is staff):

| Users | Requests/s | Clinic page p95 | Availability p95 | Booking p95 | Staff lists p95 | Dashboard p95 | Errors | Double bookings | Result |
|---|---|---|---|---|---|---|---|---|---|
| 100 | 46 | 57 ms | 124 ms | 435 ms | 96–156 ms | 469 ms | 0 | 0 | all targets met |
| 150 | 70 | 71 ms | 161 ms | 439 ms | 127–164 ms | 566 ms | 0 | 0 | all targets met |
| 200 | 82 | 511 ms | 823 ms | 2,781 ms | 978–1,180 ms | 2,254 ms | 0 | 0 | over capacity: slower, never wrong |

Capacity (no pauses, as fast as possible): about **88 requests per second** on 2 cores. For scale: a clinic group
taking 2,000 bookings a day sees a few requests per second at its busiest hour.

What it means: one 2 vCPU server comfortably serves about 150 people using the site at the same moment. Beyond that
it slows down but stays correct: in every run, including at 200 users and flat-out, there were no failed requests
and no overlapping bookings; the only refusals were the correct "slot just taken" (409) answers when two people
chose the same time.

## What Phase 14 changed

| Problem found | Fix | Effect |
|---|---|---|
| List pages ran a query per row: SQLAlchemy keeps loaded objects only weakly, so per-row lookups re-queried | `app/core/preload.py` loads related rows once per page and keeps them for the request | 18 rows: appointments 85→13 queries, payments 135→16, patient's appointments 131→11, verification queue 72→16, notifications 59→10, refunds 45→13, waitlist 44→10, customers 29→11 (guarded by `tests/test_query_counts.py`) |
| Dashboard utilization re-read schedules, holidays and exceptions for every professional and day (579 queries) | Availability caches configuration per request | 731 ms → 262 ms, 57 queries |
| Availability queried busy time professional by professional | One query per kind of busy time for all professionals | 75 ms → 47 ms |
| One API process used one core | `WEB_CONCURRENCY` worker processes (default 2) with Prometheus multi-process metrics | capacity 45 → 88 requests/s on 2 cores |
| The response could reach the client before the database commit | Commit before responding (`scope="function"`) | no more "Hold not found" right after creating a hold; never "created" for data whose commit failed |
| Idle connections closed by the API while the proxy reused them | API keep-alive 75 s, Caddy 60 s | no connection resets under load |
| Revenue-by-date and first-visit queries scanned a clinic's whole history | Indexes `ix_payments_org_verified` and `ix_appointments_org_customer_start` (built `CONCURRENTLY`) | 5.4 ms → 0.05 ms; 13.6 ms → 8.3 ms (index-only) |

Database time is small at these volumes (the most expensive query averages 3.5 ms); the API's Python CPU time is
what limits throughput, which is why the next step for more capacity is more cores.

## Scaling further

1. **More cores**: set `WEB_CONCURRENCY` to the number of cores (in `.env`) on a bigger server.
2. **Database**: keep `WEB_CONCURRENCY × (DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW)` below PostgreSQL's
   `max_connections` (100 by default), or put PgBouncer in front. Give PostgreSQL about a quarter of the RAM as
   `shared_buffers` on a dedicated database server.
3. **Find slow spots in production**: queries over `DATABASE_SLOW_QUERY_MS` (500 ms) are logged as
   `db.slow_query` with their SQL text (never their parameters). For a full picture enable PostgreSQL's
   `pg_stat_statements` and look at `total_exec_time`.
4. **Patient search** uses `LIKE '%…%'`, which reads all of a clinic's patients (4 ms for 4,400 patients). Above
   about 50,000 patients per clinic, add a trigram index (`CREATE EXTENSION pg_trgm`) if your host allows extensions.

## Reproduce

```bash
createdb perf && DATABASE_URL=postgresql+psycopg://.../perf alembic upgrade head      # from backend/
python ../scripts/perf/seed_volume.py --database-url postgresql+psycopg://.../perf
RATE_LIMIT_ENABLED=false DATABASE_URL=postgresql+psycopg://.../perf uvicorn app.main:app --port 8001 --workers 2
python ../scripts/perf/load_test.py --base-url http://127.0.0.1:8001 --users 150 --seconds 90 --think 2 \
    --database-url postgresql+psycopg://.../perf
```

The load test exits non-zero if a target is missed, a request fails, or any two active appointments of one
professional overlap. Rate limiting must be off for the run because every virtual user shares one IP address.
Never point either script at a real clinic's database: the seeder refuses a database that already has clinics.
