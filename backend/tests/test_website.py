"""Website Management: validation, draft/publish/restore, concurrency, permissions, isolation and the public read."""
from __future__ import annotations

import copy

import pytest

from tests.booking_helpers import Clinic
from tests.helpers import bearer, create_org, register


@pytest.fixture()
def clinic(client):
    return Clinic(client, email="site-owner@example.com", name="Site Clinic")


def _get(client, clinic):
    r = client.get("/api/v1/website", headers=clinic.h)
    assert r.status_code == 200, r.text
    return r.json()


def _save(client, clinic, doc, lock, expect=200):
    r = client.put("/api/v1/website/draft", json={"document": doc, "lock_version": lock}, headers=clinic.h)
    assert r.status_code == expect, r.text
    return r.json()


def _public(client, clinic):
    r = client.get(f"/api/v1/public/organizations/{clinic.org['slug']}/website")
    assert r.status_code == 200, r.text
    return r.json()


def test_new_clinic_gets_a_starting_site_from_its_own_profile(client, clinic):
    site = _public(client, clinic)
    assert site["published"] is False and site["version"] == 0
    doc = site["document"]
    assert doc["settings"]["clinic_name"] == "Site Clinic"
    types = [s["type"] for s in doc["sections"]]
    assert types[0] == "hero" and {"services", "doctors", "contact", "branches"} <= set(types)
    # No invented content: testimonials and FAQ start empty and are hidden by the site until filled in.
    sections = {s["type"]: s for s in doc["sections"]}
    assert sections["testimonials"]["items"] == [] and sections["faq"]["items"] == []
    assert any(b["kind"] == "book" for b in doc["buttons"])


def test_draft_publish_restore_cycle(client, clinic):
    state = _get(client, clinic)
    assert state["has_unpublished_changes"] is True and state["published_version"] == 0
    doc = state["draft"]
    doc["sections"][0]["heading"] = "Ayurveda care you can trust"
    state = _save(client, clinic, doc, state["lock_version"])
    assert state["lock_version"] == 1
    assert _public(client, clinic)["document"]["sections"][0]["heading"] != "Ayurveda care you can trust"  # draft is private

    r = client.post("/api/v1/website/publish", json={"lock_version": state["lock_version"], "note": "First version"}, headers=clinic.h)
    assert r.status_code == 200, r.text
    state = r.json()
    assert state["published_version"] == 1 and state["has_unpublished_changes"] is False
    site = _public(client, clinic)
    assert site["published"] is True and site["document"]["sections"][0]["heading"] == "Ayurveda care you can trust"

    doc = state["draft"]
    doc["sections"][0]["heading"] = "Second headline"
    state = _save(client, clinic, doc, state["lock_version"])
    state = client.post("/api/v1/website/publish", json={"lock_version": state["lock_version"]}, headers=clinic.h).json()
    assert state["published_version"] == 2

    versions = client.get("/api/v1/website/versions", headers=clinic.h).json()
    assert [v["version"] for v in versions] == [2, 1] and versions[1]["note"] == "First version" and versions[0]["published_by"] == "Clinic Owner"

    # Restoring copies v1 into the draft; the live site changes only when published again.
    state = client.post("/api/v1/website/versions/1/restore", json={"lock_version": state["lock_version"]}, headers=clinic.h).json()
    assert state["draft"]["sections"][0]["heading"] == "Ayurveda care you can trust"
    assert _public(client, clinic)["document"]["sections"][0]["heading"] == "Second headline"
    state = client.post("/api/v1/website/draft/discard", json={"lock_version": state["lock_version"]}, headers=clinic.h).json()
    assert state["draft"]["sections"][0]["heading"] == "Second headline" and state["has_unpublished_changes"] is False

    actions = [a["action"] for a in client.get(f"/api/v1/organizations/{clinic.org['id']}/audit-logs", params={"page_size": 50}, headers=clinic.h).json()["data"]]
    assert {"website.draft_saved", "website.published", "website.version_restored", "website.draft_discarded"} <= set(actions)


