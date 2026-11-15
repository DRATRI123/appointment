"""Development and test helpers. This router is mounted only when APP_ENV is development or test.

The console delivery providers keep messages in memory instead of sending them. Automated browser tests read the
latest one-time code from here, so the code never has to appear in an API response or a log line.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.exceptions import NotFoundError
from app.notifications.providers import console_provider

router = APIRouter(prefix="/dev", tags=["development"])


@router.get("/outbox/latest-code", summary="Latest one-time code sent to a destination by a console provider (development only)")
def latest_code(destination: str = Query(min_length=3, max_length=254)):
    wanted = destination.strip().lower()
    for channel in ("sms", "whatsapp", "email"):
        for message in reversed(console_provider(channel).outbox):
            if message.sensitive and message.to.lower() == wanted and message.template_params:
                return {"channel": channel, "code": message.template_params[0]}
    raise NotFoundError("No code sent to that destination.", code="not_found")
