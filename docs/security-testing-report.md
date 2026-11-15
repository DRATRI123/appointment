# Security and load testing report (15 November 2026)

What was tested, how, the measured results, what was fixed, and what risk remains. All tests ran on a local machine
(4 CPU cores) against the production stack (`compose.production.yaml`, `APP_ENV=staging`, Nginx with a self-signed
certificate, PostgreSQL 17.12, Redis 7.4). The clinic, patients and payments were sample data created by the tests.
**No real patient data and no production credentials were used. Nothing was deployed.**

This report does not claim the application is unhackable. It records what these tests could and could not find.

## 1. Tools and results

| Tool | Scope | Result |
|---|---|---|
| Bandit 1.9 | backend code (20,095 lines) | 0 issues after review (1 false positive, a metric label, annotated) |
| pip-audit 2.10 | `requirements.lock`, exactly what the image installs | no known vulnerabilities |
| npm audit | all website dependencies | 0 vulnerabilities |
| Semgrep 1.185, project rules (`.semgrep/rules.yml`, 13 rules) | 441 files: backend, website, scripts | 0 open findings; 3 reviewed SQL lines that use constants or a strictly validated name. The rules caught all 8 kinds of mistakes planted in a test file |
| Semgrep public rulesets (OWASP Top 10, ...) | | **not run here** (the rule registry was unreachable from the test machine); runs in CI, report-only until the first results are reviewed |
| Gitleaks 8.28 | working tree + all 31 commits | no real secret. Hits were test fixtures (allow-listed) and 5 example values in old documentation commits: a booking token and a session key from a local test run, which unlock nothing. Those are recorded in `.gitleaksignore` and replaced in the current files |
| Trivy 0.67, images | our API/website images | **no HIGH/CRITICAL** in Python or npm packages |
| Trivy 0.67, third-party images | PostgreSQL, Redis, Nginx, certbot | the original pins were a year old with many fixable issues. **Updated** (§3); remaining items in §5 |
| Trivy 0.67, config | 3 Dockerfiles | no MEDIUM/HIGH/CRITICAL misconfiguration |
| OWASP ZAP 2.16 baseline (passive) | https site through Nginx | **0 failures, 54 passed, 4 warnings** (§5) |
| ShellCheck 0.11 | 8 deployment scripts + Nginx entry scripts | clean |
| Backend test suite | SQLite and, in Docker, PostgreSQL 17 | all pass (SQLite: everything; PostgreSQL in Docker: 351 passed, 2 skipped) |
| Website tests | unit (Vitest) and browser end to end (Playwright, Chromium) | 63 unit tests and 32 browser tests pass, including CSP and accessibility checks |

## 2. Abuse and load scenarios (`scripts/perf/abuse_test.py`)

The test runs inside the Docker network, as Nginx does, so each virtual patient has its own client address.

### Same-slot race

| Attempt | Result |
|---|---|
| 60 patients hold the same time at the same moment | **1 succeeded, 59 refused** ("already taken") |
| 20 receptionists book the same time at once | **1 succeeded, 19 refused** |
| Database check after all runs (1,181 appointments) | **0 overlapping active appointments** |

### Duplicate payments

| Attempt | Result |
|---|---|
| The same UTR submitted 10 times at once for one booking | 1 accepted, 9 refused; **one payment** recorded |
| The same UTR on another booking of the same clinic | refused (`duplicate_utr`) |
| The same request twice with one `Idempotency-Key` (a phone retrying) | identical answer twice; nothing done twice |
| The same key with different content | refused (`idempotency_key_reused`) |
| Anything marked paid without staff | **no**: payments stay "submitted" and bookings "pending verification" until staff verify |

### One-time codes (attacker who never receives the code)

| Attempt | Result |
|---|---|
| Guessing the code | locked after 5 attempts; further guesses refused |
| Asking for a new code at once | refused (cool-down) |
| Booking without a verified code | refused (`contact_not_verified`) |
| One address asks for 8 codes in a minute | 5 sent, then refused |
| 12 different addresses flood one person's inbox | 5 sent, then refused (`otp_destination_limit`) |

### 100 simultaneous users

API: 2 processes limited to 1.5 CPU cores (the default for a 2 vCPU VPS); PostgreSQL limited to 1.5 cores.

| Run | Requests | Errors | Throughput |
|---|---|---|---|
| Realistic: 2 s between clicks, 30% of visits book | 6,024 in 102 s | **0** | 59 requests/s |
| Stress: 1 s between clicks, every visit books | 2,941 in 72 s | **0** | 41 requests/s |

Latency in the realistic run (milliseconds):

| Step | p50 | p95 | p99 |
|---|---|---|---|
| clinic page | 58 | 271 | 382 |
| services + doctors | 69 | 317 | 571 |
| free times | 293 | 725 | 888 |
| hold a time | 500 | 2,231 | 2,902 |
| book | 841 | 1,851 | 2,845 |
| payment page | 290 | 706 | 885 |
| submit UTR | 572 | 1,612 | 1,920 |
| staff: day's appointments | 227 | 788 | 1,051 |
| staff: payments to verify | 287 | 803 | 922 |
| staff: dashboard | 468 | 1,202 | 1,745 |

