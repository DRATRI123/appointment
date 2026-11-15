"""Load test against a running API seeded with scripts/perf/seed_volume.py.

    python scripts/perf/load_test.py --base-url http://127.0.0.1:8000 --users 50 --seconds 60 \\
        [--database-url postgresql+psycopg://...]   # also checks there are no double bookings afterwards

Each virtual user loops: patients browse a clinic page, search availability and book (hold, then confirm);
staff open the day's appointments, the payment verification queue, a patient search and the dashboard.
Prints p50/p95/p99 per action and checks them against the targets in docs/performance.md.
Run the API with RATE_LIMIT_ENABLED=false: every virtual user shares one IP address.

--full-flow runs the complete public journey instead, with rate limits left ON (each virtual user gets its own
client address through X-Forwarded-For, which the API accepts only from a trusted proxy such as 127.0.0.1):
booking page (with --web-url), clinic, doctors, services, free times, hold, one-time code through the console
(mock) provider, verify, book, UPI payment page, UTR submission, status page; staff also verify submitted payments.
It needs APP_ENV=development. The mock code is read from /api/v1/dev/outbox, which lives in one API process's
memory; with several API processes start the API with OTP_TEST_CODE=123456 and pass --otp-code 123456 (the API
refuses that setting outside development and test). No real message or payment is ever sent.

    python scripts/perf/load_test.py --full-flow --users 100 --seconds 90 --think 2 \
        --base-url http://127.0.0.1:8000 --web-url http://localhost:3000 --api-pid <uvicorn pid> \
        --database-url sqlite:///path/to/perf.db
"""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
PASSWORD = "PerfTest-2026!"
# p95 targets in milliseconds (docs/performance.md)
TARGETS = {"clinic page": 300, "availability": 300, "book (hold+confirm)": 800, "staff: day's appointments": 500,
           "staff: verification queue": 500, "staff: patient search": 500, "staff: dashboard": 1500}
FULL_FLOW_TARGETS = {"booking page (HTML)": 800, "clinic page": 300, "doctors": 300, "services": 300, "availability": 300, "hold slot": 500,
                     "otp send": 800, "otp verify": 500, "create booking": 800, "payment page": 500, "payment submit": 800,
                     "status page": 300, "staff: verify payment": 800, "staff: day's appointments": 500, "staff: verification queue": 500,
                     "staff: patient search": 500, "staff: dashboard": 1500}
OTP_CODE: str | None = None  # --otp-code: the API's OTP_TEST_CODE, so several API processes can be tested
EXPECTED = {409}  # someone else took the slot first: correct behaviour, not an error


class Stats:
    def __init__(self) -> None:
        self.times: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, list[str]] = defaultdict(list)
        self.expected: dict[str, int] = defaultdict(int)

    def record(self, name: str, ms: float, status: int, detail: str = "") -> None:
        self.times[name].append(ms)
        if status in EXPECTED:
            self.expected[name] += 1
        elif status >= 400:
            self.errors[name].append(f"{status} {detail[:80]}")


class _Failed:
    status_code = 599
    text = ""

    def json(self):
        return {}


async def timed(stats: Stats, name: str, coro):
    started = time.perf_counter()
    try:
        r = await coro
    except httpx.TransportError as exc:  # a dropped connection is an error to report, not a reason to stop the test
        stats.record(name, (time.perf_counter() - started) * 1000, 599, f"connection: {type(exc).__name__}")
        return _Failed()
    stats.record(name, (time.perf_counter() - started) * 1000, r.status_code, r.text if r.status_code >= 400 else "")
    return r


