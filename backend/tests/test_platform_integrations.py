"""Super admin -> Integrations: settings from the panel or .env, secrets, tests, storage switch, providers."""
from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import select

from app.core import storage as storage_module
from app.core.config import get_settings
from app.integrations.http import set_http_client
from app.models import AuditLog, User
from app.notifications.providers import (
    BrevoEmailProvider,
    DeliveryResult,
    FallbackProvider,
    OutboundMessage,
    ProviderConfig,
    SESEmailProvider,
    SNSSMSProvider,
    TwoFactorSMSProvider,
)
from app.services import platform_config as pc
from app.services import storage_migration as sm
from tests.helpers import bearer, register

CLIENT_ID = "1234-abc.apps.googleusercontent.com"


def _root(client, db, email="root-int@example.com"):
    h = bearer(register(client, email, "Platform Root"))
    db.scalar(select(User).where(User.email == email)).is_platform_admin = True
    db.flush()
    return h


def _section(body, key):
    return next(s for s in body["sections"] if s["key"] == key)


def test_panel_values_win_over_env_and_secrets_never_come_back(client, db):
    h = _root(client, db)
    r = client.get("/api/v1/platform/integrations", headers=h)
    assert r.status_code == 200, r.text
    google = _section(r.json(), "google")
    assert google["status"] == "not_configured" and {f["source"] for f in google["fields"]} <= {"env", "default"}

    r = client.put("/api/v1/platform/integrations/google", headers=h,
                   json={"values": {"google_client_id": CLIENT_ID}, "secrets": {"google_client_secret": "GOCSPX-very-secret-value-9876"}})
    assert r.status_code == 200, r.text
    google = _section(r.json(), "google")
    fields = {f["name"]: f for f in google["fields"]}
    assert fields["google_client_id"]["source"] == "panel" and fields["google_client_id"]["value"] == CLIENT_ID
    assert fields["google_client_secret"]["hint"] == "…9876" and "value" not in fields["google_client_secret"]
    assert "very-secret" not in r.text
    assert google["status"] == "untested"  # Connected only after a real test
    # Every part of the app now uses the panel values.
    assert pc.runtime_settings().google_client_id == CLIENT_ID
    from app.security.google import get_google_verifier  # Sign in with Google reads the same value

    assert get_google_verifier() is not None
    # Stored encrypted; the audit log has names only.
    raw = db.scalar(select(__import__("app.models", fromlist=["SystemSetting"]).SystemSetting.value).where(
        __import__("app.models", fromlist=["SystemSetting"]).SystemSetting.key == pc.KEY))
    assert "very-secret" not in json.dumps(raw)
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "platform.integration_saved")).all()[-1]
    assert "very-secret" not in json.dumps(audit.after) and audit.after["secrets_changed"] == ["google_client_secret"]

    # "Use .env value" removes the panel value again.
    r = client.put("/api/v1/platform/integrations/google", headers=h, json={"clear": ["google_client_id", "google_client_secret"]})
    assert {f["source"] for f in _section(r.json(), "google")["fields"] if f["name"] != "google_calendar_redirect_uri"} <= {"env", "default"}
    assert pc.runtime_settings().google_client_id == get_settings().google_client_id


def test_only_super_admins_and_same_safety_rules_as_env(client, db):
    h = bearer(register(client, "not-root@example.com", "Normal User"))
    assert client.get("/api/v1/platform/integrations", headers=h).status_code == 403
    root = _root(client, db, "root-rules@example.com")
    # The test environment never sends real messages, whatever the panel says.
    r = client.put("/api/v1/platform/integrations/email", headers=root, json={"values": {"email_provider": "smtp", "smtp_host": "smtp.example.com"}})
    assert r.status_code == 422 and r.json()["code"] == "unsafe_setting"
    r = client.put("/api/v1/platform/integrations/email", headers=root, json={"values": {"smtp_port": "abc"}})
    assert r.status_code == 422
    r = client.put("/api/v1/platform/integrations/email", headers=root, json={"values": {"database_url": "sqlite://"}})
    assert r.status_code == 422  # only listed integration settings can be changed