def test_a_stale_save_is_refused_instead_of_overwriting(client, clinic):
    state = _get(client, clinic)
    doc = state["draft"]
    _save(client, clinic, doc, state["lock_version"])
    r = client.put("/api/v1/website/draft", json={"document": doc, "lock_version": state["lock_version"]}, headers=clinic.h)
    assert r.status_code == 409 and r.json()["code"] == "website_edit_conflict"


@pytest.mark.parametrize(("path", "value", "message"), [
    (("buttons", 0, "url"), "javascript:alert(1)", "https://"),
    (("buttons", 0, "url"), "http://example.com", "https://"),
    (("buttons", 0, "url"), "https://user:pw@example.com", "user name"),
    (("settings", "logo_url"), "data:image/png;base64,AAAA", "https://"),
    (("settings", "primary_color"), "red; background:url(x)", "primary color: must be a colour"),
    (("settings", "font"), "Comic Sans", "Input should be"),
    (("settings", "phone"), "<script>", "phone number"),
    (("settings", "social", "instagram"), "https://instagram.com/x\" onmouseover=\"x", "spaces"),
    (("sections", 0, "type"), "html", "tag"),
])
def test_unsafe_or_invalid_content_is_rejected(client, clinic, path, value, message):
    state = _get(client, clinic)
    doc = copy.deepcopy(state["draft"])
    doc["buttons"][0].update({"kind": "url", "url": "https://example.com"})
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    r = client.put("/api/v1/website/draft", json={"document": doc, "lock_version": state["lock_version"]}, headers=clinic.h)
    assert r.status_code == 422, r.text
    assert message.lower() in r.text.lower()


def test_rules_that_span_the_document(client, clinic):
    state = _get(client, clinic)
    lock = state["lock_version"]

    def attempt(mutate, code="website_invalid"):
        doc = copy.deepcopy(state["draft"])
        mutate(doc)
        r = client.put("/api/v1/website/draft", json={"document": doc, "lock_version": lock}, headers=clinic.h)
        assert r.status_code == 422 and r.json()["code"] == code, r.text
        return r.json()["detail"]

    assert "page that does not exist" in attempt(lambda d: d["buttons"].append({"id": "pg", "label": "Our story", "kind": "page", "page": "story"}))
    assert "booking site" in attempt(lambda d: d["pages"].append({"slug": "book", "title": "Book"}))
    assert "share the id" in attempt(lambda d: d["sections"].append(copy.deepcopy(d["sections"][0])))
    # A testimonial can only go live with the patient's consent on record.
    assert "consent" in attempt(lambda d: next(s for s in d["sections"] if s["type"] == "testimonials")["items"].append(
        {"id": "t1", "name": "Asha", "text": "Very caring doctors.", "approved": True, "consent": False}))
    # Custom page addresses cannot hide a location page (/clinic/main).
    assert "used by a location" in attempt(lambda d: d["pages"].append({"slug": clinic.branch["slug"], "title": "Main"}), code="website_page_conflict")
    assert "pdf" in attempt(lambda d: d["buttons"].append({"id": "brochure", "label": "Brochure", "kind": "pdf", "url": "https://example.com/brochure.exe"})).lower()


def test_errors_say_where_the_problem_is(client, clinic):
    state = _get(client, clinic)
    doc = state["draft"]
    doc["sections"].append({"type": "features", "id": "facilities", "heading": "Facilities", "items": [{"title": "Pharmacy"}, {"title": ""}]})
    r = client.put("/api/v1/website/draft", json={"document": doc, "lock_version": state["lock_version"]}, headers=clinic.h)
    assert r.status_code == 422
    assert r.json()["detail"] == "Facilities › item 2 › title: cannot be empty"


