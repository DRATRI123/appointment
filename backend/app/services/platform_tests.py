"""Real connection tests for the platform integration settings. A section shows Connected only after one passes."""
from __future__ import annotations

import re
import secrets as pysecrets
from typing import Any

from app.core.exceptions import ValidationFailed
from app.integrations.http import IntegrationAPIError, request

S3_ERRORS = {
    "NoSuchBucket": "The bucket does not exist. Check the bucket name and the region.",
    "AccessDenied": "Access denied. The access key needs permission to read, write and delete objects in this bucket.",
    "InvalidAccessKeyId": "The access key ID is not known to this storage provider.",
    "SignatureDoesNotMatch": "The secret access key is wrong.",
    "PermanentRedirect": "The bucket is in a different region. Correct the region.",
    "AuthorizationHeaderMalformed": "The region is wrong for this bucket.",
}


def _s3_message(exc: Exception) -> str:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    if code in S3_ERRORS:
        return S3_ERRORS[code]
    name = type(exc).__name__
    if name in ("EndpointConnectionError", "ConnectTimeoutError", "ConnectionClosedError"):
        return "Cannot reach the storage. Check the endpoint URL and the server's internet access."
    if name == "NoCredentialsError":
        return "Enter the access key ID and secret access key."
    return f"{name}: {str(exc)[:200]}"


def test_bucket(bucket: str, prefix: str) -> tuple[bool, str]:
    """Write, read back and delete a small object."""
    from app.core.storage import S3Storage, read_raw, s3_client, write_raw

    if not bucket:
        return False, "Enter the bucket name."
    try:
        backend = S3Storage(s3_client(), bucket, prefix or "")
        key = f"private/_connection-test/{pysecrets.token_hex(8)}.txt"
        body = f"connection test {pysecrets.token_hex(8)}".encode()
        write_raw(backend, key, body)
        ok = read_raw(backend, key) == body
        backend.delete(key)
    except Exception as exc:  # noqa: BLE001 - boto3 raises many error types; all become a clear message
        return False, _s3_message(exc)
    return (True, "Connected: a test file was written, read back and deleted.") if ok else (False, "The file read back was different.")


def test_google(client_id: str | None, client_secret: str | None, redirect: str) -> tuple[bool, str]:
    """Google's token endpoint answers a made-up code with ``invalid_grant`` when the client ID and secret are right,
    and with ``invalid_client`` when they are wrong. Nothing is created in Google."""
    from app.integrations.google_calendar import TOKEN_URL

    if not client_id or not client_secret:
        return False, "Enter the client ID and the client secret."
    if not client_id.endswith(".apps.googleusercontent.com"):
        return False, "A Google OAuth client ID ends with .apps.googleusercontent.com."
    try:
        resp = request("POST", TOKEN_URL, data={"code": "connection-test", "client_id": client_id, "client_secret": client_secret,
                                                "redirect_uri": redirect, "grant_type": "authorization_code"})
    except IntegrationAPIError as exc:
        return False, f"Cannot reach Google: {exc}"
    try:
        error = (resp.json() or {}).get("error")
    except ValueError:
        error = None
    if error == "invalid_grant":
        return True, "Google accepted the client ID and secret. The redirect URL is checked when someone connects."
    if error in ("invalid_client", "unauthorized_client"):
        return False, "Google did not accept the client ID or secret. Copy them again from Google Cloud Console → Credentials."
    if error == "redirect_uri_mismatch":
        return False, "Add the redirect URL shown here to the OAuth client in Google Cloud Console."
    return False, f"Unexpected answer from Google (HTTP {resp.status_code}{', ' + error if error else ''})."


SENTRY_DSN = re.compile(r"^https://[0-9a-f]{16,64}(:[0-9a-f]+)?@[A-Za-z0-9.-]+(:\d+)?/(.+/)?\d+$")


def test_sentry(dsn: str | None) -> tuple[bool, str]:
    if not dsn:
        return False, "Enter the DSN."
    if not SENTRY_DSN.match(dsn):
        return False, "This does not look like a Sentry DSN (https://<key>@<host>/<project id>)."
    return True, "The DSN is valid. Error reporting starts after the API and worker restart."


def test_channel(channel: str, to: str) -> tuple[bool, str]:
    """Send a real test message through the platform's provider for this channel."""
    from app.notifications.providers import OutboundMessage, get_provider

    if not to:
        raise ValidationFailed("Enter where to send the test message.", code="test_destination_required")
    provider = get_provider(channel)
    if not provider.configured():
        return False, f"{provider.name} is not completely set up."
    body = "Test message from your appointment platform. If you received this, the connection works."
    message = OutboundMessage(channel=channel, to=to, body=body, subject="Test message", from_name="Appointment Platform")
    if channel == "whatsapp" and provider.name != "console":
        return False, "WhatsApp only delivers approved templates to people who have not written first. Send a test booking instead, or check with “Test sign-in code” on a clinic."
    try:
        result = provider.send(message)
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"
    return (True, f"Sent with {result.provider}.") if result.ok else (False, result.error or "Sending failed.")


def run(section: str, payload: dict[str, Any]) -> tuple[bool, str]:
    from app.services.platform_config import runtime_settings

    s = runtime_settings()
    if section == "storage":
        return test_bucket(s.s3_bucket, s.s3_prefix)
    if section == "backup":
        return test_bucket(s.backup_s3_bucket, s.backup_s3_prefix or "backups/")
    if section == "google":
        from app.integrations.google_calendar import redirect_uri

        return test_google(s.google_client_id, s.google_client_secret, redirect_uri())
    if section == "monitoring":
        return test_sentry(s.sentry_dsn)
    if section in ("email", "sms", "whatsapp"):
        return test_channel(section, (payload.get("to") or "").strip())
    raise ValidationFailed("Unknown section.", code="invalid_section")
