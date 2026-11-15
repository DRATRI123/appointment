"""Create the server .env for Docker Compose from a template, with fresh random secrets.

    python scripts/generate_env.py --domain book.yourclinic.in [--env production|staging] [--letsencrypt-email you@x.in]

Production uses .env.production.example, staging .env.staging.example (separate secrets; never reuse production's).

Standard library only, so it runs on a fresh server. Refuses to overwrite an existing .env (that would make
encrypted notes and backups unreadable). Afterwards, copy DATA_ENCRYPTION_KEY and BACKUP_ENCRYPTION_KEY into your
password manager: they are the only way to read clinical notes and backups.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATORS = {
    "SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "DATA_ENCRYPTION_KEY": lambda: base64.b64encode(os.urandom(32)).decode(),
    "OTP_PEPPER": lambda: secrets.token_urlsafe(32),
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(24),  # hex: safe inside the database URL
    "BACKUP_ENCRYPTION_KEY": lambda: base64.b64encode(os.urandom(32)).decode(),
    "METRICS_TOKEN": lambda: secrets.token_urlsafe(32),
}
DOMAIN_RE = re.compile(r"^(localhost|([a-z0-9-]+\.)+[a-z]{2,})$")


def render(template: str, values: dict[str, str]) -> str:
    out = []
    for line in template.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m and m.group(1) in values:
            comment = ""
            if "#" in m.group(2):
                comment = "  " + m.group(2)[m.group(2).index("#"):]
            line = f"{m.group(1)}={values[m.group(1)]}{comment}"
        out.append(line)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", required=True, help="the address patients will use, e.g. book.sunriseclinic.in")
    parser.add_argument("--env", choices=["production", "staging"], default="production", help="which template to fill")
    parser.add_argument("--email-from", help="sender address for email (SMTP_FROM)")
    parser.add_argument("--letsencrypt-email", help="address for HTTPS certificate notices (LETSENCRYPT_EMAIL)")
    parser.add_argument("--output", type=Path, default=ROOT / ".env")
    parser.add_argument("--force", action="store_true", help="overwrite an existing file (old encrypted data becomes unreadable!)")
    args = parser.parse_args(argv)

    domain = args.domain.strip().lower().removeprefix("https://").rstrip("/")
    if not DOMAIN_RE.match(domain):
        print(f"error: {args.domain!r} is not a domain name like clinic.example.com", file=sys.stderr)
        return 2
    if args.output.exists() and not args.force:
        print(f"error: {args.output} already exists. Keep it (it holds your encryption keys) or pass --force.", file=sys.stderr)
        return 1
    values = {name: make() for name, make in GENERATORS.items()}
    values["DOMAIN"] = domain
    if args.email_from:
        values["SMTP_FROM"] = args.email_from
    if args.letsencrypt_email:
        values["LETSENCRYPT_EMAIL"] = args.letsencrypt_email
    text = render((ROOT / f".env.{args.env}.example").read_text(encoding="utf-8"), values)
    args.output.write_text(text, encoding="utf-8")
    try:
        os.chmod(args.output, 0o600)
    except OSError:  # pragma: no cover - Windows
        pass
    print(f"Wrote {args.output} ({args.env}) for https://{domain}")
    print("Now: 1) save DATA_ENCRYPTION_KEY and BACKUP_ENCRYPTION_KEY in your password manager,")
    print("     2) fill in the SMS / email provider settings, 3) docker compose up -d --build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
