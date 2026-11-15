"""The environment templates stay complete and each one is valid for its own environment."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _values(name: str) -> dict[str, str]:
    out = {}
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*?)\s*(#.*)?$", line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


@pytest.fixture(autouse=True)
def _blank_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def _load(values: dict[str, str]) -> Settings:
    known = {k: v for k, v in values.items() if k in Settings.model_fields and v != ""}
    return Settings(_env_file=None, **known)


def test_every_setting_is_documented_in_env_example():
    documented = set(_values(".env.example"))
    missing = [n.upper() for n in Settings.model_fields if n not in documented]
    assert missing == [], f"add these to .env.example with a one-line explanation: {missing}"


@pytest.mark.parametrize("name, env", [(".env.development.example", "development"), (".env.test.example", "test")])
def test_local_templates_start_as_they_are(name, env):
    assert _load(_values(name)).app_env == env


@pytest.mark.parametrize("name", [".env.staging.example", ".env.production.example"])
def test_server_templates_are_refused_until_filled_in(name):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _load(_values(name))


@pytest.mark.parametrize("env", ["production", "staging"])
def test_server_templates_pass_once_deploy_fills_them(tmp_path, env):
    out = tmp_path / ".env"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_env.py"), "--domain", "book.example-clinic.in", "--env", env,
                    "--output", str(out)], check=True, capture_output=True)
    values: dict[str, str] = {}
    for line in out.read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*?)\s*(#.*)?$", line)
        if m:
            values[m.group(1).lower()] = m.group(2).strip()
    domain = values["domain"]
    # What compose.production.yaml derives from DOMAIN for the API container:
    values.update(frontend_url=f"https://{domain}", cors_origins=f"https://{domain}", trusted_hosts=domain,
                  forwarded_allow_ips="172.28.0.0/16", cookie_secure="true", database_url="postgresql+psycopg://app:x@postgres:5432/appointments",
                  smtp_host="smtp.example.com", smtp_from="bookings@example-clinic.in")
    assert _load(values).app_env == env
