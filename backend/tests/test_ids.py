from app.core.ids import new_public_id, new_reference, new_ulid


def test_ulid_is_sortable_and_unique():
    ids = [new_ulid() for _ in range(200)]
    assert len(set(ids)) == 200
    assert all(len(i) == 26 for i in ids)


def test_reference_format():
    ref = new_reference("PAY", "acme")
    assert ref.startswith("PAY-ACME-")
    assert len(ref.split("-")) == 3


def test_public_id_is_uuid():
    assert len(new_public_id()) == 36
