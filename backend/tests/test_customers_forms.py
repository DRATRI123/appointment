from __future__ import annotations

import io

from sqlalchemy import select

from app.models import CustomerNote
from app.security.crypto import is_encrypted
from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, otp_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _storage(tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.LocalStorage(tmp_path)
    return storage_module


# ---------------------------------------------------------------- customers
def test_customer_crud_search_segments_and_export(client):
    c = Clinic(client, email="cust-owner@example.com", name="Cust Clinic", payment_mode="pay_at_clinic")
    r = client.post("/api/v1/customers", json={"full_name": "Asha Patel", "mobile": "9811111111", "email": "ASHA@example.com", "gender": "female", "tags": ["VIP", "diabetic"]}, headers=c.h)
    assert r.status_code == 201, r.text
    asha = r.json()
    assert asha["mobile"] == "+919811111111" and asha["email"] == "asha@example.com" and asha["tags"] == ["diabetic", "vip"]
    assert asha["customer_code"].endswith("-00001") and asha["is_guest"] is False
    assert client.post("/api/v1/customers", json={"full_name": "Dup", "mobile": "9811111111"}, headers=c.h).status_code == 409
    assert client.post("/api/v1/customers", json={"full_name": "Nobody"}, headers=c.h).status_code == 422

    # Booking as a guest creates a customer row that shows in the list.
    hold = c.public_hold(ist(c.monday, 9))
    c.public_book(hold["id"], customer={"full_name": "Guest Guy", "mobile": "9822222222"})
    page = c.get("/customers", {"search": "guest"})
    assert page["meta"]["total"] == 1 and page["data"][0]["is_guest"] is True
    assert c.get("/customers", {"tag": "vip"})["meta"]["total"] == 1
    assert c.get("/customers", {"segment": "upcoming"})["data"][0]["full_name"] == "Guest Guy"
    assert c.get("/customers", {"segment": "new_30d"})["meta"]["total"] == 2

    detail = c.get(f"/customers/{asha['id']}")
    assert detail["stats"]["total_appointments"] == 0
    r = client.patch(f"/api/v1/customers/{asha['id']}", json={"blood_group": "B+", "saved_professional_ids": [c.pro["id"]], "consent": {"marketing": False}}, headers=c.h)
    assert r.status_code == 200 and r.json()["saved_professional_ids"] == [c.pro["id"]]
    assert client.patch(f"/api/v1/customers/{asha['id']}", json={"saved_branch_ids": ["00000000-0000-0000-0000-000000000000"]}, headers=c.h).status_code == 422

    r = client.get("/api/v1/customers/export.csv", headers=c.h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("customer_code,full_name") and len(lines) == 3
    logs = client.get(f"/api/v1/organizations/{c.org['id']}/audit-logs", params={"action": "customer.exported"}, headers=c.h).json()
    assert logs["meta"]["total"] == 1

    # Cannot delete a customer with an upcoming appointment; can delete one without.
    guest = page["data"][0]
    assert client.delete(f"/api/v1/customers/{guest['id']}", headers=c.h).status_code == 409
    assert client.delete(f"/api/v1/customers/{asha['id']}", headers=c.h).status_code == 200
    assert client.get(f"/api/v1/customers/{asha['id']}", headers=c.h).status_code == 404


def test_customer_data_is_tenant_isolated(client):
    a = Clinic(client, email="iso-cust-a@example.com", name="Iso Cust A")
    b = Clinic(client, email="iso-cust-b@example.com", name="Iso Cust B")
    cust = client.post("/api/v1/customers", json={"full_name": "Private Person", "mobile": "9833333333"}, headers=a.h).json()
    assert client.get(f"/api/v1/customers/{cust['id']}", headers=b.h).status_code == 404
    assert client.get("/api/v1/customers", headers=b.h).json()["meta"]["total"] == 0
    # Same mobile may exist independently in both organizations.
    assert client.post("/api/v1/customers", json={"full_name": "Private Person", "mobile": "9833333333"}, headers=b.h).status_code == 201


def test_clinical_notes_are_encrypted_and_permissioned(client, db):
    c = Clinic(client, email="notes-owner@example.com", name="Notes Clinic")
    cust = client.post("/api/v1/customers", json={"full_name": "Patient P", "mobile": "9844444444"}, headers=c.h).json()
    r = client.post(f"/api/v1/customers/{cust['id']}/notes", json={"body": "Allergic to penicillin", "note_type": "allergy"}, headers=c.h)
    assert r.status_code == 201, r.text
    note = r.json()
    row = db.scalar(select(CustomerNote).where(CustomerNote.public_id == note["id"]))
    assert is_encrypted(row.body_encrypted) and "penicillin" not in row.body_encrypted
    notes = client.get(f"/api/v1/customers/{cust['id']}/notes", params={"purpose": "consultation"}, headers=c.h).json()
    assert notes[0]["body"] == "Allergic to penicillin" and notes[0]["author_name"] == "Clinic Owner"
    logs = client.get(f"/api/v1/organizations/{c.org['id']}/audit-logs", params={"action": "customer.notes_viewed"}, headers=c.h).json()
    assert logs["data"][0]["purpose"] == "consultation"

    # Receptionist: can read the profile but not clinical notes; doctor can.
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9855555555", "full_name": "Desk", "role_code": "receptionist"})
    rec = otp_login(client, "9855555555")
    client.cookies.clear()
    hr = {**bearer(rec), "X-Organization-Id": c.org["id"]}
    assert client.get(f"/api/v1/customers/{cust['id']}", headers=hr).status_code == 200
    assert client.get(f"/api/v1/customers/{cust['id']}/notes", headers=hr).status_code == 403
    assert client.post(f"/api/v1/customers/{cust['id']}/notes", json={"body": "x"}, headers=hr).status_code == 403
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9866666666", "full_name": "Doc", "role_code": "doctor"})
    doc = otp_login(client, "9866666666")
    client.cookies.clear()
    hd = {**bearer(doc), "X-Organization-Id": c.org["id"]}
    assert client.get(f"/api/v1/customers/{cust['id']}/notes", headers=hd).status_code == 200
    assert client.delete(f"/api/v1/customers/{cust['id']}/notes/{note['id']}", headers=hd).status_code == 200


def test_documents_upload_download_retention_and_purge(client, db, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="docs-owner@example.com", name="Docs Clinic")
        c.put(f"/organizations/{c.org['id']}/settings/privacy", {"values": {"document_retention_days": 30}})
        cust = client.post("/api/v1/customers", json={"full_name": "Doc Patient", "mobile": "9877777777"}, headers=c.h).json()
        r = client.post(f"/api/v1/customers/{cust['id']}/documents", files={"file": ("report.png", io.BytesIO(PNG), "image/png")}, data={"title": "Blood report", "document_type": "report"}, headers=c.h)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["mime_type"] == "image/png" and doc["retention_until"] is not None and doc["uploaded_by_name"] == "Clinic Owner"
        # Not served from the public /media mount.
        assert not list((tmp_path / "public").rglob("*.png"))
        r = client.get(f"/api/v1/customers/{cust['id']}/documents/{doc['id']}/download", params={"purpose": "review"}, headers=c.h)
        assert r.status_code == 200 and r.content == PNG and r.headers["cache-control"] == "private, no-store"
        logs = client.get(f"/api/v1/organizations/{c.org['id']}/audit-logs", params={"action": "customer.document_downloaded"}, headers=c.h).json()
        assert logs["meta"]["total"] == 1
        assert client.post(f"/api/v1/customers/{cust['id']}/documents", files={"file": ("x.exe", io.BytesIO(b"MZ\x90\x00" * 10), "application/octet-stream")}, headers=c.h).status_code == 422

        # Retention purge removes expired documents.
        from datetime import date, timedelta

        from app.models import CustomerDocument
        from app.services.customer_management_service import purge_expired_documents

        row = db.scalar(select(CustomerDocument).where(CustomerDocument.public_id == doc["id"]))
        row.retention_until = date.today() - timedelta(days=1)
        db.flush()
        assert purge_expired_documents(db) == 1
        assert client.get(f"/api/v1/customers/{cust['id']}/documents", headers=c.h).json() == []
        assert not (tmp_path / row.storage_path).exists()
    finally:
        storage_module._storage = None


def test_dependents_and_dependent_booking_via_customer_self_service(client):
    c = Clinic(client, email="fam-owner@example.com", name="Family Clinic", payment_mode="pay_at_clinic")
    user = otp_login(client, "9888888881", "Parent")
    client.cookies.clear()
    hu = bearer(user)
    # Reading never creates a customer record; the first write (or a booking) does.
    r = client.get(f"/api/v1/customer/organizations/{c.org['id']}/profile", headers=hu)
    assert r.status_code == 404 and r.json()["code"] == "no_customer_record"
    assert client.get(f"/api/v1/customer/organizations/{c.org['id']}/dependents", headers=hu).json() == []
    assert c.get("/customers")["meta"]["total"] == 0
    r = client.post(f"/api/v1/customer/organizations/{c.org['id']}/dependents", json={"full_name": "Little One", "relationship_label": "child", "date_of_birth": "2019-05-01"}, headers=hu)
    assert r.status_code == 201, r.text
    dep = r.json()
    assert client.get(f"/api/v1/customer/organizations/{c.org['id']}/profile", headers=hu).json()["is_guest"] is False
    assert client.patch(f"/api/v1/customer/organizations/{c.org['id']}/profile", json={"communication_preferences": {"sms": True, "whatsapp": False}, "consent": {"data_processing": True}}, headers=hu).json()["consent"] == {"data_processing": True}

    # Book for the dependent.
    hold = client.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 9)), "session_key": "fam"}, headers=hu).json()
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "fam", "customer": {"full_name": "Parent"}, "dependent_id": dep["id"]}, headers=hu)
    assert r.status_code == 201, r.text
    assert r.json()["dependent_id"] == dep["id"]
    # Another user's dependent id is rejected.
    other = otp_login(client, "9888888882", "Other")
    client.cookies.clear()
    hold2 = client.post(f"/api/v1/public/organizations/{c.org['slug']}/holds", json={"professional_id": c.pro["id"], "branch_id": c.branch["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 10)), "session_key": "o"}, headers=bearer(other)).json()
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold2["id"], "session_key": "o", "customer": {"full_name": "Other"}, "dependent_id": dep["id"]}, headers=bearer(other))
    assert r.status_code == 404
    # Staff see the dependent under the customer.
    cust_id = c.get("/customers", {"search": "Parent"})["data"][0]["id"]
    assert [d["full_name"] for d in c.get(f"/customers/{cust_id}/dependents")] == ["Little One"]
    assert client.get("/api/v1/customer/organizations", headers=hu).json()[0]["slug"] == c.org["slug"]
    # Self-service can be switched off.
    c.put(f"/organizations/{c.org['id']}/settings/privacy", {"values": {"allow_customer_self_update": False}})
    assert client.get(f"/api/v1/customer/organizations/{c.org['id']}/profile", headers=hu).status_code == 403


# ------------------------------------------------------------- booking forms
INTAKE = {
    "name": "Intake", "fields": [
        {"key": "reason", "label": "Reason", "field_type": "textarea", "is_required": True, "sort_order": 1, "validation": {"min_length": 5}},
        {"key": "smoker", "label": "Do you smoke?", "field_type": "radio", "is_required": True, "sort_order": 2, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
        {"key": "per_day", "label": "Cigarettes per day", "field_type": "number", "is_required": True, "sort_order": 3, "validation": {"min": 1, "max": 100}, "conditions": [{"field": "smoker", "operator": "equals", "value": "yes"}]},
        {"key": "conditions", "label": "Conditions", "field_type": "multi_select", "sort_order": 4, "options": [{"value": "bp", "label": "BP"}, {"value": "sugar", "label": "Sugar"}]},
        {"key": "consent", "label": "I agree", "field_type": "checkbox", "is_required": True, "sort_order": 5},
        {"key": "dob", "label": "Date of birth", "field_type": "date", "sort_order": 6, "validation": {"max_date": "today"}},
        {"key": "reports", "label": "Reports", "field_type": "file", "sort_order": 7, "validation": {"max_files": 1}},
    ],
}


def test_form_builder_versioning_resolution_and_validation(client, tmp_path):
    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="form-owner@example.com", name="Form Clinic", payment_mode="pay_at_clinic")
        # Field validation at build time.
        bad = {"name": "Bad", "fields": [{"key": "a", "label": "A", "field_type": "dropdown"}]}
        assert client.post("/api/v1/booking-forms", json=bad, headers=c.h).status_code == 422
        bad = {"name": "Bad", "fields": [{"key": "a", "label": "A", "field_type": "text", "conditions": [{"field": "zzz", "operator": "equals", "value": 1}]}]}
        assert client.post("/api/v1/booking-forms", json=bad, headers=c.h).json()["code"] == "bad_condition"

        r = client.post("/api/v1/booking-forms", json=INTAKE, headers=c.h)
        assert r.status_code == 201, r.text
        form = r.json()
        assert form["version"] == 1 and form["is_published"] is False and len(form["fields"]) == 7
        # Nothing resolved while unpublished.
        assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"], "branch_id": c.branch["id"]}).json() is None
        assert client.post(f"/api/v1/booking-forms/{form['id']}/publish", headers=c.h).json()["is_published"] is True
        public = client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"], "branch_id": c.branch["id"]}).json()
        assert public["name"] == "Intake" and [f["key"] for f in public["fields"]][0] == "reason"

        # Booking now requires valid answers.
        def book(answers, expect):
            hold = c.public_hold(ist(c.monday, 9), session_key="f")
            r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments", json={"hold_id": hold["id"], "session_key": "f", "customer": {"full_name": "Form Guest", "mobile": "9899999999"}, "form_answers": answers})
            assert r.status_code == expect, r.text
            if expect != 201:
                client.delete(f"/api/v1/public/organizations/{c.org['slug']}/holds/{hold['id']}", params={"session_key": "f"})
            return r.json()

        err = book({}, 422)
        assert err["code"] == "form_invalid" and {e["field"] for e in err["errors"]} == {"reason", "smoker", "consent"}
        err = book({"reason": "too", "smoker": "maybe", "consent": True, "conditions": ["bp", "nope"], "dob": "2999-01-01", "extra": 1}, 422)
        fields = {e["field"]: e["message"] for e in err["errors"]}
        assert "reason" in fields and "smoker" in fields and "conditions" in fields and "dob" in fields and "extra" in fields
        # Conditional field is required only when visible.
        err = book({"reason": "Persistent cough", "smoker": "yes", "consent": True}, 422)
        assert [e["field"] for e in err["errors"]] == ["per_day"]
        # File answers must reference uploaded private keys.
        err = book({"reason": "Persistent cough", "smoker": "no", "consent": True, "reports": [{"key": "public/evil.png"}]}, 422)
        assert err["errors"][0]["field"] == "reports"
        up = client.post(f"/api/v1/public/organizations/{c.org['slug']}/booking-form-files", files={"file": ("r.png", io.BytesIO(PNG), "image/png")})
        assert up.status_code == 200 and up.json()["key"].startswith("private/")
        ok = book({"reason": "Persistent cough", "smoker": "no", "consent": True, "conditions": ["bp"], "dob": "1990-01-01", "reports": [up.json()]}, 201)
        assert ok["form_answers"]["reason"] == "Persistent cough" and ok["form_answers"]["reports"][0]["key"] == up.json()["key"]
        resp = client.get(f"/api/v1/booking-forms/responses/by-appointment/{ok['id']}", headers=c.h).json()
        assert resp["form_version"] == 1 and resp["attachments"][0]["key"].startswith("private/")
        assert client.get(f"/api/v1/booking-forms/{form['id']}", headers=c.h).json()["response_count"] == 1

        # Editing fields of a published form creates version 2 as a draft; v1 keeps serving.
        r = client.patch(f"/api/v1/booking-forms/{form['id']}", json={"fields": INTAKE["fields"][:2]}, headers=c.h)
        v2 = r.json()
        assert v2["version"] == 2 and v2["is_published"] is False and v2["id"] != form["id"]
        assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"]}).json()["version"] == 1
        client.post(f"/api/v1/booking-forms/{v2['id']}/publish", headers=c.h)
        assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"]}).json()["version"] == 2
        assert client.get(f"/api/v1/booking-forms/{form['id']}", headers=c.h).json()["is_published"] is False
        latest = client.get("/api/v1/booking-forms", headers=c.h).json()
        assert [f["version"] for f in latest if f["slug"] == "intake"] == [2]

        # Service-specific form wins over the organization default.
        r = client.post("/api/v1/booking-forms", json={"name": "Skin", "scope": "service", "clone_from": "template-skin-consultation"}, headers=c.h)
        skin = r.json()
        assert skin["fields"][0]["key"] == "concern"
        client.post(f"/api/v1/booking-forms/{skin['id']}/publish", headers=c.h)
        client.post("/api/v1/booking-forms/assign", json={"service_id": c.service["id"], "form_id": skin["id"]}, headers=c.h)
        assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"]}).json()["name"] == "Skin"
        assert client.delete(f"/api/v1/booking-forms/{skin['id']}", headers=c.h).json()["code"] == "form_in_use"
        client.post("/api/v1/booking-forms/assign", json={"service_id": c.service["id"], "form_id": None}, headers=c.h)
        assert client.get(f"/api/v1/public/organizations/{c.org['slug']}/booking-form", params={"service_id": c.service["id"]}).json()["name"] == "Intake"
        assert len(client.get("/api/v1/booking-forms/templates", headers=c.h).json()) == 3
    finally:
        storage_module._storage = None


def test_booking_forms_permissions(client):
    c = Clinic(client, email="formperm-owner@example.com", name="Perm Clinic")
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9811111199", "full_name": "Desk", "role_code": "receptionist"})
    rec = otp_login(client, "9811111199")
    client.cookies.clear()
    hr = {**bearer(rec), "X-Organization-Id": c.org["id"]}
    assert client.get("/api/v1/booking-forms", headers=hr).status_code == 200
    assert client.post("/api/v1/booking-forms", json={"name": "Nope"}, headers=hr).status_code == 403


def test_customer_erasure_removes_personal_data_but_keeps_financial_records(client, db, tmp_path):
    from app.models import AuditLog, Customer, CustomerDocument, CustomerNote, Notification
    from tests.test_payments import _verifier

    storage_module = _storage(tmp_path)
    try:
        c = Clinic(client, email="erase-owner@example.com", name="Erase Clinic", payment_mode="pay_at_clinic")
        appt = c.staff_book(ist(c.monday, 9), customer={"full_name": "Asha Patel", "mobile": "9812345678", "email": "asha@example.com"})
        cust_id = c.get("/customers", {"search": "Asha"})["data"][0]["id"]
        c.post(f"/customers/{cust_id}/notes", {"body": "Allergic to penicillin", "note_type": "allergy"})
        c.post(f"/customers/{cust_id}/dependents", {"full_name": "Little Patel", "relationship_label": "child"})
        doc = client.post(f"/api/v1/customers/{cust_id}/documents", files={"file": ("r.png", io.BytesIO(PNG), "image/png")}, data={"title": "Blood report"}, headers=c.h).json()
        assert list(tmp_path.rglob("*.png"))

        # Only owners/admins may erase; it must be confirmed; upcoming visits block it.
        rec = _verifier(client, c, role="receptionist", mobile="9600000071")
        body = {"reason": "Written request from the customer", "confirm": True}
        assert client.post(f"/api/v1/customers/{cust_id}/anonymize", json=body, headers=rec).status_code == 403
        assert client.post(f"/api/v1/customers/{cust_id}/anonymize", json={**body, "confirm": False}, headers=c.h).json()["code"] == "confirmation_required"
        assert client.post(f"/api/v1/customers/{cust_id}/anonymize", json=body, headers=c.h).json()["code"] == "has_upcoming"
        assert client.post(f"/api/v1/appointments/{appt['id']}/status", json={"action": "cancel"}, headers=c.h).status_code == 200

        r = client.post(f"/api/v1/customers/{cust_id}/anonymize", json=body, headers=c.h)
        assert r.status_code == 200, r.text
        assert client.get(f"/api/v1/customers/{cust_id}", headers=c.h).status_code == 404
        assert c.get("/customers", {"search": "9812345678"})["meta"]["total"] == 0

        db.expire_all()
        row = db.scalars(select(Customer).where(Customer.public_id == cust_id)).one()
        assert (row.full_name, row.mobile, row.email, row.user_id) == ("Erased customer", None, None, None)
        assert db.scalars(select(CustomerNote).where(CustomerNote.customer_id == row.id)).all() == []
        assert all(d.full_name == "Erased" and d.deleted_at for d in row.dependents)
        assert db.scalars(select(CustomerDocument).where(CustomerDocument.public_id == doc["id"])).one().deleted_at is not None
        assert not list(tmp_path.rglob("*.png"))  # the file itself is gone
        for n in db.scalars(select(Notification).where(Notification.recipient_customer_id == row.id)).all():
            assert n.recipient_address is None and "Asha" not in n.body
        # The appointment (and its money trail) is kept, attached to the anonymous record.
        kept = c.get(f"/appointments/{appt['id']}")
        assert kept["status"] == "cancelled" and "Asha" not in str(kept)
        audit = db.scalars(select(AuditLog).where(AuditLog.action == "customer.anonymized")).one()
        assert audit.purpose == body["reason"] and "Asha" not in str(audit.before) + str(audit.after)
    finally:
        storage_module._storage = None
