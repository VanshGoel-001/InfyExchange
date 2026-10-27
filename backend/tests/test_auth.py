"""AUTH-001..005 / RATE-001: authentication, password policy, and login abuse controls."""

from tests.conftest import (
    auth_headers,
    make_user,
    register_payload,
)

from app.config import settings


def test_unauthenticated_access_denied(client):
    response = client.get("/api/users/me")

    assert response.status_code in (401, 403)


def test_invalid_token_rejected(client):
    response = client.get(
        "/api/users/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_alg_none_token_rejected(client):
    # Forged token without signature must never be accepted (algorithm pinning)
    forged = (
        "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
        "eyJzdWIiOiIxIn0."
    )

    response = client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


def test_deactivated_user_rejected(client, db_session):
    user = make_user(db_session, is_active=False)

    response = client.get(
        "/api/users/me",
        headers=auth_headers(user),
    )

    assert response.status_code == 403


def test_login_failure_messages_are_identical(client, db_session):
    user = make_user(db_session, email="known@gmail.com")

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "Wrong0pass"},
    )

    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "unknown@gmail.com", "password": "Wrong0pass"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_login_success_returns_bearer_token(client, db_session):
    user = make_user(db_session, email="login-ok@gmail.com")

    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "Passw0rd1"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_password_hash_uses_argon2id(db_session):
    user = make_user(db_session, email="hash-format@gmail.com")

    assert user.password_hash.startswith("$argon2id$")


def test_password_policy_rejects_letters_only(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload("letters-only@gmail.com", password="onlyletters"),
    )

    assert response.status_code == 422


def test_password_policy_rejects_short_password(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload("short-pass@gmail.com", password="a1b2c3"),
    )

    assert response.status_code == 422


def test_registration_succeeds_with_strong_password(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload("strong-pass@gmail.com", password="Passw0rd1"),
    )

    assert response.status_code == 201


def test_registration_rejects_disallowed_email_domain(client):
    response = client.post(
        "/api/auth/register",
        json=register_payload("user@example.com"),
    )

    assert response.status_code == 400


def test_login_rate_limit_returns_429_with_retry_after(client):
    payload = {"email": "bruteforce@gmail.com", "password": "Wrong0pass"}

    statuses = [
        client.post("/api/auth/login", json=payload).status_code
        for _ in range(settings.rate_limit_login + 1)
    ]

    assert 429 in statuses
    assert statuses[-1] == 429

    limited = client.post("/api/auth/login", json=payload)
    assert limited.headers.get("Retry-After") == str(settings.rate_limit_window_seconds)


def test_registration_rate_limit_returns_429(client):
    statuses = []

    for index in range(settings.rate_limit_register + 1):
        response = client.post(
            "/api/auth/register",
            json=register_payload(f"flood-{index}@gmail.com"),
        )
        statuses.append(response.status_code)

    assert 429 in statuses