def test_google_connection_test_asks_google_for_real(client, db):
    h = _root(client, db, "root-google@example.com")
    client.put("/api/v1/platform/integrations/google", headers=h, json={"values": {"google_client_id": CLIENT_ID}, "secrets": {"google_client_secret": "s3cret-value"}})
    answers = [{"error": "invalid_client"}, {"error": "invalid_grant"}]
    seen = []

    def handler(request: httpx.Request):
        seen.append(request.url.host)
        return httpx.Response(400 if answers[0]["error"] == "invalid_grant" else 401, json=answers.pop(0))

    set_http_client(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        bad = client.post("/api/v1/platform/integrations/google/test", headers=h, json={}).json()
        assert bad["ok"] is False and _section(bad["overview"], "google")["status"] == "error"
        good = client.post("/api/v1/platform/integrations/google/test", headers=h, json={}).json()
        assert good["ok"] is True and _section(good["overview"], "google")["status"] == "connected"
    finally:
        set_http_client(None)
    assert seen == ["oauth2.googleapis.com", "oauth2.googleapis.com"]
    # Changing a value after a successful test means "test again".
    r = client.put("/api/v1/platform/integrations/google", headers=h, json={"secrets": {"google_client_secret": "another-secret"}})
    assert _section(r.json(), "google")["status"] == "untested"


def test_env_export_and_write_for_development_computers(client, db, tmp_path, monkeypatch):
    h = _root(client, db, "root-env@example.com")
    client.put("/api/v1/platform/integrations/google", headers=h, json={"values": {"google_client_id": CLIENT_ID}, "secrets": {"google_client_secret": "hidden-secret-1"}})
    text = client.get("/api/v1/platform/integrations/env", headers=h).text
    assert f"GOOGLE_CLIENT_ID={CLIENT_ID}" in text and "hidden-secret-1" not in text and "GOOGLE_CLIENT_SECRET=<hidden" in text
    assert "GOOGLE_CLIENT_SECRET=hidden-secret-1" in client.get("/api/v1/platform/integrations/env?include_secrets=true", headers=h).text
    # Writing .env is only for a development computer.
    assert client.post("/api/v1/platform/integrations/env/write", headers=h).status_code == 422
    env = tmp_path / ".env"
    env.write_text("APP_ENV=development\nGOOGLE_CLIENT_ID=old\n# keep me\n")
    monkeypatch.setattr(get_settings(), "app_env", "development")
    result = pc.write_env_file(db, env)
    content = env.read_text()
    assert f"GOOGLE_CLIENT_ID={CLIENT_ID}" in content and "GOOGLE_CLIENT_ID=old" not in content and "# keep me" in content
    assert "GOOGLE_CLIENT_SECRET=hidden-secret-1" in content and (tmp_path / ".env.before-integrations").read_text().startswith("APP_ENV")
    assert "GOOGLE_CLIENT_SECRET" in result["written"]


@pytest.fixture()
def two_disks(tmp_path, monkeypatch):
    """'s3' is simulated by a second folder: the switch logic is the same for any storage."""
    def build(backend):
        return storage_module.LocalStorage(tmp_path / backend)

    monkeypatch.setattr(storage_module, "build_backend", build)
    monkeypatch.setattr(sm, "build_backend", build)
    storage_module.reset_storage()
    return tmp_path


def test_storage_switch_copies_and_checks_every_file_then_switches(client, db, two_disks, monkeypatch):
    h = _root(client, db, "root-storage@example.com")
    store = storage_module.get_storage()
    doc = store.save(scope="org/1", visibility="private", data=b"%PDF-1.4 patient report", mime_type="application/pdf")
    logo = store.save(scope="org/1", visibility="public", data=b"\x89PNG\r\n\x1a\nlogo", mime_type="image/png")
    assert (two_disks / "local" / doc.key).read_bytes() != b"%PDF-1.4 patient report"  # private files are encrypted

    # A switch needs saved and tested bucket settings.
    r = client.post("/api/v1/platform/integrations/storage/switch", headers=h, json={"target": "s3"})
    assert r.status_code == 422 and r.json()["code"] == "storage_untested"
    client.put("/api/v1/platform/integrations/storage", headers=h, json={"values": {"s3_bucket": "clinic-files", "s3_access_key_id": "AKIAEXAMPLE"},
                                                                          "secrets": {"s3_secret_access_key": "secret-key-123"}})
    from app.services import platform_tests

    monkeypatch.setattr(platform_tests, "test_bucket", lambda bucket, prefix: (True, "Connected"))
    assert client.post("/api/v1/platform/integrations/storage/test", headers=h, json={}).json()["ok"] is True

    r = client.post("/api/v1/platform/integrations/storage/switch", headers=h, json={"target": "s3"})
    assert r.status_code == 200 and r.json()["storage"]["migration"]["status"] == "queued"
    st = sm.run_pending(db)
    assert st["status"] == "done" and st["copied"] == 2 and st["total"] == 2
    assert storage_module.active_backend() == "s3"
    # Same bytes in the new place (still encrypted), readable through the app.
    assert (two_disks / "s3" / doc.key).read_bytes() == (two_disks / "local" / doc.key).read_bytes()
    assert storage_module.get_storage().open(doc.key).read() == b"%PDF-1.4 patient report"
    assert client.get(f"/media/{logo.key[len('public/'):]}").content == b"\x89PNG\r\n\x1a\nlogo"
    # A file that only exists in the old place is still found until "Finish".
    late = storage_module.LocalStorage(two_disks / "local").save(scope="org/1", visibility="public", data=b"GIF89a-late", mime_type="image/gif")
    assert storage_module.get_storage().open(late.key).read() == b"GIF89a-late"
    client.post("/api/v1/platform/integrations/storage/finish", headers=h)
    with pytest.raises(FileNotFoundError):
        storage_module.get_storage().open(late.key)
    usage = client.get("/api/v1/platform/integrations/storage/usage", headers=h).json()
    assert usage["backend"] == "s3" and usage["private"]["files"] == 1 and usage["public"]["files"] == 1


def test_storage_switch_resumes_in_slices_and_never_switches_after_a_failed_copy(db, two_disks, monkeypatch):
    store = storage_module.get_storage()
    for i in range(3):
        store.save(scope="org/1", visibility="public", data=b"GIF89a" + bytes([i]), mime_type="image/gif")
    pc.record_test(db, "storage", True, "ok")  # pretend the bucket test passed with the current values
    monkeypatch.setattr(pc, "section_state", lambda db, key, row=None: {"status": "connected"})
    sm.request_switch(db, "s3", None)
    st = sm.run_pending(db, slice_seconds=-1)  # no time left: nothing copied yet, still running
    assert st["status"] == "running" and storage_module.active_backend() == "local"
    st = sm.run_pending(db)
    assert st["status"] == "done" and st["copied"] == 3

    # A copy that does not match the original stops the move; nothing switches back.
    sm.request_switch(db, "local", None)
    monkeypatch.setattr(sm, "write_raw", lambda backend, key, data: storage_module.write_raw(backend, key, data + b"x"))
    for f in (two_disks / "local").rglob("*.gif"):
        f.unlink()
    st = sm.run_pending(db)
    assert st["status"] == "failed" and "does not match" in st["error"] and storage_module.active_backend() == "s3"


# --------------------------------------------------------------------------------------------- providers
def _msg(**kw):
    return OutboundMessage(channel=kw.pop("channel", "email"), to=kw.pop("to", "asha@example.com"), body="Hello", subject="Hi", **kw)


def test_brevo_sends_with_the_api_key_header():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(url=str(request.url), key=request.headers["api-key"], body=json.loads(request.content))
        return httpx.Response(201, json={"messageId": "<abc@smtp-relay.brevo.com>"})

    p = BrevoEmailProvider(client=httpx.Client(transport=httpx.MockTransport(handler)),
                           config=ProviderConfig({"brevo_api_key": "xkeysib-123", "email_from": "clinic@example.com"}))
    result = p.send(_msg(reply_to="desk@example.com", html="<p>Hello</p>"))
    assert result.ok and result.message_id == "<abc@smtp-relay.brevo.com>"
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email" and seen["key"] == "xkeysib-123"
    assert seen["body"]["to"] == [{"email": "asha@example.com"}] and seen["body"]["replyTo"] == {"email": "desk@example.com"}
    bad = BrevoEmailProvider(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"message": "Key not found"}))),
                             config=ProviderConfig({"brevo_api_key": "x", "email_from": "c@example.com"})).send(_msg())
    assert not bad.ok and not bad.retryable


