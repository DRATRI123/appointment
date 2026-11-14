"""Route handlers that use the database must be plain `def` functions.

FastAPI runs `def` handlers in a worker thread but `async def` handlers on the event loop. Our database session is
synchronous, so an `async def` handler that touches it blocks the event loop while it waits for a lock. If the request
holding that lock needs the event loop to finish (every request does), the server deadlocks until the database's
lock timeout: "database is locked" on SQLite, a statement timeout on PostgreSQL. This happened with the UTR submission
endpoint under parallel load.
"""
from __future__ import annotations

import inspect

from fastapi.routing import APIRoute

from app.core.database import get_db
from app.main import app


def _uses_db(dependant) -> bool:
    return any(d.call is get_db or _uses_db(d) for d in dependant.dependencies)


def _api_routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        nested = getattr(route, "original_router", None) or getattr(route, "router", None)  # included routers
        if nested is not None and nested is not route:
            yield from _api_routes(nested.routes)


def test_database_routes_are_not_coroutines():
    routes = list(_api_routes(app.routes))
    db_routes = [route for route in routes if _uses_db(route.dependant)]
    assert len(db_routes) > 100, "route discovery broke; the check below would pass vacuously"
    offenders = [
        f"{','.join(sorted(route.methods))} {route.path} ({route.endpoint.__module__}.{route.endpoint.__name__})"
        for route in db_routes
        if inspect.iscoroutinefunction(inspect.unwrap(route.endpoint)) or inspect.iscoroutinefunction(route.endpoint)
    ]
    assert offenders == [], "Use `def`, not `async def`, for handlers that use the database:\n" + "\n".join(offenders)
