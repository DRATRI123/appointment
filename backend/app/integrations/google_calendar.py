"""Google Calendar API (OAuth 2.0 web flow, events, Meet links).

Scopes: ``openid email`` (to show which account is connected) and ``calendar.events`` (create/update/delete
our events and read busy time). Tokens are stored encrypted on the Integration row.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from app.core.time import utcnow
from app.integrations.http import IntegrationAPIError, check, request
from app.services.platform_config import runtime_settings as get_settings  # panel values win over .env

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
# bandit B105 false positive: public OAuth endpoint URL
TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
API = "https://www.googleapis.com/calendar/v3"
SCOPES = ["openid", "email", "https://www.googleapis.com/auth/calendar.events",
          # to let the doctor choose which calendar receives bookings (connections made before this keep "primary")
          "https://www.googleapis.com/auth/calendar.calendarlist.readonly"]
PRIVATE_KEY = "appointment_platform_id"  # extendedProperties.private marker on events we create


def configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def redirect_uri() -> str:
    s = get_settings()
    return s.google_calendar_redirect_uri or f"{s.frontend_url.rstrip('/')}/api/v1/integrations/google/callback"


def authorization_url(state: str, login_hint: str | None = None, scopes: list[str] | None = None) -> str:
    s = get_settings()
    params = {"client_id": s.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code", "scope": " ".join(scopes or SCOPES),
              "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state}
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict[str, str]) -> dict[str, Any]:
    s = get_settings()
    body = check(request("POST", TOKEN_URL, data={**data, "client_id": s.google_client_id or "", "client_secret": s.google_client_secret or ""}), "Google token")
    expires = utcnow() + timedelta(seconds=int(body.get("expires_in", 3600)) - 60)
    return {**body, "expires_at": expires.isoformat()}


def exchange_code(code: str, required_scope: str | None = SCOPES[2]) -> dict[str, Any]:
    tokens = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    if not tokens.get("refresh_token"):
        raise IntegrationAPIError("Google did not return a refresh token. Remove the app's access in your Google account settings and connect again.")
    granted = set((tokens.get("scope") or "").split())
    if required_scope and required_scope not in granted:
        what = "your calendar" if required_scope == SCOPES[2] else "the requested Google service"
        raise IntegrationAPIError(f"Access to {what} was not granted. Connect again and tick the box Google shows.")
    return tokens


def refresh(refresh_token: str) -> dict[str, Any]:
    try:
        return _token_request({"refresh_token": refresh_token, "grant_type": "refresh_token"})
    except IntegrationAPIError as exc:
        if exc.status == 400 and isinstance(exc.body, dict) and exc.body.get("error") == "invalid_grant":
            exc.reconnect = True
            exc.retryable = False
        raise


def revoke(token: str) -> None:
    try:
        request("POST", REVOKE_URL, data={"token": token})
    except IntegrationAPIError:
        pass  # best effort; the stored credentials are deleted regardless


def account_email(access_token: str) -> str | None:
    return check(request("GET", USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}), "Google user info").get("email")


def list_calendars(access_token: str) -> list[dict[str, Any]]:
    """Calendars the doctor may write to (owner or writer), primary first."""
    data = check(request("GET", f"{API}/users/me/calendarList", params={"minAccessRole": "writer", "fields": "items(id,summary,primary,accessRole,timeZone)"},
                         headers={"Authorization": f"Bearer {access_token}"}), "List calendars")
    items = [{"id": c["id"], "name": c.get("summary") or c["id"], "primary": bool(c.get("primary")), "time_zone": c.get("timeZone")} for c in data.get("items", [])]
    return sorted(items, key=lambda c: (not c["primary"], c["name"].lower()))


class CalendarClient:
    def __init__(self, access_token: str, calendar_id: str = "primary"):
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.calendar_id = calendar_id

    def _url(self, suffix: str = "") -> str:
        from urllib.parse import quote

        return f"{API}/calendars/{quote(self.calendar_id, safe='')}/events{suffix}"

    def insert(self, event: dict[str, Any], *, with_meet: bool) -> dict[str, Any]:
        params = {"sendUpdates": "none"}
        if with_meet:
            params["conferenceDataVersion"] = "1"
        return check(request("POST", self._url(), params=params, json=event, headers=self.headers), "Create calendar event")

    def patch(self, event_id: str, event: dict[str, Any], *, with_meet: bool) -> dict[str, Any]:
        params = {"sendUpdates": "none"}
        if with_meet:
            params["conferenceDataVersion"] = "1"
        return check(request("PATCH", self._url(f"/{event_id}"), params=params, json=event, headers=self.headers), "Update calendar event")

    def delete(self, event_id: str) -> None:
        try:
            check(request("DELETE", self._url(f"/{event_id}"), params={"sendUpdates": "none"}, headers=self.headers), "Delete calendar event")
        except IntegrationAPIError as exc:
            if exc.status not in (404, 410):  # already gone is fine
                raise

    def busy(self, time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
        """Opaque, non-cancelled events that we did not create. Titles are not kept."""
        out: list[tuple[datetime, datetime]] = []
        page: str | None = None
        for _ in range(20):
            params = {"timeMin": time_min.isoformat(), "timeMax": time_max.isoformat(), "singleEvents": "true", "orderBy": "startTime",
                      "maxResults": "250", "fields": "items(status,transparency,start,end,extendedProperties),nextPageToken"}
            if page:
                params["pageToken"] = page
            data = check(request("GET", self._url(), params=params, headers=self.headers), "Read calendar")
            for item in data.get("items", []):
                if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
                    continue
                if ((item.get("extendedProperties") or {}).get("private") or {}).get(PRIVATE_KEY):
                    continue
                start, end = _parse_when(item.get("start")), _parse_when(item.get("end"))
                if start and end and end > start:
                    out.append((start, end))
            page = data.get("nextPageToken")
            if not page:
                break
        return out


def _parse_when(value: dict | None) -> datetime | None:
    from zoneinfo import ZoneInfo

    if not value:
        return None
    if value.get("dateTime"):
        return datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
    if value.get("date"):  # all-day event: busy for the whole day in the event's timezone
        tz = ZoneInfo(value.get("timeZone") or "Asia/Kolkata")
        return datetime.fromisoformat(value["date"]).replace(tzinfo=tz)
    return None


def meet_link(event: dict[str, Any]) -> str | None:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for ep in (event.get("conferenceData") or {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            return ep.get("uri")
    return None
