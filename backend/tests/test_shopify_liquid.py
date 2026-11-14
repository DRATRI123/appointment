"""The Shopify snippet builds a safe booking link from whatever a merchant (or a theme setting) passes in.

Rendered with python-liquid plus a `handleize` filter that behaves like Shopify's.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from liquid import Environment, FileSystemLoader

SHOPIFY = Path(__file__).resolve().parents[2] / "integrations" / "shopify"


def handleize(_context, value) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


@pytest.fixture(scope="module")
def env() -> Environment:
    e = Environment(loader=FileSystemLoader(str(SHOPIFY / "snippets"), ext=".liquid"))
    e.filters["handleize"] = handleize
    return e


def render(env: Environment, **params) -> str:
    args = ", ".join(f"{k}: {v!r}" if not isinstance(v, bool) else f"{k}: {str(v).lower()}" for k, v in params.items())
    return env.parse("{% render 'appointment-booking-button'" + (", " + args if args else "") + " %}").render({"request": {"design_mode": False}})


def href(html: str) -> str:
    m = re.search(r'href="([^"]*)"', html)
    assert m, html
    return m.group(1).replace("&amp;", "&")


def test_basic_link(env):
    html = render(env, booking_url="https://booking.mydomain.com", clinic="akshar-clinic")
    assert href(html) == "https://booking.mydomain.com/akshar-clinic"
    assert "Book appointment" in html and 'class="ab-button ab-button--solid"' in html and "target=" not in html


def test_preselection_parameters_are_cleaned_individually(env):
    html = render(env, booking_url="https://booking.mydomain.com/", clinic="Akshar Clinic", service="Consultation",
                  branch="Navrangpura Main", doctor="Dr. Meera Joshi", date="2026-11-20", label="Book a consultation", style="outline", new_tab=True)
    assert href(html) == ("https://booking.mydomain.com/akshar-clinic?service=consultation&branch=navrangpura-main"
                          "&doctor=dr-meera-joshi&date=2026-11-20")
    assert 'target="_blank" rel="noopener"' in html and "ab-button--outline" in html and "Book a consultation" in html


@pytest.mark.parametrize("bad", [
    {"booking_url": "javascript:alert(1)//", "clinic": "x"},
    {"booking_url": "http://booking.mydomain.com", "clinic": "x"},  # https only
    {"booking_url": "https://booking.mydomain.com", "clinic": ""},
    {"booking_url": "", "clinic": "akshar-clinic"},
])
def test_unsafe_or_incomplete_settings_render_no_link(env, bad):
    assert "<a" not in render(env, **bad)


def test_injection_attempts_cannot_break_out_of_the_link(env):
    html = render(env, booking_url='https://booking.mydomain.com"><script>alert(1)</script>', clinic='x" onmouseover="alert(1)',
                  service="a&price=1", label='<img src=x onerror=alert(1)>')
    assert "<script" not in html and "<img" not in html
    opening_tag = re.search(r"<a\b[^>]*>", html).group(0)
    assert not re.search(r"\son\w+\s*=", opening_tag)  # no event-handler attribute got out of the href
    link = href(html)
    assert link.startswith("https://booking.mydomain.com") and not any(c in link for c in '"<> ') and "price=" not in link
    assert "&lt;img src=x onerror=alert(1)&gt;" in html  # the label is shown as text


def test_section_schema_is_valid_json(env):
    import json

    text = (SHOPIFY / "sections" / "appointment-booking.liquid").read_text()
    schema = json.loads(text.split("{% schema %}")[1].split("{% endschema %}")[0])
    ids = {s["id"] for s in schema["settings"] if "id" in s}
    assert {"booking_url", "clinic", "mode", "service", "branch", "doctor", "button_label", "frame_height"} <= ids
    assert len(schema["name"]) <= 25 and schema["presets"]


SECTION_DEFAULTS = {
    "booking_url": "https://booking.mydomain.com", "clinic": "akshar-clinic", "mode": "button", "service": "", "branch": "",
    "doctor": "", "heading": "Book an appointment", "text": "", "align": "center", "button_label": "Book appointment",
    "button_style": "solid", "button_color": "#0f5132", "button_text_color": "#ffffff", "new_tab": False, "frame_height": 900,
}


def render_section(env: Environment, **settings) -> str:
    text = (SHOPIFY / "sections" / "appointment-booking.liquid").read_text()
    body = text.split("{% schema %}")[0]  # the schema tag is Shopify-only and renders nothing
    return env.parse(body).render({"section": {"id": "s1", "settings": {**SECTION_DEFAULTS, **settings}},
                                   "request": {"design_mode": False}})


def test_section_button_mode_uses_the_snippet(env):
    html = render_section(env, service="Consultation")
    assert href(html) == "https://booking.mydomain.com/akshar-clinic?service=consultation"
    assert "<iframe" not in html


def test_section_embed_mode_frames_the_embed_page_and_checks_the_sender(env):
    html = render_section(env, mode="embed", branch="Navrangpura Main", doctor='x"><script>alert(1)</script>')
    src = re.search(r'<iframe[^>]*\ssrc="([^"]*)"', html).group(1).replace("&amp;", "&")
    assert src == "https://booking.mydomain.com/embed/akshar-clinic?branch=navrangpura-main&doctor=x-script-alert-1-script"
    assert 'loading="lazy"' in html and 'title="Book an appointment"' in html and "height: 900px" in html
    assert "event.origin !== origin" in html and "appointment-booking:resize" in html
    assert html.count("<script") == 1  # only the resize listener


def test_section_renders_nothing_clickable_when_misconfigured(env):
    for mode in ("button", "embed"):
        html = render_section(env, mode=mode, booking_url="http://booking.mydomain.com")
        assert "<a" not in html and "<iframe" not in html
