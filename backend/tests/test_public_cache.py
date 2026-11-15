"""The public catalogue cache: served from memory for a few seconds, and emptied as soon as the catalogue changes."""
from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core import public_cache
from app.core.config import Settings, get_settings
from app.core.database import build_engine
from app.models import Base, Organization


@pytest.fixture()
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_cache_seconds", 30)
    public_cache.clear()
    engine = build_engine(Settings(_env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path / 'cache.db'}"))
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    public_cache.clear()
    engine.dispose()


def test_cached_until_the_catalogue_changes(factory):
    calls = []

    @public_cache.cached("probe")
    def endpoint(slug: str, db=None):
        calls.append(slug)
        return {"slug": slug, "n": len(calls)}

    first = endpoint(slug="clinic", db=object())
    second = endpoint(slug="clinic", db=object())
    assert json.loads(first.body) == json.loads(second.body) == {"slug": "clinic", "n": 1}
    endpoint(slug="other", db=object())
    assert calls == ["clinic", "other"]  # cached per parameters

    with factory() as db:  # a change that is rolled back keeps the cache
        db.add(Organization(slug="x", code="X", name="X Clinic"))
        db.flush()
        db.rollback()
    endpoint(slug="clinic", db=object())
    assert calls == ["clinic", "other"]

    with factory() as db:  # a committed catalogue change empties it at once
        db.add(Organization(slug="y", code="Y", name="Y Clinic"))
        db.commit()
    assert json.loads(endpoint(slug="clinic", db=object()).body)["n"] == 3


def test_turned_off_with_zero(monkeypatch):
    monkeypatch.setattr(get_settings(), "public_cache_seconds", 0)
    calls = []

    @public_cache.cached("probe-off")
    def endpoint(slug: str):
        calls.append(slug)
        return {"ok": True}

    endpoint(slug="a")
    endpoint(slug="a")
    assert calls == ["a", "a"]
