"""At-rest encryption: private files, sensitive booking-form answers, payer details, family-member notes, and the
one-time migration of records saved before encryption covered them."""
from __future__ import annotations

import io

import pytest
from sqlalchemy import Text, cast, select

from app.models import BookingFormResponse, CustomerDependent, CustomerDocument, PaymentSubmission
from app.security.crypto import DecryptionError, decrypt_bytes, encrypt_bytes, is_encrypted, is_encrypted_blob, purpose_key
from tests.booking_helpers import Clinic, ist
from tests.helpers import bearer, otp_login

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def storage(tmp_path):
    from app.core import storage as storage_module

    storage_module._storage = storage_module.EncryptingStorage(storage_module.LocalStorage(tmp_path))
    yield tmp_path
    storage_module._storage = None


def test_file_encryption_roundtrip_tamper_and_key_separation():
    blob = encrypt_bytes(b"lab report")
    assert is_encrypted_blob(blob) and b"lab report" not in blob
    assert decrypt_bytes(blob) == b"lab report"
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(DecryptionError, match="modified"):
        decrypt_bytes(tampered)
    with pytest.raises(DecryptionError):
        decrypt_bytes(blob, purpose="other")  # a key for one purpose cannot open another's data
    key = b"k" * 32
    assert purpose_key(key, "files") != purpose_key(key, "audit") != key
    assert decrypt_bytes(b"plain old file") == b"plain old file"  # files from before encryption stay readable


def test_patient_documents_are_encrypted_on_disk_and_readable_through_the_app(client, db, storage):
    c = Clinic(client, email="enc-doc@example.com", name="Enc Doc Clinic", payment_mode="pay_at_clinic")
    cust = c.post("/customers", {"full_name": "Doc Patient", "mobile": "9811100001"})
    r = client.post(f"/api/v1/customers/{cust['id']}/documents", files={"file": ("r.png", io.BytesIO(PNG), "image/png")},
                    data={"title": "X-ray", "document_type": "report"}, headers=c.h)
    assert r.status_code == 201, r.text
    row = db.scalar(select(CustomerDocument).where(CustomerDocument.public_id == r.json()["id"]))
    on_disk = (storage / row.storage_path).read_bytes()
    assert is_encrypted_blob(on_disk) and PNG not in on_disk
    assert row.size_bytes == len(PNG)  # the document's own size and checksum, not the ciphertext's
    dl = client.get(f"/api/v1/customers/{cust['id']}/documents/{r.json()['id']}/download", headers=c.h)
    assert dl.status_code == 200 and dl.content == PNG


def test_sensitive_form_answers_are_encrypted_and_hidden_without_clinical_access(client, db, storage):
    c = Clinic(client, email="enc-form@example.com", name="Enc Form Clinic", payment_mode="pay_at_clinic")
    form = c.post("/booking-forms", {"name": "Intake", "fields": [
        {"key": "reason", "label": "Reason for visit", "field_type": "text"},
        {"key": "history", "label": "Medical history", "field_type": "textarea", "is_sensitive": True},
    ]})
    c.post(f"/booking-forms/{form['id']}/publish", {}, expect=200)
    hold = c.public_hold(ist(c.monday, 9), session_key="ef")
    appt = c.public_book(hold["id"], session_key="ef", customer={"full_name": "Form Patient", "mobile": "9811100002"},
                         form_answers={"reason": "Back pain", "history": "Diabetes since 2019"})
    raw = db.scalar(select(BookingFormResponse))
    assert raw.answers["reason"] == "Back pain"
    assert set(raw.answers["history"]) == {"enc"} and is_encrypted(raw.answers["history"]["enc"])
    assert "Diabetes" not in str(raw.answers)

    # The owner has clinical access: sees the answer. A receptionist does not.
    owner_view = c.get(f"/booking-forms/responses/by-appointment/{appt['id']}")
    assert owner_view["answers"]["history"] == "Diabetes since 2019"
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9622200001", "full_name": "Desk", "role_code": "receptionist"})
    desk = {**bearer(otp_login(client, "9622200001")), "X-Organization-Id": c.org["id"]}
    client.cookies.clear()
    for path in (f"/api/v1/booking-forms/responses/by-appointment/{appt['id']}", f"/api/v1/appointments/{appt['id']}"):
        body = client.get(path, headers=desk).json()
        answers = body.get("answers") or body.get("form_answers")
        assert answers["reason"] == "Back pain" and answers["history"] == "Hidden: clinical access needed", path
        assert "Diabetes" not in str(body)