async def setup(client: httpx.AsyncClient, base: str, orgs: int) -> list[dict]:
    clinics = []
    for o in range(1, orgs + 1):
        r = await client.post(f"{base}/api/v1/auth/login", json={"email": f"owner{o}@perf.example.com", "password": PASSWORD})
        r.raise_for_status()
        token = r.json()["access_token"]
        me = (await client.get(f"{base}/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})).json()
        org = me["memberships"][0]["organization"]
        public = (await client.get(f"{base}/api/v1/public/organizations/{org['slug']}")).json()
        services = (await client.get(f"{base}/api/v1/public/organizations/{org['slug']}/services")).json()
        clinics.append({"slug": org["slug"], "headers": {"Authorization": f"Bearer {token}", "X-Organization-Id": org["id"]},
                        "services": [s["id"] for s in services], "branches": [b["id"] for b in public["branches"]]})
    return clinics


async def pause(rnd, think: float) -> None:
    if think:
        await asyncio.sleep(rnd.uniform(0.5 * think, 1.5 * think))  # a person reading the page before the next click


async def patient(client, base, clinic, stats, rnd, deadline, n, think=0.0):
    while time.monotonic() < deadline:
        await pause(rnd, think)
        slug = clinic["slug"]
        await timed(stats, "clinic page", client.get(f"{base}/api/v1/public/organizations/{slug}"))
        await pause(rnd, think)
        day = date.today() + timedelta(days=rnd.randint(1, 14))
        params = {"service_id": rnd.choice(clinic["services"]), "branch_id": rnd.choice(clinic["branches"]), "date": day.isoformat()}
        r = await timed(stats, "availability", client.get(f"{base}/api/v1/public/organizations/{slug}/availability", params=params))
        slots = [(p["professional_id"], s["start_at"]) for p in (r.json().get("professionals", []) if r.status_code == 200 else []) for s in p["slots"]]
        if slots and rnd.random() < 0.3:
            await pause(rnd, think)
            pro, start = rnd.choice(slots)
            key = f"lt{n}-{rnd.random()}"
            t0 = time.perf_counter()
            try:
                hold = await client.post(f"{base}/api/v1/public/organizations/{slug}/holds", json={**params, "professional_id": pro, "start_at": start, "session_key": key})
            except httpx.TransportError as exc:
                stats.record("book (hold+confirm)", (time.perf_counter() - t0) * 1000, 599, f"connection: {type(exc).__name__}")
                continue
            if hold.status_code == 201:
                book = await client.post(f"{base}/api/v1/public/organizations/{slug}/appointments", json={
                    "hold_id": hold.json()["id"], "session_key": key, "customer": {"full_name": f"Load Test {n}", "mobile": f"9{rnd.randint(100000000, 999999999)}"}})
                stats.record("book (hold+confirm)", (time.perf_counter() - t0) * 1000, book.status_code, book.text if book.status_code >= 400 else "")
            else:
                stats.record("book (hold+confirm)", (time.perf_counter() - t0) * 1000, hold.status_code, hold.text if hold.status_code >= 400 else "")


async def patient_full(client, base, web, clinic, stats, rnd, deadline, n, think=0.0):
    """The complete public journey. Each virtual user has its own client address, as real patients do."""
    h = {"X-Forwarded-For": f"10.{n // 250 % 250}.{n % 250}.{rnd.randint(1, 250)}"}
    slug = clinic["slug"]
    pub = f"{base}/api/v1/public/organizations/{slug}"
    while time.monotonic() < deadline:
        await pause(rnd, think)
        if web:
            await timed(stats, "booking page (HTML)", client.get(f"{web}/{slug}/book", headers=h))
        await timed(stats, "clinic page", client.get(pub, headers=h))
        await timed(stats, "doctors", client.get(f"{pub}/professionals", headers=h))
        await timed(stats, "services", client.get(f"{pub}/services", headers=h))
        await pause(rnd, think)
        day = date.today() + timedelta(days=rnd.randint(1, 14))
        params = {"service_id": rnd.choice(clinic["services"]), "branch_id": rnd.choice(clinic["branches"]), "date": day.isoformat()}
        r = await timed(stats, "availability", client.get(f"{pub}/availability", params=params, headers=h))
        slots = [(p["professional_id"], s["start_at"]) for p in (r.json().get("professionals", []) if r.status_code == 200 else []) for s in p["slots"]]
        if not slots or rnd.random() >= 0.3:
            continue
        await pause(rnd, think)
        pro, start = rnd.choice(slots)
        key = f"lt{n}-{rnd.random()}"
        mobile = f"9{rnd.randint(100000000, 999999999)}"
        hold = await timed(stats, "hold slot", client.post(f"{pub}/holds", headers=h, json={**params, "professional_id": pro, "start_at": start, "session_key": key}))
        if hold.status_code != 201:
            continue
        hold_id = hold.json()["id"]
        await pause(rnd, think)
        sent = await timed(stats, "otp send", client.post(f"{pub}/verification/start", headers=h,
                                                          json={"channel": "sms", "destination": mobile, "hold_id": hold_id, "session_key": key}))
        if sent.status_code != 200:
            continue
        code = OTP_CODE or (await client.get(f"{base}/api/v1/dev/outbox/latest-code", params={"destination": f"+91{mobile}"})).json().get("code")
        await pause(rnd, think)
        ok = await timed(stats, "otp verify", client.post(f"{pub}/verification/{sent.json()['challenge_id']}/verify", headers=h,
                                                          json={"code": code, "session_key": key}))
        if ok.status_code != 200:
            continue
        book = await timed(stats, "create booking", client.post(f"{pub}/appointments", headers=h, json={
            "hold_id": hold_id, "session_key": key, "verification_token": ok.json()["verification_token"],
            "customer": {"full_name": f"Load Test {n}", "mobile": f"+91{mobile}"}}))
        if book.status_code != 201:
            continue
        ref, token = book.json()["reference"], book.json()["access_token"]
        if book.json().get("advance_due_paise"):
            await pause(rnd, think)
            pay = await timed(stats, "payment page", client.get(f"{pub}/appointments/{ref}/payment", params={"access_token": token}, headers=h))
            if pay.status_code == 200 and pay.json():
                await pause(rnd, think)
                await timed(stats, "payment submit", client.post(f"{pub}/appointments/{ref}/payment/submit", params={"access_token": token}, headers=h,
                                                                 data={"utr": str(rnd.randint(10**11, 10**12 - 1))}))
        await timed(stats, "status page", client.get(f"{pub}/appointments/{ref}", params={"access_token": token}, headers=h))


async def staff_full(client, base, clinic, stats, rnd, deadline, think=0.0):
    """Staff work their lists and approve submitted payments (simulated bank check)."""
    h = clinic["headers"]
    while time.monotonic() < deadline:
        if rnd.random() < 0.3:
            await pause(rnd, think)
            q = await timed(stats, "staff: verification queue", client.get(f"{base}/api/v1/payments", headers=h, params={"status": "submitted", "page_size": 20}))
            rows = q.json().get("data", []) if q.status_code == 200 else []
            if rows:
                p = rnd.choice(rows)
                await timed(stats, "staff: verify payment", client.post(f"{base}/api/v1/admin/payments/{p['id']}/verify", headers=h,
                                                                        json={"bank_credit_confirmed": True, "verified_amount_paise": p["amount_paise"],
                                                                              "notes": "load test"}))
        else:
            await staff(client, base, clinic, stats, rnd, min(deadline, time.monotonic() + 0.01), think)


class Sampler:
    """CPU and memory of the API process, once a second (psutil if installed, else /proc on Linux)."""

    def __init__(self, pids: list[int] | None) -> None:
        self.pids, self.cpu, self.rss = pids or [], [], []

    async def run(self, deadline: float) -> None:
        if not self.pids:
            return
        try:
            import psutil

            procs = [psutil.Process(p) for p in self.pids]
            for proc in procs:
                proc.cpu_percent(None)
            while time.monotonic() < deadline:
                await asyncio.sleep(1)
                self.cpu.append(sum(p.cpu_percent(None) for p in procs))
                self.rss.append(sum(p.memory_info().rss for p in procs) / 2**20)
        except ImportError:
            import os

            tick = os.sysconf("SC_CLK_TCK")

            def read():
                cpu = rss = 0.0
                for pid in self.pids:
                    with open(f"/proc/{pid}/stat") as f:
                        parts = f.read().rsplit(")", 1)[1].split()
                    cpu += int(parts[11]) + int(parts[12])
                    rss += int(parts[21]) * os.sysconf("SC_PAGE_SIZE") / 2**20
                return cpu, rss

            last_cpu, _ = read()
            last_t = time.monotonic()
            while time.monotonic() < deadline:
                await asyncio.sleep(1)
                cpu, rss = read()
                now = time.monotonic()
                self.cpu.append((cpu - last_cpu) / tick / (now - last_t) * 100)
                self.rss.append(rss)
                last_cpu, last_t = cpu, now


async def staff(client, base, clinic, stats, rnd, deadline, think=0.0):
    h = clinic["headers"]
    while time.monotonic() < deadline:
        await pause(rnd, think)
        day = datetime.combine(date.today() + timedelta(days=rnd.randint(-30, 14)), datetime.min.time(), tzinfo=IST)
        action = rnd.random()
        if action < 0.5:
            await timed(stats, "staff: day's appointments", client.get(f"{base}/api/v1/appointments", headers=h,
                                                                       params={"from_at": day.isoformat(), "to_at": (day + timedelta(days=1)).isoformat()}))
        elif action < 0.7:
            await timed(stats, "staff: verification queue", client.get(f"{base}/api/v1/payments", headers=h, params={"status": "submitted,under_review", "page_size": 50}))
        elif action < 0.9:
            await timed(stats, "staff: patient search", client.get(f"{base}/api/v1/customers", headers=h, params={"search": f"{rnd.randint(1, 3999)}", "page_size": 25}))
        else:
            await timed(stats, "staff: dashboard", client.get(f"{base}/api/v1/analytics/dashboard", headers=h))


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, round(p / 100 * (len(values) - 1)))]


