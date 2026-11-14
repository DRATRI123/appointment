"""S3-compatible storage: uploads, private files and /media streaming from a private bucket."""
from __future__ import annotations

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.core import storage as storage_module
from app.core.config import Settings
from app.core.exceptions import ValidationFailed
from app.main import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture()
def bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(Bucket="clinic-files", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
        store = storage_module.S3Storage(client, "clinic-files", prefix="prod")
        storage_module._storage = store
        try:
            yield client, store
        finally:
            storage_module._storage = None


def test_files_round_trip_under_the_prefix_and_are_encrypted_at_rest(bucket):
    client, store = bucket
    public = store.save(scope="org/1", visibility="public", data=PNG, mime_type="image/png")
    private = store.save(scope="org/1/payments", visibility="private", data=b"%PDF-1.4 receipt", mime_type="application/pdf")
    assert public.url.startswith("/media/org/1/") and private.url is None
    head = client.head_object(Bucket="clinic-files", Key=f"prod/{private.key}")
    assert head["ContentType"] == "application/pdf" and head["ServerSideEncryption"] == "AES256"
    assert store.open(private.key).read() == b"%PDF-1.4 receipt"
    store.delete(private.key)
    with pytest.raises(FileNotFoundError):
        store.open(private.key)
    with pytest.raises(ValidationFailed):
        store.open("public/../private/x.pdf")


def test_media_is_streamed_from_the_private_bucket_and_never_exposes_private_files(bucket):
    _, store = bucket
    public = store.save(scope="org/1", visibility="public", data=PNG, mime_type="image/png")
    private = store.save(scope="org/1/payments", visibility="private", data=PNG, mime_type="image/png")
    app = create_app(Settings(_env_file=None, app_env="test", storage_backend="s3", s3_bucket="clinic-files"))
    with TestClient(app) as c:
        r = c.get(public.url)
        assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert c.get("/media/" + private.key).status_code == 404  # "private/..." is looked up under public/
        assert c.get("/media/../" + private.key).status_code == 404
        assert c.get("/media/org/1/missing.png").status_code == 404
