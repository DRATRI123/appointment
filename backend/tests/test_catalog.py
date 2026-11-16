from __future__ import annotations

import io

from tests.helpers import bearer, create_org, otp_login, register

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _owner_with_org(client, email="cat-owner@example.com", name="Cat Clinic"):
    tokens = register(client, email)
    client.cookies.clear()
    org = create_org(client, bearer(tokens), name)
    headers = {**bearer(tokens), "X-Organization-Id": org["id"]}
    return tokens, org, headers


def test_branch_crud_default_and_last_branch_guard(client):
    _, _, h = _owner_with_org(client)
    r = client.post("/api/v1/branches", json={"name": "Main Branch", "code": "main", "business_hours": {"mon": [["09:00", "13:00"], ["16:00", "20:00"]]}}, headers=h)
    assert r.status_code == 201, r.text
    main = r.json()
    assert main["code"] == "MAIN" and main["slug"] == "main-branch" and main["is_default"] is True

    r = client.post("/api/v1/branches", json={"name": "Second", "code": "MAIN"}, headers=h)
    assert r.status_code == 409
    r = client.post("/api/v1/branches", json={"name": "Second", "code": "SEC", "business_hours": {"xyz": []}}, headers=h)
    assert r.status_code == 422
    second = client.post("/api/v1/branches", json={"name": "Second", "code": "SEC", "is_default": True}, headers=h).json()
    assert second["is_default"] is True
    branches = client.get("/api/v1/branches", headers=h).json()
    assert [b["is_default"] for b in branches] == [True, False] and branches[0]["id"] == second["id"]

    r = client.patch(f"/api/v1/branches/{main['id']}", json={"phone": "+911234567890", "is_active": False}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert len(client.get("/api/v1/branches?include_inactive=false", headers=h).json()) == 1

    assert client.delete(f"/api/v1/branches/{second['id']}", headers=h).status_code == 200
    r = client.delete(f"/api/v1/branches/{main['id']}", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "last_branch"
    assert client.get("/api/v1/branches", headers=h).json()[0]["is_default"] is True


def test_catalog_is_tenant_isolated_and_permission_guarded(client):
    _, org_a, ha = _owner_with_org(client, "iso-a@example.com", "Iso A")
    _, org_b, hb = _owner_with_org(client, "iso-b@example.com", "Iso B")
    branch_a = client.post("/api/v1/branches", json={"name": "A1", "code": "A1"}, headers=ha).json()
    # B cannot see or modify A's branch, even by id.
    assert client.get(f"/api/v1/branches/{branch_a['id']}", headers=hb).status_code == 404
    assert client.patch(f"/api/v1/branches/{branch_a['id']}", json={"name": "Renamed"}, headers=hb).status_code == 404
    assert client.get("/api/v1/branches", headers=hb).json() == []
    # B cannot point a service's pricing at A's branch.
    r = client.post("/api/v1/services", json={"name": "Consult", "price_paise": 50000, "pricing": [{"branch_id": branch_a["id"]}]}, headers=hb)
    assert r.status_code == 404

    # Receptionist can read but not write the catalogue.
    client.post(f"/api/v1/organizations/{org_a['id']}/members", json={"identifier": "9555555555", "full_name": "Desk", "role_code": "receptionist"}, headers=ha)
    rec = otp_login(client, "9555555555")
    client.cookies.clear()
    hr = {**bearer(rec), "X-Organization-Id": org_a["id"]}
    assert client.get("/api/v1/branches", headers=hr).status_code == 200
    assert client.post("/api/v1/branches", json={"name": "Nope", "code": "N"}, headers=hr).status_code == 403
    assert client.post("/api/v1/services", json={"name": "Nope"}, headers=hr).status_code == 403


def test_categories_services_pricing_and_payment_rules(client):
    _, org, h = _owner_with_org(client, "svc-owner@example.com", "Svc Clinic")
    b1 = client.post("/api/v1/branches", json={"name": "City", "code": "CITY"}, headers=h).json()
    b2 = client.post("/api/v1/branches", json={"name": "Suburb", "code": "SUB"}, headers=h).json()
    cat = client.post("/api/v1/service-categories", json={"name": "Ayurvedic consultation"}, headers=h).json()
    assert cat["slug"] == "ayurvedic-consultation"

    r = client.post("/api/v1/services", json={"name": "Panchakarma", "price_paise": 150000, "payment_mode": "partial_advance"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "advance_required"
    r = client.post("/api/v1/services", json={"name": "Free camp", "price_paise": 100, "payment_mode": "free"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "free_price"
    r = client.post("/api/v1/services", json={"name": "Bad discount", "price_paise": 100, "discounted_price_paise": 200}, headers=h)
    assert r.status_code == 422

    payload = {
        "name": "Ayurvedic consultation", "category_id": cat["id"], "duration_minutes": 30, "price_paise": 80000,
        "discounted_price_paise": 70000, "payment_mode": "partial_advance", "advance_amount_paise": 20000,
        "consultation_mode": "both",
        "pricing": [{"branch_id": b1["id"], "price_paise": 90000}, {"branch_id": b2["id"], "is_available": False}],
    }
    r = client.post("/api/v1/services", json=payload, headers=h)
    assert r.status_code == 201, r.text
    svc = r.json()
    assert svc["currency"] == "INR" and svc["category_name"] == "Ayurvedic consultation"
    assert {p["branch_id"]: p["price_paise"] for p in svc["pricing"]} == {b1["id"]: 90000, b2["id"]: None}

    # Branch filter honours availability overrides.
    assert len(client.get(f"/api/v1/services?branch_id={b1['id']}", headers=h).json()) == 1
    assert len(client.get(f"/api/v1/services?branch_id={b2['id']}", headers=h).json()) == 0
    cats = client.get("/api/v1/service-categories", headers=h).json()
    assert cats[0]["service_count"] == 1

    # Replace pricing: drop b2 row, change b1 price.
    r = client.patch(f"/api/v1/services/{svc['id']}", json={"pricing": [{"branch_id": b1["id"], "price_paise": 95000}], "sort_order": 2}, headers=h)
    assert r.status_code == 200
    assert [(p["branch_id"], p["price_paise"]) for p in r.json()["pricing"]] == [(b1["id"], 95000)]
    assert len(client.get(f"/api/v1/services?branch_id={b2['id']}", headers=h).json()) == 1

    # Follow-up service linkage and self-reference guard.
    follow = client.post("/api/v1/services", json={"name": "Follow-up", "kind": "follow_up", "price_paise": 30000, "payment_mode": "pay_at_clinic"}, headers=h).json()
    r = client.patch(f"/api/v1/services/{svc['id']}", json={"follow_up_service_id": follow["id"], "follow_up_within_days": 14}, headers=h)
    assert r.json()["follow_up_service_id"] == follow["id"]
    assert client.patch(f"/api/v1/services/{svc['id']}", json={"follow_up_service_id": svc["id"]}, headers=h).status_code == 422

    # Packages.
    r = client.post("/api/v1/service-packages", json={"name": "Wellness pack", "price_paise": 200000, "items": [{"service_id": svc["id"], "quantity": 3}, {"service_id": follow["id"]}]}, headers=h)
    assert r.status_code == 201, r.text
    assert sum(i["quantity"] for i in r.json()["items"]) == 4
    r = client.post("/api/v1/service-packages", json={"name": "Dup", "price_paise": 1, "items": [{"service_id": svc["id"]}, {"service_id": svc["id"]}]}, headers=h)
    assert r.status_code == 422

    # Deleting a category uncategorises its services.
    assert client.delete(f"/api/v1/service-categories/{cat['id']}", headers=h).status_code == 200
    assert client.get(f"/api/v1/services/{svc['id']}", headers=h).json()["category_id"] is None


def test_professionals_with_branches_services_and_user_link(client):
    tokens, org, h = _owner_with_org(client, "pro-owner@example.com", "Pro Clinic")
    b1 = client.post("/api/v1/branches", json={"name": "North", "code": "N"}, headers=h).json()
    b2 = client.post("/api/v1/branches", json={"name": "South", "code": "S"}, headers=h).json()
    consult = client.post("/api/v1/services", json={"name": "Consult", "price_paise": 50000}, headers=h).json()
    derm = client.post("/api/v1/services", json={"name": "Skin check", "price_paise": 70000}, headers=h).json()

    payload = {
        "display_name": "Dr. Meera Rao", "title": "Dr.", "specialization": "Dermatology", "qualification": "MBBS, MD",
        "experience_years": 12, "registration_number": "KMC-12345", "languages": ["en", "kn"], "default_fee_paise": 60000,
        "default_duration_minutes": 20, "buffer_minutes": 5,
        "branches": [{"branch_id": b1["id"], "fee_paise": 60000}, {"branch_id": b2["id"], "fee_paise": 80000, "duration_minutes": 30}],
        "services": [{"service_id": consult["id"]}, {"service_id": derm["id"], "branch_id": b2["id"], "fee_override_paise": 90000}],
    }
    r = client.post("/api/v1/professionals", json=payload, headers=h)
    assert r.status_code == 201, r.text
    pro = r.json()
    assert pro["slug"] == "dr-meera-rao"
    assert {b["branch_name"]: b["fee_paise"] for b in pro["branches"]} == {"North": 60000, "South": 80000}
    assert len(pro["services"]) == 2

    # Filters by branch and by service.
    assert len(client.get(f"/api/v1/professionals?branch_id={b1['id']}", headers=h).json()) == 1
    assert len(client.get(f"/api/v1/professionals?service_id={derm['id']}", headers=h).json()) == 1
    assert client.get(f"/api/v1/services/{consult['id']}", headers=h).json()["professional_ids"] == [pro["id"]]

    # Linking a user requires staff membership first.
    me = client.get("/api/v1/users/me", headers=bearer(tokens)).json()
    r = client.post(f"/api/v1/organizations/{org['id']}/members", json={"identifier": "doc@example.com", "full_name": "Meera", "role_code": "doctor"}, headers=h)
    doc_user_id = r.json()["user"]["id"]
    assert client.patch(f"/api/v1/professionals/{pro['id']}", json={"user_id": doc_user_id}, headers=h).json()["user_id"] == doc_user_id
    plain = register(client, "plain-pro@example.com")
    client.cookies.clear()
    plain_id = client.get("/api/v1/users/me", headers=bearer(plain)).json()["user"]["id"]
    r = client.patch(f"/api/v1/professionals/{pro['id']}", json={"user_id": plain_id}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "not_staff"
    assert me["user"]["id"] != plain_id

    # Replace branch assignments; removing South drops it.
    r = client.patch(f"/api/v1/professionals/{pro['id']}", json={"branches": [{"branch_id": b1["id"], "fee_paise": 65000}]}, headers=h)
    assert [b["branch_name"] for b in r.json()["branches"]] == ["North"]
    assert client.get(f"/api/v1/professionals?branch_id={b2['id']}", headers=h).json() == []

    # Duplicate slug within the organization is rejected; same slug in another org is fine.
    assert client.post("/api/v1/professionals", json={"display_name": "Other", "slug": "dr-meera-rao"}, headers=h).status_code == 409
    _, _, h2 = _owner_with_org(client, "pro-owner2@example.com", "Other Clinic")
    assert client.post("/api/v1/professionals", json={"display_name": "Dr. Meera Rao", "slug": "dr-meera-rao"}, headers=h2).status_code == 201

    # Soft delete hides the professional.
    assert client.delete(f"/api/v1/professionals/{pro['id']}", headers=h).status_code == 200
    assert client.get(f"/api/v1/professionals/{pro['id']}", headers=h).status_code == 404


def test_public_catalogue_hides_inactive_and_private_fields(client):
    _, org, h = _owner_with_org(client, "pub-owner@example.com", "Public Clinic")
    b = client.post("/api/v1/branches", json={"name": "Main", "code": "M"}, headers=h).json()
    client.post("/api/v1/branches", json={"name": "Closed", "code": "C", "is_active": False}, headers=h)
    cat = client.post("/api/v1/service-categories", json={"name": "General"}, headers=h).json()
    client.post("/api/v1/service-categories", json={"name": "Hidden", "is_active": False}, headers=h)
    svc = client.post("/api/v1/services", json={"name": "Visible", "category_id": cat["id"], "price_paise": 100}, headers=h).json()
    client.post("/api/v1/services", json={"name": "Offline only", "price_paise": 100, "is_bookable_online": False}, headers=h)
    client.post("/api/v1/services", json={"name": "Inactive", "price_paise": 100, "is_active": False}, headers=h)
    pro = client.post("/api/v1/professionals", json={"display_name": "Dr. Public", "email": "secret@example.com", "phone": "+911111111111", "branches": [{"branch_id": b["id"]}], "services": [{"service_id": svc["id"]}]}, headers=h).json()
    client.post("/api/v1/professionals", json={"display_name": "Dr. Hidden", "is_bookable_online": False}, headers=h)

    slug = org["slug"]
    r = client.get(f"/api/v1/public/organizations/{slug}")
    assert r.status_code == 200
    body = r.json()
    assert [x["name"] for x in body["branches"]] == ["Main"]
    assert [x["name"] for x in body["categories"]] == ["General"]
    assert "branding" in body["settings"] and "payment" not in body["settings"]
    assert [s["name"] for s in client.get(f"/api/v1/public/organizations/{slug}/services").json()] == ["Visible"]
    pros = client.get(f"/api/v1/public/organizations/{slug}/professionals").json()
    assert [p["display_name"] for p in pros] == ["Dr. Public"]
    assert pros[0]["email"] is None and pros[0]["phone"] is None
    assert client.get(f"/api/v1/public/organizations/{slug}/professionals?service_id={svc['id']}").json()[0]["id"] == pro["id"]
    assert client.get(f"/api/v1/public/organizations/{slug}/professionals/{pro['id']}").status_code == 200
    assert client.get("/api/v1/public/organizations/does-not-exist").status_code == 404


def test_image_upload_validation_and_serving(client, tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.EncryptingStorage(storage_module.LocalStorage(tmp_path))
    try:
        _, org, h = _owner_with_org(client, "up-owner@example.com", "Upload Clinic")
        r = client.post("/api/v1/uploads/images", files={"file": ("logo.png", io.BytesIO(PNG), "image/png")}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mime_type"] == "image/png" and body["url"].startswith("/media/org/")
        assert (tmp_path / body["key"]).exists()
        # Declared type is ignored; content is sniffed.
        r = client.post("/api/v1/uploads/images", files={"file": ("evil.png", io.BytesIO(b"<script>alert(1)</script>"), "image/png")}, headers=h)
        assert r.status_code == 422 and r.json()["code"] == "unsupported_file"
        r = client.post("/api/v1/uploads/images", files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 ..."), "application/pdf")}, headers=h)
        assert r.status_code == 422
        # Receptionist (no write permissions) cannot upload.
        client.post(f"/api/v1/organizations/{org['id']}/members", json={"identifier": "9666666666", "full_name": "Desk", "role_code": "staff"}, headers=h)
        staff = otp_login(client, "9666666666")
        client.cookies.clear()
        r = client.post("/api/v1/uploads/images", files={"file": ("logo.png", io.BytesIO(PNG), "image/png")}, headers={**bearer(staff), "X-Organization-Id": org["id"]})
        assert r.status_code == 403
    finally:
        storage_module._storage = None