def test_payer_details_and_family_notes_are_encrypted_at_rest(client, db, storage):
    c = Clinic(client, email="enc-pay@example.com", name="Enc Pay Clinic")
    c.post("/upi-accounts", {"display_name": "Main", "upi_id": "encpay@okhdfcbank", "merchant_name": "Enc Pay"})
    hold = c.public_hold(ist(c.monday, 9), session_key="ep")
    appt = c.public_book(hold["id"], session_key="ep", customer={"full_name": "Payer", "mobile": "9811100003"})
    r = client.post(f"/api/v1/public/organizations/{c.org['slug']}/appointments/{appt['reference']}/payment/submit",
                    params={"access_token": appt["access_token"]}, data={"utr": "412345678909", "payer_upi_id": "asha@oksbi"})
    assert r.status_code == 200, r.text
    stored = db.execute(select(cast(PaymentSubmission.__table__.c.payer_upi_id, Text))).scalar_one()
    assert is_encrypted(stored) and "asha" not in stored
    assert db.scalar(select(PaymentSubmission)).payer_upi_id == "asha@oksbi"  # the app still reads it

    user = otp_login(client, "9811100004", "Parent")
    client.cookies.clear()
    hu = bearer(user)
    r = client.post("/api/v1/me/dependents", json={"full_name": "Child", "relationship_label": "child", "notes": "Asthma inhaler"}, headers=hu)
    if r.status_code == 404:  # dependents created by staff instead
        cust = c.post("/customers", {"full_name": "Parent Two", "mobile": "9811100005"})
        r = client.post(f"/api/v1/customers/{cust['id']}/dependents", json={"full_name": "Child", "notes": "Asthma inhaler"}, headers=c.h)
    assert r.status_code == 201, r.text
    raw_note = db.execute(select(cast(CustomerDependent.__table__.c.notes, Text)).where(CustomerDependent.__table__.c.notes.is_not(None))).scalar_one()
    assert is_encrypted(raw_note) and "Asthma" not in raw_note


def test_one_time_migration_encrypts_old_plain_records_and_files(client, db, storage, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy import text as sql_text

    from app.core.storage import get_storage
    from app.ops import rotate_keys
    from app.ops.rotate_keys import rotate

    @contextmanager
    def same_session():  # the tests share one uncommitted session; the command must see it
        yield db
        db.flush()

    monkeypatch.setattr(rotate_keys, "session_scope", same_session)

    c = Clinic(client, email="enc-mig@example.com", name="Enc Mig Clinic", payment_mode="pay_at_clinic")
    cust = c.post("/customers", {"full_name": "Old Patient", "mobile": "9811100006"})
    r = client.post(f"/api/v1/customers/{cust['id']}/dependents", json={"full_name": "Kid", "notes": "Peanut allergy"}, headers=c.h)
    assert r.status_code == 201, r.text
    # Simulate rows and a file saved before encryption existed.
    db.execute(sql_text("UPDATE customer_dependents SET notes = 'Peanut allergy'"))  # raw: bypasses the encrypted type
    old_file = storage / "private" / "documents" / "aa" / "old.png"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_bytes(PNG)
    db.flush()

    dry = rotate(dry_run=True)
    assert dry["customer_dependents.notes"]["reencrypted"] == 1 and dry["private files"]["reencrypted"] >= 1
    assert old_file.read_bytes() == PNG  # dry run changes nothing
    report = rotate()
    assert report["customer_dependents.notes"]["failed"] == 0 and report["private files"]["failed"] == 0
    assert is_encrypted_blob(old_file.read_bytes())
    assert get_storage().open("private/documents/aa/old.png").read() == PNG
    db.expire_all()
    raw_note = db.execute(select(cast(CustomerDependent.__table__.c.notes, Text))).scalar_one()
    assert is_encrypted(raw_note)
    again = rotate(dry_run=True)
    assert all(v["reencrypted"] == 0 for v in again.values())  # idempotent