def test_valid_rich_site_round_trips(client, clinic):
    state = _get(client, clinic)
    doc = state["draft"]
    doc["settings"].update({"whatsapp": "+91 98250 12345", "font": "classic", "social": {"instagram": "https://instagram.com/akshar"}})
    doc["buttons"] += [
        {"id": "wa", "label": "WhatsApp us", "kind": "whatsapp", "message": "Hello, I'd like an appointment", "icon": "message-circle", "positions": ["hero", "floating"]},
        {"id": "brochure", "label": "Treatment brochure", "kind": "pdf", "url": "/media/org/x/brochure.pdf", "positions": ["footer"], "new_tab": True},
        {"id": "story", "label": "Our story", "kind": "page", "page": "our-story", "positions": ["header"]},
    ]
    doc["pages"].append({"slug": "our-story", "title": "Our story", "body": "## Since 2009\n\nWe **care**.", "show_in_nav": True,
                         "sections": [{"type": "faq", "id": "story-faq", "items": [{"question": "Parking?", "answer": "Yes, free."}]}]})
    doc["sections"].insert(2, {"type": "gallery", "id": "facilities", "heading": "Our clinic",
                               "images": [{"url": "https://cdn.example.com/a.jpg", "alt": "Reception"}]})
    testimonials = next(s for s in doc["sections"] if s["type"] == "testimonials")
    testimonials["items"] = [{"id": "t1", "name": "Ravi P.", "text": "Felt better in a week.", "rating": 5, "consent": True, "approved": True}]
    doc["header"]["nav"].append({"label": "Our story", "kind": "page", "target": "our-story"})
    state = _save(client, clinic, doc, state["lock_version"])
    saved = state["draft"]
    assert saved["pages"][0]["sections"][0]["items"][0]["question"] == "Parking?"
    assert [b["id"] for b in saved["buttons"]][-3:] == ["wa", "brochure", "story"]


def test_permissions_and_tenant_isolation(client, clinic):
    from tests.test_payments import _verifier

    receptionist = _verifier(client, clinic, role="receptionist", mobile="9600000801")
    assert client.get("/api/v1/website", headers=receptionist).status_code == 403
    state = _get(client, clinic)
    r = client.post("/api/v1/website/publish", json={"lock_version": state["lock_version"]}, headers=receptionist)
    assert r.status_code == 403

    # Another clinic's admin edits their own site only.
    other = register(client, "other-site@example.com", "Other Owner")
    client.cookies.clear()
    other_org = create_org(client, bearer(other), "Other Site Clinic")
    other_h = {**bearer(other), "X-Organization-Id": other_org["id"]}
    other_state = client.get("/api/v1/website", headers=other_h).json()
    doc = other_state["draft"]
    doc["sections"][0]["heading"] = "Other clinic only"
    client.put("/api/v1/website/draft", json={"document": doc, "lock_version": other_state["lock_version"]}, headers=other_h)
    client.post("/api/v1/website/publish", json={"lock_version": other_state["lock_version"] + 1}, headers=other_h)
    assert _public(client, clinic)["document"]["sections"][0]["heading"] != "Other clinic only"
    assert client.get(f"/api/v1/public/organizations/{other_org['slug']}/website").json()["document"]["sections"][0]["heading"] == "Other clinic only"


def test_pdf_upload_checks_the_file(client, clinic):
    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    r = client.post("/api/v1/uploads/documents", files={"file": ("brochure.pdf", pdf, "application/pdf")}, headers=clinic.h)
    assert r.status_code == 200, r.text
    assert r.json()["mime_type"] == "application/pdf" and r.json()["url"].endswith(".pdf")
    r = client.post("/api/v1/uploads/documents", files={"file": ("brochure.pdf", b"<html>not a pdf</html>", "application/pdf")}, headers=clinic.h)
    assert r.status_code == 422 and r.json()["code"] == "unsupported_file"


def test_unknown_clinic_has_no_website(client):
    assert client.get("/api/v1/public/organizations/no-such-clinic/website").status_code == 404