def double_bookings(database_url: str) -> int:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.connect() as conn:  # any two active appointments of one professional that overlap in time
        n = conn.execute(text("""
            SELECT COUNT(*) FROM appointments a JOIN appointments b
              ON a.professional_id = b.professional_id AND a.id < b.id
             AND a.start_at < b.end_at AND b.start_at < a.end_at
             WHERE a.status IN ('pending_payment','pending_verification','confirmed','checked_in','in_progress')
               AND b.status IN ('pending_payment','pending_verification','confirmed','checked_in','in_progress')""")).scalar()
    engine.dispose()
    return int(n)


def queue_backlog(database_url: str) -> tuple[int, float]:
    """Notifications waiting for the worker, and the age in seconds of the oldest one."""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.connect() as conn:
        n, oldest = conn.execute(text("SELECT COUNT(*), MIN(created_at) FROM notifications WHERE status = 'pending'")).one()
    engine.dispose()
    if not n or not oldest:
        return 0, 0.0
    oldest = datetime.fromisoformat(str(oldest)) if not isinstance(oldest, datetime) else oldest
    if oldest.tzinfo is None:
        from datetime import UTC
        oldest = oldest.replace(tzinfo=UTC)
    return int(n), (datetime.now(oldest.tzinfo) - oldest).total_seconds()


