"""Zoom meetings via a Server-to-Server OAuth app (Zoom Marketplace → Develop → Server-to-Server OAuth).

Scopes needed on the Zoom app: ``meeting:write:meeting:admin`` (create/update/delete) and ``user:read:user:admin``
(test the connection). Meetings are created for the professional's Zoom user (email) or the account owner (``me``).
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError, check, request

TOKEN_URL = "https://zoom.us/oauth/token"
API = "https://api.zoom.us/v2"


def access_token(account_id: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        body = check(request("POST", TOKEN_URL, params={"grant_type": "account_credentials", "account_id": account_id},
                             headers={"Authorization": f"Basic {basic}"}), "Zoom token")
    except IntegrationAPIError as exc:
        if exc.status in (400, 401):
            exc.reconnect, exc.retryable = True, False
        raise
    return body["access_token"], utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)) - 60)


class ZoomClient:
    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}

    def me(self, user: str = "me") -> dict[str, Any]:
        return check(request("GET", f"{API}/users/{user}", headers=self.headers), "Zoom user")

    def create(self, user: str, payload: dict[str, Any]) -> dict[str, Any]:
        return check(request("POST", f"{API}/users/{user}/meetings", json=payload, headers=self.headers), "Create Zoom meeting")

    def update(self, meeting_id: str, payload: dict[str, Any]) -> None:
        check(request("PATCH", f"{API}/meetings/{meeting_id}", json=payload, headers=self.headers), "Update Zoom meeting")

    def delete(self, meeting_id: str) -> None:
        try:
            check(request("DELETE", f"{API}/meetings/{meeting_id}", params={"schedule_for_reminder": "false"}, headers=self.headers), "Delete Zoom meeting")
        except IntegrationAPIError as exc:
            if exc.status != 404:
                raise


def meeting_payload(topic: str, start: datetime, minutes: int, timezone: str, agenda: str | None = None) -> dict[str, Any]:
    return {"topic": topic[:200], "type": 2, "start_time": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": max(1, minutes), "timezone": timezone, "agenda": (agenda or "")[:2000],
            "settings": {"waiting_room": True, "join_before_host": False, "mute_upon_entry": True, "approval_type": 2, "meeting_authentication": False}}