class _FakeAWS:
    def __init__(self, fail: Exception | None = None):
        self.calls, self.fail = [], fail

    def send_email(self, **kw):
        if self.fail:
            raise self.fail
        self.calls.append(kw)
        return {"MessageId": "ses-1"}

    def publish(self, **kw):
        self.calls.append(kw)
        return {"MessageId": "sns-1"}


AWS = {"aws_region": "ap-south-1", "aws_access_key_id": "AKIA", "aws_secret_access_key": "x", "email_from": "clinic@example.com"}


def test_amazon_ses_and_sns_including_india_dlt_attributes():
    ses = _FakeAWS()
    assert SESEmailProvider(ProviderConfig(AWS), client=ses).send(_msg()).message_id == "ses-1"
    assert ses.calls[0]["Destination"] == {"ToAddresses": ["asha@example.com"]} and ses.calls[0]["FromEmailAddress"].endswith("<clinic@example.com>")
    sns = _FakeAWS()
    cfg = ProviderConfig({**AWS, "dlt_entity_id": "1101234567890", "sns_sender_id": "AKSHAR"})
    assert SNSSMSProvider(cfg, client=sns).send(_msg(channel="sms", to="+919811111111", provider_template_id="1107000000001")).ok
    attrs = sns.calls[0]["MessageAttributes"]
    assert attrs["AWS.MM.SMS.EntityId"]["StringValue"] == "1101234567890" and attrs["AWS.MM.SMS.TemplateId"]["StringValue"] == "1107000000001"
    assert attrs["AWS.SNS.SMS.SMSType"]["StringValue"] == "Transactional"

    class Throttled(Exception):
        response = {"Error": {"Code": "Throttling"}}

    failed = SESEmailProvider(ProviderConfig(AWS), client=_FakeAWS(Throttled("slow down"))).send(_msg())
    assert not failed.ok and failed.retryable