async def run(args) -> int:
    global OTP_CODE
    OTP_CODE = args.otp_code
    rnd = random.Random(args.seed)
    stats = Stats()
    targets = FULL_FLOW_TARGETS if args.full_flow else TARGETS
    sampler = Sampler(args.api_pid)
    limits = httpx.Limits(max_connections=args.users + 10, max_keepalive_connections=args.users + 10)
    # Patients have no session cookies (anonymous public booking); staff authenticate with bearer tokens only.
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        clinics = await setup(client, args.base_url, args.orgs)
        client.cookies.clear()
        deadline = time.monotonic() + args.seconds
        started = time.monotonic()
        tasks = []
        for n in range(args.users):
            clinic = clinics[n % len(clinics)]
            r = random.Random(rnd.random())
            if n % 5 == 4:  # one in five virtual users is staff
                tasks.append((staff_full if args.full_flow else staff)(client, args.base_url, clinic, stats, r, deadline, args.think))
            elif args.full_flow:
                tasks.append(patient_full(client, args.base_url, args.web_url, clinic, stats, r, deadline, n, args.think))
            else:
                tasks.append(patient(client, args.base_url, clinic, stats, r, deadline, n, args.think))
        await asyncio.gather(sampler.run(deadline), *tasks)
        elapsed = time.monotonic() - started
    total = sum(len(v) for v in stats.times.values())
    print(f"\n{args.users} users (think time {args.think:g}s) for {elapsed:.0f}s: {total:,} requests ({total / elapsed:.0f}/s)\n")
    print(f"{'action':30} {'count':>7} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'max ms':>8} {'target':>8} {'errors':>7} {'409':>5}")
    failed = False
    for name in targets:
        v = stats.times.get(name, [])
        p95 = pct(v, 95)
        ok = bool(v) and p95 <= targets[name] and not stats.errors.get(name)
        failed |= not ok
        print(f"{name:30} {len(v):>7} {statistics.median(v) if v else 0:>8.0f} {p95:>8.0f} {pct(v, 99):>8.0f} {max(v) if v else 0:>8.0f} "
              f"{targets[name]:>8} {len(stats.errors.get(name, [])):>7} {stats.expected.get(name, 0):>5}  {'ok' if ok else 'MISSED'}")
    for name, errs in stats.errors.items():
        print(f"  errors in {name}: {errs[:3]}")
    all_errors = [e for errs in stats.errors.values() for e in errs]
    print(f"\nError rate: {len(all_errors) / max(total, 1) * 100:.2f}% ({len(all_errors)} of {total:,});"
          f" database-locked errors: {sum('locked' in e.lower() for e in all_errors)}")
    if sampler.cpu:
        print(f"API processes CPU: average {statistics.mean(sampler.cpu):.0f}%, peak {max(sampler.cpu):.0f}% (100% = one core);"
              f" memory: peak {max(sampler.rss):.0f} MiB")
    if args.database_url:
        overlaps = double_bookings(args.database_url)
        print(f"\nDouble bookings in the database after the run: {overlaps}")
        failed |= overlaps > 0
        waiting, age = queue_backlog(args.database_url)
        print(f"Notifications waiting for the worker: {waiting} (oldest {age:.0f}s)")
    print("\nAll targets met." if not failed else "\nSome targets were missed (see above).")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--orgs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--think", type=float, default=2.0, help="average seconds a user pauses between clicks (0 = flat out, for capacity)")
    parser.add_argument("--database-url", help="also count overlapping active appointments after the run")
    parser.add_argument("--full-flow", action="store_true", help="complete public journey with mock OTP and payment submission (see above)")
    parser.add_argument("--web-url", help="with --full-flow, also load the Next.js booking page, e.g. http://localhost:3000")
    parser.add_argument("--api-pid", type=int, nargs="*", help="sample CPU and memory of these processes (the uvicorn API and its workers)")
    parser.add_argument("--otp-code", help="the API's OTP_TEST_CODE (development only); needed with more than one API process")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
