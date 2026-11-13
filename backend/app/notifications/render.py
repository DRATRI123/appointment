"""Placeholder rendering. Deliberately not a template engine: ``{{name}}`` is replaced by a value and nothing else runs."""
from __future__ import annotations

import html
import re

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


def placeholders(text: str | None) -> set[str]:
    return set(PLACEHOLDER.findall(text or ""))


def render(text: str | None, values: dict[str, str]) -> str:
    if not text:
        return ""
    out = PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), text)
    # Drop lines that became empty because an optional value was blank, and collapse runs of blank lines.
    lines = [ln.rstrip() for ln in out.splitlines()]
    cleaned: list[str] = []
    for ln in lines:
        if ln == "" and cleaned and cleaned[-1] == "":
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def single_line(text: str, limit: int | None = None) -> str:
    one = re.sub(r"\s+", " ", text).strip()
    return one if limit is None or len(one) <= limit else one[: limit - 1].rstrip() + "…"


URL = re.compile(r"(https?://[^\s<]+)")


def email_html(body_text: str, *, organization_name: str, primary_color: str = "#0f766e", footer: str | None = None) -> str:
    """Minimal, inline-styled HTML version of a plain-text email. All text is escaped; links are made clickable."""
    color = primary_color if re.fullmatch(r"#[0-9a-fA-F]{3,8}", primary_color or "") else "#0f766e"
    paragraphs = []
    for block in body_text.split("\n\n"):
        escaped = html.escape(block)
        escaped = URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:{color}">{m.group(1)}</a>', escaped)
        paragraphs.append(f'<p style="margin:0 0 14px;line-height:1.55">{escaped.replace(chr(10), "<br>")}</p>')
    foot = html.escape(footer or f"Sent by {organization_name}. You receive this because you have an appointment with us.")
    return (
        '<!doctype html><html><body style="margin:0;background:#f5f5f4;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1c1917">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden" cellpadding="0" cellspacing="0">'
        f'<tr><td style="background:{color};color:#ffffff;padding:16px 24px;font-size:16px;font-weight:600">{html.escape(organization_name)}</td></tr>'
        f'<tr><td style="padding:24px;font-size:15px;word-break:break-word;overflow-wrap:anywhere">{"".join(paragraphs)}</td></tr>'
        f'<tr><td style="padding:16px 24px;font-size:12px;color:#78716c;border-top:1px solid #e7e5e4">{foot}</td></tr>'
        "</table></td></tr></table></body></html>"
    )
