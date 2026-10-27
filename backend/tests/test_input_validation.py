"""INPUT-001..004 / DB-003 / RATE-002: validation, injection resistance, data exposure."""

import time

from tests.conftest import (
    auth_headers,
    make_user,
    register_payload,
)

from app.services.rate_limit import InMemoryRateLimiter, MAX_TRACKED_KEYS


def test_register_rejects_missing_fields(client):
    response = client.post("/api/auth/register", json={})

    assert response.status_code == 422


def test_register_rejects_oversized_values(client):
    payload = register_payload("oversized@gmail.com")
    payload["name"] = "x" * 500

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


def test_search_input_cannot_break_sql(client):
    # Non-destructive injection probe: parameterized queries must return cleanly
    response = client.get("/api/listings", params={"search": "' OR 1=1 --"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_input_with_quotes_returns_cleanly(client):
    response = client.get("/api/needs", params={"search": "'; DROP TABLE users; --"})

    assert response.status_code == 200


def test_registration_response_has_no_password_hash(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload("nohash@gmail.com"),
    )

    assert response.status_code == 201
    assert "password_hash" not in response.json()


def test_profile_response_has_no_password_hash(client, db_session):
    user = make_user(db_session)

    response = client.get("/api/users/me", headers=auth_headers(user))

    assert response.status_code == 200
    assert "password_hash" not in response.json()


def test_errors_do_not_leak_internal_details(client):
    response = client.get("/api/listings/not-an-int")

    assert response.status_code == 422
    body = response.text.lower()
    assert "traceback" not in body
    assert "sqlalchemy" not in body


def test_rate_limiter_bounds_memory_under_key_rotation():
    limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60, name="memtest")

    for index in range(MAX_TRACKED_KEYS + 50):
        limiter._requests[f"ip:{index}"] = [time.time()]

    limiter._prune(time.time())

    assert len(limiter._requests) <= MAX_TRACKED_KEYS


def test_rate_limiter_window_expiry():
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=1, name="window")

    assert limiter.is_allowed("k") is True
    assert limiter.is_allowed("k") is True
    assert limiter.is_allowed("k") is False

    time.sleep(1.05)

    assert limiter.is_allowed("k") is True
