"""Abuse and load scenarios against a running STAGING (or local) stack. Never run it against production.

    python scripts/perf/abuse_test.py --base-url http://api:8000 --forwarded-ips [--users 100 --seconds 60]

It creates its own clinic ("Abuse Test Clinic (sample)", owner abuse-owner-<random>@example.test) and checks:

  1. same-slot race     60 patients hold the same time at the same moment -> exactly one may win; 20 receptionists
                        book one time at once -> exactly one may win
  2. duplicate payments 10 identical submissions at once, the same UTR on another booking, a repeated
                        Idempotency-Key -> one payment, duplicate refused, nothing marked paid without staff
  3. one-time codes     wrong-code guessing locks the code, resend cool-down, per-IP and per-address request limits,
                        booking without a verified code is refused (needs a working email channel; see --skip-otp)
  4. load               N patients (browse, free times; a share of them hold, book, open the payment page and
                        submit a UTR) + 5 staff, for S seconds: p50/p95/p99 per step and the error rate

--forwarded-ips gives every virtual patient its own client address (X-Forwarded-For). The API believes that header
only from its trusted proxy network (FORWARDED_ALLOW_IPS), so this works only when the script runs inside that
network (as Nginx does), e.g. in a container on the stack's "public" network. Otherwise every request shares one
address and the per-IP limits (correctly) stop the race and load tests early.

Codes are never read: the test behaves like an attacker who does not receive them. Afterwards check the database
for double bookings with --database-url, or with the query printed at the end.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import random
import secrets
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
DOUBLE_BOOKING_SQL = """SELECT COUNT(*) FROM appointments a JOIN appointments b
  ON a.professional_id = b.professional_id AND a.id < b.id AND a.start_at < b.end_at AND b.start_at < a.end_at
 WHERE a.status IN ('pending_payment','pending_verification','confirmed','checked_in','in_progress')
   AND b.status IN ('pending_payment','pending_verification','confirmed','checked_in','in_progress')"""


class Client:
    """One httpx client; each call can pretend to come from a different visitor address."""

    def __init__(self, base: str, forwarded: bool, host: str | None):
        self.base = base.rstrip("/") + "/api/v1"
        self.forwarded = forwarded
        self.http = httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=400, max_keepalive_connections=200),
                                      headers={"Host": host} if host else None)
        self._ips = (str(ipaddress.IPv4Address(0x0A000000 + i)) for i in range(1, 10**7))  # 10.0.0.1, 10.0.0.2, ...

    def ip(self) -> str:
        return next(self._ips)

    async def req(self, method: str, path: str, *, ip: str | None = None, headers: dict | None = None, **kw) -> httpx.Response:
        h = dict(headers or {})
        if self.forwarded:
            h["X-Forwarded-For"] = ip or self.ip()
        return await self.http.request(method, self.base + path, headers=h, **kw)


def ok(r: httpx.Response, *codes: int) -> dict:
    if r.status_code not in (codes or (200, 201)):
        raise SystemExit(f"setup failed: {r.request.method} {r.request.url.path} -> {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


async def setup(c: Client) -> dict:
    tag = secrets.token_hex(4)
    email, password = f"abuse-owner-{tag}@example.test", "Abuse-" + secrets.token_urlsafe(12)
    tokens = ok(await c.req("POST", "/auth/register", json={"full_name": "Abuse Test Owner (sample)", "email": email, "password": password}), 201)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    org = ok(await c.req("POST", "/organizations", headers=h, json={"name": f"Abuse Test Clinic {tag} (sample)", "slug": f"abuse-test-{tag}"}), 201)
    h["X-Organization-Id"] = org["id"]

    async def post(path, body):
        return ok(await c.req("POST", path, headers=h, json=body), 200, 201)

    branch = await post("/branches", {"name": "Main (sample)", "code": "MAIN"})
    service = await post("/services", {"name": "Consultation (sample)", "duration_minutes": 15, "price_paise": 50000, "payment_mode": "full_advance"})
    pros = [await post("/professionals", {"display_name": f"Dr. Sample {i}", "default_duration_minutes": 15, "buffer_minutes": 0,
                                          "branches": [{"branch_id": branch["id"]}], "services": [{"service_id": service["id"]}]}) for i in range(1, 4)]
    for p in pros:
        ok(await c.req("PUT", "/schedules", headers=h, json={"professional_id": p["id"], "branch_id": branch["id"],
                       "windows": [{"weekday": wd, "start_time": "08:00:00", "end_time": "22:00:00"} for wd in range(7)]}))
    await post("/upi-accounts", {"display_name": "Main UPI (sample)", "upi_id": f"abuse{tag}@okhdfcbank", "merchant_name": "Abuse Test Clinic"})
    clinic = {"slug": org["slug"], "org_id": org["id"], "h": h, "branch": branch["id"], "service": service["id"], "pros": [p["id"] for p in pros]}
    await verification(c, clinic, required=False)
    return clinic


async def verification(c: Client, clinic: dict, *, required: bool) -> None:
    org = clinic["org_id"]
    values = {"enabled": True, "required_for_booking": True, "channels": ["email"], "default_channel": "email"} if required else {"required_for_booking": False}
    ok(await c.req("PUT", f"/organizations/{org}/settings/otp", headers=clinic["h"], json={"values": values}))
    ok(await c.req("PUT", f"/organizations/{org}/settings/booking", headers=clinic["h"], json={"values": {"require_mobile_verification": required}}))


def pub(clinic: dict) -> str:
    return f"/public/organizations/{clinic['slug']}"


async def free_slots(c: Client, clinic: dict, day: date) -> list[tuple[str, str]]:
    r = await c.req("GET", f"{pub(clinic)}/availability", params={"service_id": clinic["service"], "branch_id": clinic["branch"], "date": day.isoformat()})
    return [(p["professional_id"], s["start_at"]) for p in (r.json().get("professionals", []) if r.status_code == 200 else []) for s in p["slots"]]


def hold_body(clinic, pro, start, key):
    return {"professional_id": pro, "branch_id": clinic["branch"], "service_id": clinic["service"], "start_at": start, "session_key": key}


async def book(c: Client, clinic: dict, pro: str, start: str, *, ip: str | None = None, n: int = 0) -> httpx.Response | None:
    ip = ip or c.ip()
    key = "abuse-" + secrets.token_hex(8)
    hold = await c.req("POST", f"{pub(clinic)}/holds", ip=ip, json=hold_body(clinic, pro, start, key))
    if hold.status_code != 201:
        return hold
    return await c.req("POST", f"{pub(clinic)}/appointments", ip=ip, json={
        "hold_id": hold.json()["id"], "session_key": key, "customer": {"full_name": f"Sample Patient {n}", "mobile": f"9{random.randint(100000000, 999999999)}"}})


# ------------------------------------------------------------------------------------------------------------- 1. race
async def race(c: Client, clinic: dict) -> dict:
    day = date.today() + timedelta(days=20)
    slots = await free_slots(c, clinic, day)
    pro, start = slots[0]
    holds = await asyncio.gather(*[c.req("POST", f"{pub(clinic)}/holds", json=hold_body(clinic, pro, start, f"race-{i}")) for i in range(60)])
    hold_codes = Counter(r.status_code for r in holds)
    pro2, start2 = slots[5]
    staff = await asyncio.gather(*[c.req("POST", "/appointments", headers=clinic["h"], json={
        "professional_id": pro2, "branch_id": clinic["branch"], "service_id": clinic["service"], "start_at": start2, "source": "reception",
        "confirm_without_payment": True, "customer": {"full_name": f"Walk In {i} (sample)", "mobile": f"98000{i:05d}"}}) for i in range(20)])
    staff_codes = Counter(r.status_code for r in staff)
    return {"public holds on one time (60 at once)": dict(hold_codes), "receptionists booking one time (20 at once)": dict(staff_codes),
            "passed": hold_codes.get(201) == 1 and staff_codes.get(201) == 1 and sum(hold_codes.values()) == 60
            and set(hold_codes) <= {201, 409} and set(staff_codes) <= {201, 409}}


# -------------------------------------------------------------------------------------------------- 2. duplicate payments
async def payments(c: Client, clinic: dict) -> dict:
    day = date.today() + timedelta(days=21)
    slots = await free_slots(c, clinic, day)
    appts = []
    for i in range(3):
        r = await book(c, clinic, *slots[i * 3], n=900 + i)
        appts.append(ok(r, 201))

    def submit(a, utr, key=None, ip=None):
        return c.req("POST", f"{pub(clinic)}/appointments/{a['reference']}/payment/submit", ip=ip, params={"access_token": a["access_token"]},
                     data={"utr": utr}, headers={"Idempotency-Key": key} if key else None)

    utr = f"5{random.randint(10**10, 10**11 - 1)}"
    same = await asyncio.gather(*[submit(appts[0], utr) for _ in range(10)])
    same_codes = Counter(r.status_code for r in same)
    other = await submit(appts[1], utr)
    key, ip, utr3 = secrets.token_hex(12), c.ip(), f"6{random.randint(10**10, 10**11 - 1)}"
    first = await submit(appts[2], utr3, key, ip)  # a phone retrying the same request (timeout, double tap)
    again = await submit(appts[2], utr3, key, ip)
    changed = await submit(appts[2], f"6{random.randint(10**10, 10**11 - 1)}", key, ip)  # same key, different content
    listed = ok(await c.req("GET", "/payments", headers=clinic["h"], params={"page_size": 100}))
    rows = listed.get("data", listed if isinstance(listed, list) else [])
    by_utr = Counter(p.get("latest_utr") for p in rows if p.get("latest_utr"))
    statuses = Counter(p.get("status") for p in rows)
    status_of = {a["reference"]: ok(await c.req("GET", f"{pub(clinic)}/appointments/{a['reference']}", params={"access_token": a["access_token"]}))["status"]
                 for a in appts}
    return {"same UTR sent 10 times at once": dict(same_codes), "same UTR on another booking": f"{other.status_code} {other.json().get('code', '')}",
            "same Idempotency-Key and content twice": f"{first.status_code} / {again.status_code} (same answer: {first.text == again.text})",
            "same Idempotency-Key, different content": f"{changed.status_code} {changed.json().get('code', '')}",
            "payments per UTR": dict(by_utr), "payment statuses": dict(statuses),
            "appointment statuses (nobody verified yet)": status_of,
            "passed": by_utr.get(utr) == 1 and other.status_code == 409 and first.status_code == again.status_code == 200 and first.text == again.text
            and changed.status_code == 422 and "paid" not in statuses and "verified" not in statuses
            and all(s != "confirmed" for s in status_of.values())}


# --------------------------------------------------------------------------------------------------- 3. one-time codes
def label(r: httpx.Response) -> str:
    code = r.json().get("code") if r.headers.get("content-type", "").startswith("application/json") else None
    return f"{r.status_code}:{code or ('sent' if r.status_code == 200 else 'rate_limited')}"


async def otp(c: Client, clinic: dict) -> dict:
    await verification(c, clinic, required=True)
    day = date.today() + timedelta(days=22)
    slots = await free_slots(c, clinic, day)
    out: dict = {}
    ip, key = c.ip(), "otp-" + secrets.token_hex(6)
    hold = ok(await c.req("POST", f"{pub(clinic)}/holds", ip=ip, json=hold_body(clinic, *slots[0], key)), 201)
    email = f"patient-{secrets.token_hex(3)}@example.test"
    start = await c.req("POST", f"{pub(clinic)}/verification/start", ip=ip, json={"channel": "email", "destination": email, "hold_id": hold["id"], "session_key": key})
    out["start (send a code)"] = start.status_code
    if start.status_code != 200:
        out["note"] = f"could not send a code ({start.json().get('code')}): configure an email channel or use --skip-otp"
        await verification(c, clinic, required=False)
        out["passed"] = False
        return out
    ch = start.json()["challenge_id"]
    guesses = []
    for i in range(8):  # an attacker guessing; max_attempts is 5 by default
        r = await c.req("POST", f"{pub(clinic)}/verification/{ch}/verify", ip=ip, json={"code": f"{secrets.randbelow(10**6):06d}", "session_key": key})
        guesses.append(f"{r.status_code}:{r.json().get('code', 'ok')}")
    out["8 wrong guesses"] = guesses
    resend = await c.req("POST", f"{pub(clinic)}/verification/{ch}/resend", ip=ip, json={"session_key": key})
    out["resend at once"] = f"{resend.status_code} {resend.json().get('code', '')}"
    book_r = await c.req("POST", f"{pub(clinic)}/appointments", ip=ip, json={"hold_id": hold["id"], "session_key": key,
                                                                            "customer": {"full_name": "No Code (sample)", "email": email}})
    out["book without a verified code"] = f"{book_r.status_code} {book_r.json().get('code', '')}"
    spam_ip = c.ip()  # one address asking for many codes (5 per minute allowed)
    spam = []
    for i in range(8):
        k = f"spam-{i}-" + secrets.token_hex(4)
        h = await c.req("POST", f"{pub(clinic)}/holds", ip=spam_ip, json=hold_body(clinic, *slots[2 + i], k))
        if h.status_code != 201:
            spam.append(f"hold {h.status_code}")
            continue
        r = await c.req("POST", f"{pub(clinic)}/verification/start", ip=spam_ip, json={"channel": "email", "destination": f"spam{i}@example.test", "hold_id": h.json()["id"], "session_key": k})
        spam.append(label(r))
    out["one address asks for 8 codes"] = spam
    victim = f"victim-{secrets.token_hex(3)}@example.test"  # many addresses flooding one person's inbox
    flood = []
    for i in range(12):
        k, vip = f"flood-{i}-" + secrets.token_hex(4), c.ip()
        h = await c.req("POST", f"{pub(clinic)}/holds", ip=vip, json=hold_body(clinic, *slots[12 + i], k))
        if h.status_code != 201:
            flood.append(f"hold {h.status_code}")
            continue
        r = await c.req("POST", f"{pub(clinic)}/verification/start", ip=vip, json={"channel": "email", "destination": victim, "hold_id": h.json()["id"], "session_key": k})
        flood.append(label(r))
    out["12 addresses send codes to one victim"] = flood
    await verification(c, clinic, required=False)
    locked = any("locked" in g or "too_many" in g or g.startswith("429") for g in guesses[5:])
    out["passed"] = (all(not g.startswith("200") for g in guesses) and locked and resend.status_code == 429 and book_r.status_code in (400, 403, 422)
                     and any(s.startswith("429") for s in spam) and any(s.startswith("429") for s in flood))
    return out


# --------------------------------------------------------------------------------------------------------------- 4. load
def pct(values, p):
    v = sorted(values)
    return round(v[min(len(v) - 1, round(p / 100 * (len(v) - 1)))]) if v else 0


async def load(c: Client, clinic: dict, users: int, seconds: int, think: float, book_share: float, seed: int | None = None) -> dict:
    times: dict[str, list[float]] = defaultdict(list)
    errors: Counter = Counter()
    rnd = random.Random(seed)  # a fresh seed per run: UTRs and phone numbers never repeat between runs
    deadline = time.monotonic() + seconds

    async def timed(name, coro):
        t0 = time.perf_counter()
        try:
            r = await coro
        except httpx.HTTPError as exc:
            errors[f"{name}: {type(exc).__name__}"] += 1
            return None
        times[name].append((time.perf_counter() - t0) * 1000)
        for one in (r if isinstance(r, list) else [r]):
            if one.status_code >= 400 and one.status_code != 409:  # 409 = somebody else took that time: correct
                code = one.json().get("code", "") if one.headers.get("content-type", "").startswith("application/json") else ""
                errors[f"{name}: {one.status_code} {code}"] += 1
        return r

    async def nap():
        await asyncio.sleep(rnd.uniform(0.5 * think, 1.5 * think))

    async def patient(n):
        ip = c.ip()
        while time.monotonic() < deadline:
            await timed("clinic page", c.req("GET", pub(clinic), ip=ip))
            await nap()
            await timed("services + doctors", asyncio.gather(c.req("GET", f"{pub(clinic)}/services", ip=ip), c.req("GET", f"{pub(clinic)}/professionals", ip=ip)))
            await nap()
            day = date.today() + timedelta(days=rnd.randint(1, 30))
            r = await timed("free times", c.req("GET", f"{pub(clinic)}/availability", ip=ip, params={"service_id": clinic["service"], "branch_id": clinic["branch"], "date": day.isoformat()}))
            slots = [(p["professional_id"], s["start_at"]) for p in (r.json().get("professionals", []) if r is not None and r.status_code == 200 else []) for s in p["slots"]]
            if not slots or rnd.random() >= book_share:  # most visitors look around without booking
                continue
            await nap()
            pro, start = rnd.choice(slots)
            key = f"load-{n}-{secrets.token_hex(4)}"
            h = await timed("hold a time", c.req("POST", f"{pub(clinic)}/holds", ip=ip, json=hold_body(clinic, pro, start, key)))
            if h is None or h.status_code != 201:
                continue
            await nap()
            a = await timed("book", c.req("POST", f"{pub(clinic)}/appointments", ip=ip, json={
                "hold_id": h.json()["id"], "session_key": key, "customer": {"full_name": f"Sample Patient {n}", "mobile": f"9{rnd.randint(100000000, 999999999)}"}}))
            if a is None or a.status_code != 201:
                continue
            a = a.json()
            await timed("payment page", c.req("GET", f"{pub(clinic)}/appointments/{a['reference']}/payment", ip=ip, params={"access_token": a["access_token"]}))
            await nap()
            await timed("submit UTR", c.req("POST", f"{pub(clinic)}/appointments/{a['reference']}/payment/submit", ip=ip,
                                            params={"access_token": a["access_token"]}, data={"utr": f"7{rnd.randint(10**10, 10**11 - 1)}"}))

    async def staff():
        while time.monotonic() < deadline:
            day = datetime.combine(date.today() + timedelta(days=rnd.randint(0, 30)), datetime.min.time(), tzinfo=IST)
            await timed("staff: day's appointments", c.req("GET", "/appointments", headers=clinic["h"], params={"from_at": day.isoformat(), "to_at": (day + timedelta(days=1)).isoformat()}))
            await timed("staff: payments to verify", c.req("GET", "/payments", headers=clinic["h"], params={"status": "submitted,under_review", "page_size": 50}))
            await timed("staff: dashboard", c.req("GET", "/analytics/dashboard", headers=clinic["h"]))
            await nap()

    t0 = time.monotonic()
    await asyncio.gather(*[patient(i) for i in range(users)], *[staff() for _ in range(5)])
    elapsed = time.monotonic() - t0
    total = sum(len(v) for v in times.values())
    return {"users": users, "think_seconds": think, "book_share": book_share, "seconds": round(elapsed), "requests": total, "requests_per_second": round(total / elapsed, 1),
            "errors": dict(errors), "error_rate_percent": round(100 * sum(errors.values()) / max(total, 1), 2),
            "latency_ms": {k: {"p50": pct(v, 50), "p95": pct(v, 95), "p99": pct(v, 99), "n": len(v), "mean": round(statistics.mean(v))} for k, v in sorted(times.items())}}


async def main_async(args) -> int:
    c = Client(args.base_url, args.forwarded_ips, args.host)
    meta = (await c.req("GET", "/meta/")).json()
    if meta.get("environment") not in ("development", "test", "staging"):
        print(f"Refused: this API reports environment {meta.get('environment')!r}. Abuse tests run on staging or local stacks only.")
        return 2
    clinic = await setup(c)
    report = {"environment": meta.get("environment"), "clinic": clinic["slug"]}
    print(f"clinic {clinic['slug']} ready", file=sys.stderr)
    if not args.load_only:
        report["1. same-slot race"] = await race(c, clinic)
        print("race done", file=sys.stderr)
        report["2. duplicate payments"] = await payments(c, clinic)
        print("payments done", file=sys.stderr)
    if not args.skip_otp and not args.load_only:
        report["3. one-time codes"] = await otp(c, clinic)
        print("otp done", file=sys.stderr)
    if args.users:
        report["4. load"] = await load(c, clinic, args.users, args.seconds, args.think, args.book_share, args.seed)
    report["double-booking check (run on the database)"] = " ".join(DOUBLE_BOOKING_SQL.split())
    print(json.dumps(report, indent=2))
    await c.http.aclose()
    return 0 if all(v.get("passed", True) for v in report.values() if isinstance(v, dict)) else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://api:8000")
    p.add_argument("--host", help="Host header to send (e.g. api when calling the container by IP)")
    p.add_argument("--forwarded-ips", action="store_true", help="a different client address per virtual patient (see above)")
    p.add_argument("--users", type=int, default=100, help="virtual patients for the load test (0 = skip it)")
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--think", type=float, default=1.0, help="average seconds a patient pauses between clicks")
    p.add_argument("--book-share", type=float, default=0.3, help="share of visits that go on to book (1 = every visit: a stress test)")
    p.add_argument("--seed", type=int, help="repeat an earlier run exactly (default: a new random run)")
    p.add_argument("--skip-otp", action="store_true")
    p.add_argument("--load-only", action="store_true", help="skip scenarios 1-3")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