def test_two_factor_sends_codes_only_and_never_stores_the_key_in_errors():
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"Status": "Success", "Details": "session-1"}) if "/123456/" in str(request.url) else \
            httpx.Response(400, json={"Status": "Error", "Details": "Invalid API Key"})

    cfg = ProviderConfig({"twofactor_api_key": "KEY-SECRET-42"})
    p = TwoFactorSMSProvider(client=httpx.Client(transport=httpx.MockTransport(handler)), config=cfg)
    assert not p.send(_msg(channel="sms", to="+919811111111")).ok  # a reminder: not through 2Factor
    ok = p.send(_msg(channel="sms", to="+919811111111", sensitive=True, template_params=["123456", "5"], provider_template_id="LOGIN"))
    assert ok.ok and seen[-1] == "https://2factor.in/API/V1/KEY-SECRET-42/SMS/919811111111/123456/LOGIN"
    bad = p.send(_msg(channel="sms", to="+919811111111", sensitive=True, template_params=["999999"]))
    assert not bad.ok and "KEY-SECRET-42" not in (bad.error or "")


def test_fallback_provider_is_tried_once_when_the_main_one_fails():
    class Stub:
        def __init__(self, name, ok):
            self.name, self.channel, self.ok, self.sent = name, "email", ok, 0

        def configured(self):
            return True

        def send(self, message):
            self.sent += 1
            return DeliveryResult(self.name, self.ok, error=None if self.ok else "down", retryable=not self.ok)

    main, spare = Stub("smtp", False), Stub("brevo", True)
    result = FallbackProvider(main, spare).send(_msg())
    assert result.ok and result.provider == "brevo" and "smtp: down" in result.response["fallback_after"]
    both = FallbackProvider(Stub("smtp", False), Stub("ses", False)).send(_msg())
    assert not both.ok and both.retryable and "smtp: down" in both.error and "ses: down" in both.error


def test_panel_values_are_re_read_through_the_read_only_engine(monkeypatch):
    """On SQLite the write engine starts transactions with BEGIN IMMEDIATE: re-reading the panel values with it inside a
    request that is already writing would wait for that same request (measured: a 30-second stall when sending a code)."""
    from app.core import database

    opened = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def scalar(self, *_a, **_k):
            return {"values": {"google_client_id": "from-panel.apps.googleusercontent.com"}}

    monkeypatch.setattr(pc, "_auto_refresh", lambda: True)
    monkeypatch.setattr(database, "ReadSessionLocal", lambda: opened.append("read") or FakeSession())
    monkeypatch.setattr(database, "SessionLocal", lambda: opened.append("write") or FakeSession())
    pc.reset_cache()
    assert pc.value("google_client_id") == "from-panel.apps.googleusercontent.com"
    assert opened == ["read"]
