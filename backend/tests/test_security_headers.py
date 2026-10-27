"""WEB-001..005 / NET backend-level checks: headers, CORS, correlation IDs, caching."""

from app.config import settings


def test_security_headers_present(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in response.headers
    assert "Permissions-Policy" in response.headers
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_hsts_absent_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "hsts_enabled", False)

    response = client.get("/health")

    assert "Strict-Transport-Security" not in response.headers


def test_hsts_present_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "hsts_enabled", True)
    monkeypatch.setattr(settings, "hsts_max_age", 300)

    response = client.get("/health")

    assert response.headers["Strict-Transport-Security"] == "max-age=300"


def test_csp_exempts_docs_paths(client):
    # Documentation endpoints render pages that need remote assets;
    # they must not receive the strict JSON API CSP.
    response = client.get("/openapi.json")

    assert "Content-Security-Policy" not in response.headers


def test_request_id_is_returned(client):
    response = client.get("/health")

    assert response.headers.get("X-Request-ID")


def test_request_id_is_not_echoed_when_malformed(client):
    response = client.get(
        "/health",
        headers={"X-Request-ID": "bad id with spaces!"},
    )

    request_id = response.headers.get("X-Request-ID")
    assert request_id and " " not in request_id


def test_cors_allows_configured_origin(client):
    response = client.get(
        "/api/listings",
        headers={"Origin": "http://allowed.example"},
    )

    assert response.headers.get("access-control-allow-origin") == "http://allowed.example"


def test_cors_blocks_unknown_origin_preflight(client):
    response = client.options(
        "/api/listings",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_cors_rejects_wildcard_with_credentials(client):
    # Regression guard: allow_origins must never contain "*"
    assert "*" not in settings.cors_origin_list


def test_sensitive_endpoints_not_cached(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@gmail.com", "password": "wrongpass1"},
    )

    assert response.headers.get("Cache-Control") == "no-store"
