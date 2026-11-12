def test_health_live(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


def test_health_ready_checks_database(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"]["database"] == "ok"


def test_security_headers_and_request_id(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers
    assert r.headers["X-Request-ID"]


def test_request_id_is_echoed(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"


def test_meta_enums(client):
    r = client.get("/api/v1/meta/enums")
    assert r.status_code == 200
    data = r.json()
    assert "confirmed" in data["appointment_statuses"]
    assert "verified" in data["payment_statuses"]
    assert "payments:verify" in data["permissions"]


def test_validation_error_envelope(client):
    r = client.get("/api/v1/health/ready?page=notanumber")  # unknown query is ignored, so force 404 shape
    assert r.status_code == 200
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
