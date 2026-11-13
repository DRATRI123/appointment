"""iCalendar (RFC 5545) output for "add to calendar" files and professionals' private calendar feeds."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class IcsEvent:
    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str = ""
    location: str = ""
    url: str | None = None
    status: str = "CONFIRMED"  # CONFIRMED | TENTATIVE | CANCELLED
    sequence: int = 0
    updated: datetime | None = None


def _text(value: str) -> str:
    bs = chr(92)  # backslash
    value = value.replace(bs, bs + bs).replace(';', bs + ';').replace(',', bs + ',')
    return value.replace('\r\n', bs + 'n').replace('\n', bs + 'n')


def _dt(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a single space (never splitting UTF-8)."""
    out, current = [], b""
    for ch in line:
        enc = ch.encode()
        if len(current) + len(enc) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += enc
    out.append(current.decode())
    return "\r\n ".join(out)


def calendar(events: list[IcsEvent], *, name: str, method: str | None = "PUBLISH") -> str:
    now = _dt(datetime.now(UTC))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Appointment Platform//Bookings//EN", "CALSCALE:GREGORIAN", f"X-WR-CALNAME:{_text(name)}"]
    if method:
        lines.append(f"METHOD:{method}")
    for e in events:
        lines += ["BEGIN:VEVENT", f"UID:{e.uid}", f"DTSTAMP:{now}", f"DTSTART:{_dt(e.start)}", f"DTEND:{_dt(e.end)}", f"SUMMARY:{_text(e.summary)}",
                  f"STATUS:{e.status}", f"SEQUENCE:{e.sequence}"]
        if e.updated:
            lines.append(f"LAST-MODIFIED:{_dt(e.updated)}")
        if e.description:
            lines.append(f"DESCRIPTION:{_text(e.description)}")
        if e.location:
            lines.append(f"LOCATION:{_text(e.location)}")
        if e.url:
            lines.append(f"URL:{e.url}")
        if e.status != "CANCELLED":
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Appointment reminder", "TRIGGER:-PT1H", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"
