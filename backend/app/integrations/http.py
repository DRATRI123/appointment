"""Shared HTTP plumbing for third-party APIs: an injectable client (tests use httpx.MockTransport) and errors
that say whether a retry can help."""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

_client: httpx.Client | None = None


def set_http_client(client: httpx.Client | None) -> None:
    global _client
    _client = client


def http() -> httpx.Client:
    return _client or httpx.Client(timeout=get_settings().integration_http_timeout_seconds)


class IntegrationAPIError(Exception):
    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False, reconnect: bool = False, body: Any = None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.reconnect = reconnect  # credentials revoked/expired: a person must reconnect
        self.body = body


def request(method: str, url: str, **kwargs) -> httpx.Response:
    client = http()
    try:
        return client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise IntegrationAPIError(f"{type(exc).__name__}: {exc}", retryable=True) from exc
    finally:
        if client is not _client:
            client.close()


def check(resp: httpx.Response, what: str) -> dict[str, Any]:
    if 200 <= resp.status_code < 300:
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {"data": data}
    try:
        body = resp.json()
    except ValueError:
        body = {"text": resp.text[:300]}
    detail = body.get("error_description") or body.get("message") or body.get("error") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message") or str(detail)
    raise IntegrationAPIError(f"{what} failed (HTTP {resp.status_code}): {str(detail or body)[:240]}", status=resp.status_code,
                              retryable=resp.status_code == 429 or resp.status_code >= 500, reconnect=resp.status_code == 401, body=body)