Resources during the realistic run:

| Service | CPU (median / peak) | Memory peak |
|---|---|---|
| API | 150% / 157% (at its 1.5-core limit) | 451 MiB |
| PostgreSQL | 36% / 65% | 273 MiB |
| worker | 0% / 51% | 158 MiB |
| website | 0% / 25% | 101 MiB |
| Redis | 0.5% / 4% | 7 MiB |

On an idle stack the same steps take 26 ms (free times), 34 ms (hold) and 67 ms (book). So the higher numbers
under load are time spent **queueing for the API's CPU**, plus holds briefly locking the doctor's diary, which is
what prevents double booking. Even the "realistic" run created bookings at about 14,000 per hour on one clinic with
3 doctors. In the stress run (every visit books), hold and book reached a p95 of 12-13 s with still no errors. These
numbers are for this machine and these limits. Measure again on the real server before drawing conclusions. More
API CPU (`API_CPUS`, `WEB_CONCURRENCY`) is the first lever if real traffic ever approaches this.

## 3. Fixed during this work

* Image pins updated to current patch releases:
  * PostgreSQL 17.6 → 17.12;
  * Redis 7.4.6 → 7.4.12;
  * Nginx 1.28.0 → 1.30.6, now its own image with Alpine updates applied;
  * certbot 4.2 → 5.10;
  * Node 22.21 → 22.23.5;
  * Prometheus 3.5 → 3.15.1.

  The upgrade was rehearsed over existing data.
* Servers now refuse a message provider without its account details, which would otherwise fail every message
  silently.
* Uvicorn's access log is off in server images: query strings can contain patient search terms. Nginx logs paths only.
* Website analytics used the server's date instead of the clinic's: bookings made between midnight and 05:30 IST were
  missing from that day's report.
* Example tokens in the API documentation replaced with obvious placeholders.
* `seed_demo --help` used to run the seed; now it only prints help.
* Found by the browser test suite (all 32 tests now pass):
  * The environment badge called `/meta/`, which the website proxy redirected to the API's own address. That address
    is blocked by the CSP, so a request hung and admin pages never finished loading. The API now answers both forms.
  * Dashboard, reports and website analytics worked out "the last 30 days" from the browser's clock, and the website
    analytics page from UTC. Between midnight and 05:30 India time, the newest bookings and payments were left out.
    All three now use the clinic's time zone.
  * CI's browser-test job would have been stopped by the new super admin two-step requirement. It now uses the same
    development setting as `.env.development.example`; servers still always require it.

## 4. How to repeat

* On every push, `.github/workflows/security.yml` runs Semgrep, Gitleaks over all history, and Trivy (our images,
  third-party images, Dockerfiles). It runs again every Monday.
* Weekly and on demand, a `zap` job deploys a throw-away staging stack with `deploy.sh`, then runs the ZAP baseline
  and the abuse tests.
* By hand, on staging only (the script refuses any API that reports production):

```bash
docker run --rm --network appointment-staging_public -v "$PWD/scripts/perf:/perf:ro" appointment-api:$(grep ^TAG= .env | cut -d= -f2) \
  python /perf/abuse_test.py --base-url http://api:8000 --forwarded-ips --users 100 --seconds 90 --think 2
```

## 5. Remaining risks (accepted or open)

| Risk | Why it remains | What limits it / next step |
|---|---|---|
| **The same UTR at two different clinics** is accepted at each | Duplicate checks are per clinic; a cross-clinic check would tell one clinic about another's payments | Staff must confirm the credit in their own bank before anything is paid. Possible improvement: a privacy-preserving platform-wide flag ("seen elsewhere", without saying where) |
| CSP allows images from any HTTPS host, and inline styles (ZAP warnings) | Clinics show logos and photos hosted anywhere; the UI uses inline styles | Scripts stay locked to per-request nonces with `strict-dynamic`, the main defence against injected code |
| Third-party images: PostgreSQL's `gosu` helper is built with an old Go; certbot has a few old Python libraries | Upstream images; fixes arrive with their next releases | `gosu` never runs (the container starts as the postgres user). certbot talks only to Let's Encrypt. CI reports both weekly; update the pins |
| Semgrep public rulesets not yet reviewed | Registry unreachable during this work | CI runs them report-only; review the first run, then make them blocking |
| `setup-server.sh` not run on a real Ubuntu 24.04 server | No server yet | ShellCheck-clean and idempotent; run it on a fresh VPS and read its output |
| Let's Encrypt issuance not exercised (only the self-signed path) | Needs a public domain | deploy.sh gives a clear error and is safe to rerun; staging first |
| ZAP was a passive baseline, not an active attack scan | Active scans need an isolated staging server and time | Run `zap-full-scan.py` against staging (never production) before launch |
| No independent penetration test or legal review | Out of scope for automated tools | Commission both before claiming DPDP Act 2023 or healthcare compliance |
| Load numbers come from a 4-core laptop-class machine | No server yet | Repeat on the real VPS; compare against these numbers |
