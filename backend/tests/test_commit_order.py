"""The database commit must happen BEFORE the response is sent.

Otherwise a client can be told "201 Created" for data whose commit then fails, and its next request (often served by
another process) may not see what it just created. TestClient waits for the whole request lifecycle, so it cannot show
the ordering; this test drives the ASGI app directly and watches the order of events.
"""
from __future__ import annotations

import asyncio
from collections.abc import Generator

from app.api.deps import DB
from app.core.database import get_db
from app.main import create_app


class _FakeSession:
    def __init__(self, events: list[str]):
        self.events = events

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.events.append("close")

    def execute(self, *a, **k):  # the health route does not query; anything else fails loudly
        raise AssertionError("unexpected query")


def test_commit_happens_before_the_response_starts():
    events: list[str] = []
    app = create_app()

    def fake_db() -> Generator[_FakeSession, None, None]:  # same shape as get_db
        db = _FakeSession(events)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    app.dependency_overrides[get_db] = fake_db

    @app.post("/probe")
    def probe(db: DB) -> dict:
        events.append("handler")
        return {"ok": True}

    box: dict = {}

    async def run():
        scope = {"type": "http", "method": "POST", "path": "/probe", "raw_path": b"/probe", "query_string": b"", "headers": [(b"host", b"testserver")],
                 "client": ("127.0.0.1", 1), "server": ("testserver", 80), "scheme": "http", "http_version": "1.1", "root_path": ""}
        sent = False
        statuses: list[int] = []
        box["statuses"] = statuses

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.sleep(3600)

        async def send(message):
            if message["type"] == "http.response.start":
                events.append("response")
                statuses.append(message["status"])
            elif message["type"] == "http.response.body":
                box.setdefault("body", b"")
                box["body"] += message.get("body", b"")

        async with asyncio.timeout(10):
            lifespan = app.router.lifespan_context(app)
            async with lifespan:
                await app(scope, receive, send)

    asyncio.run(run())
    assert box["statuses"] == [200], (box, events)
    assert events.index("handler") < events.index("commit") < events.index("response"), events
