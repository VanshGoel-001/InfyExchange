"""API tests: registration, login and identity endpoints (tasks T05, T06, T07).

Existing tests in test_auth.py / test_authorization.py already cover token forgery,
Argon2 hashing, generic login errors and basic rate limiting; these add the
endpoint-level rules from the acceptance criteria.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.services import rate_limit
from app.services.auth import decode_access_token
from tests.conftest import auth_headers, make_user, register_payload

REGISTER = "/api/auth/register"
LOGIN = "/api/auth/login"
ME = "/api/auth/me"


def _register(client, email, **overrides):
    payload = register_payload(email)
    payload.update(overrides)
    return client.post(REGISTER, json=payload)


def _token(sub, minutes=5, key=None, algorithm="HS256"):
    claims = {"exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    if sub is not None:
        claims["sub"] = sub
    return jwt.encode(claims, key or settings.secret_key, algorithm=algorithm)


class TestRegisterApi:
    def test_success_returns_profile_without_secrets(self, client):
        """TC-API-REG-001 | AC-01.1, AC-01.6 | T05 | positive | 201 with profile; role/date echoed; non-admin, active; no password data"""
        response = _register(client, "asha@gmail.com", name="Asha Rao", role="DSE", joining_date="2026-02-03")
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "asha@gmail.com"
        assert body["name"] == "Asha Rao"
        assert body["role"] == "DSE"
        assert body["joining_date"] == "2026-02-03"
        assert body["is_admin"] is False
        assert body["is_active"] is True
        assert isinstance(body["id"], int)
        assert "password" not in body and "password_hash" not in body

    def test_password_is_stored_as_argon2_hash(self, client, db_session):
        """TC-API-REG-002 | AC-01.4, AC-19.6 | T05 | positive | persisted password is an Argon2id hash, not the submitted text"""
        _register(client, "hash@gmail.com", password="Passw0rd1")
        user = db_session.scalar(select(User).where(User.email == "hash@gmail.com"))
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != "Passw0rd1"

    def test_email_is_stored_lowercase(self, client):
        """TC-API-REG-003 | AC-01.2 | T05 | business | mixed-case email (and domain) is normalised to lowercase"""
        response = _register(client, "Mixed.Case@GMAIL.com")
        assert response.status_code == 201
        assert response.json()["email"] == "mixed.case@gmail.com"

    def test_name_and_phone_are_trimmed(self, client):
        """TC-API-REG-004 | AC-01.5 | T05 | business | surrounding whitespace is stripped from name and phone before saving"""
        response = _register(client, "trim@gmail.com", name="  Asha  ", phone="  9876543210  ")
        assert response.status_code == 201
        assert response.json()["name"] == "Asha"
        assert response.json()["phone"] == "9876543210"

    def test_client_cannot_self_assign_admin(self, client):
        """TC-API-REG-005 | AC-01.6 | T05 | negative | is_admin / is_active in the request body are ignored"""
        response = _register(client, "sneaky@gmail.com", is_admin=True, is_active=False)
        assert response.status_code == 201
        assert response.json()["is_admin"] is False
        assert response.json()["is_active"] is True

    def test_registered_user_can_log_in_immediately(self, client):
        """TC-API-REG-006 | AC-01.1, AC-02.1 | T05 | business | the new credentials work at /login straight away"""
        _register(client, "fresh@gmail.com", password="Passw0rd1")
        response = client.post(LOGIN, json={"email": "fresh@gmail.com", "password": "Passw0rd1"})
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "email",
        ["user@yahoo.com", "user@gmail.com.evil.com", "user@evilgmail.com", "user@sub.gmail.com"],
    )
    def test_non_allowed_domains_are_rejected(self, client, email):
        """TC-API-REG-007 | AC-01.2 | T05 | negative | other domains, look-alikes and sub-domains of gmail.com get 400"""
        response = _register(client, email)
        assert response.status_code == 400
        assert response.json()["detail"] == "Only Gmail addresses are allowed"

    def test_multiple_allowed_domains_are_supported(self, client, monkeypatch):
        """TC-API-REG-008 | AC-01.2 | T05 | business | with several configured domains each is accepted and the error lists them"""
        monkeypatch.setattr(settings, "allowed_email_domains", "company.org, partner.org")
        assert _register(client, "a@partner.org").status_code == 201
        rejected = _register(client, "b@gmail.com")
        assert rejected.status_code == 400
        assert "@company.org" in rejected.json()["detail"]
        assert "@partner.org" in rejected.json()["detail"]

    def test_empty_domain_setting_falls_back_to_gmail(self, client, monkeypatch):
        """TC-API-REG-009 | AC-01.2 | T05 | boundary | an empty ALLOWED_EMAIL_DOMAINS behaves as gmail.com only"""
        monkeypatch.setattr(settings, "allowed_email_domains", "")
        assert _register(client, "ok@gmail.com").status_code == 201
        assert _register(client, "no@yahoo.com").status_code == 400

    def test_duplicate_email_conflicts(self, client):
        """TC-API-REG-010 | AC-01.3 | T05 | negative | a second registration with the same email gets 409"""
        assert _register(client, "dup@gmail.com").status_code == 201
        response = _register(client, "dup@gmail.com")
        assert response.status_code == 409
        assert response.json()["detail"] == "Email already registered"

    def test_duplicate_email_is_case_insensitive(self, client):
        """TC-API-REG-011 | AC-01.3 | T05 | boundary | DUP@gmail.com collides with dup@gmail.com"""
        assert _register(client, "dup2@gmail.com").status_code == 201
        assert _register(client, "DUP2@GMAIL.COM").status_code == 409

    def test_duplicate_phone_conflicts(self, client):
        """TC-API-REG-012 | AC-01.3 | T05 | negative | a different email with an already-used phone gets 409"""
        assert _register(client, "p1@gmail.com", phone="9990001112").status_code == 201
        response = _register(client, "p2@gmail.com", phone="9990001112")
        assert response.status_code == 409
        assert response.json()["detail"] == "Phone number already registered"

    def test_failed_registration_creates_no_user(self, client, db_session):
        """TC-API-REG-013 | AC-01.3, AC-19.1 | T05 | business | a rejected registration leaves no row behind"""
        _register(client, "someone@yahoo.com")
        assert db_session.scalar(select(User).where(User.email == "someone@yahoo.com")) is None


class TestLoginApi:
    def test_valid_credentials_return_bearer_token_for_user(self, client, db_session):
        """TC-API-LOG-001 | AC-02.1 | T05 | positive | 200 with a bearer token whose subject is the user's id"""
        user = make_user(db_session, email="login@gmail.com", password="Passw0rd1")
        response = client.post(LOGIN, json={"email": "login@gmail.com", "password": "Passw0rd1"})
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert decode_access_token(body["access_token"]) == user.id

    def test_returned_token_authenticates_me(self, client, db_session):
        """TC-API-LOG-002 | AC-02.1, AC-03.1 | T05 | positive | the issued token is accepted by /api/auth/me"""
        make_user(db_session, email="me@gmail.com", password="Passw0rd1")
        token = client.post(LOGIN, json={"email": "me@gmail.com", "password": "Passw0rd1"}).json()["access_token"]
        response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == "me@gmail.com"

    def test_unknown_email_and_wrong_password_return_same_401(self, client, db_session):
        """TC-API-LOG-003 | AC-02.2 | T05 | negative | unknown account and wrong password give the same status and message"""
        make_user(db_session, email="known@gmail.com", password="Passw0rd1")
        unknown = client.post(LOGIN, json={"email": "ghost@gmail.com", "password": "Passw0rd1"})
        wrong = client.post(LOGIN, json={"email": "known@gmail.com", "password": "Wrongpass1"})
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json() == {"detail": "Invalid email or password"}

    def test_email_is_case_insensitive(self, client, db_session):
        """TC-API-LOG-004 | AC-02.3 | T05 | boundary | logging in with an upper-case email succeeds"""
        make_user(db_session, email="case@gmail.com", password="Passw0rd1")
        response = client.post(LOGIN, json={"email": "CASE@GMAIL.COM", "password": "Passw0rd1"})
        assert response.status_code == 200

    def test_exactly_ten_attempts_allowed_then_429(self, client, db_session):
        """TC-API-LOG-005 | AC-02.4 | T05 | boundary | the 10th login in a window passes and the 11th is throttled"""
        make_user(db_session, email="burst@gmail.com", password="Passw0rd1")
        body = {"email": "burst@gmail.com", "password": "Passw0rd1"}
        assert [client.post(LOGIN, json=body).status_code for _ in range(10)] == [200] * 10
        response = client.post(LOGIN, json=body)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == str(settings.rate_limit_window_seconds)

    def test_per_account_limit_applies_across_ips(self, client, db_session):
        """TC-API-LOG-006 | AC-02.4 | T05 | negative | once the per-IP counter is cleared the per-account limit still blocks the same email"""
        make_user(db_session, email="target@gmail.com", password="Passw0rd1")
        body = {"email": "target@gmail.com", "password": "Wrongpass1"}
        for _ in range(10):
            client.post(LOGIN, json=body)
        rate_limit.login_limiter._requests.clear()  # simulate attempts arriving from a fresh IP
        response = client.post(LOGIN, json=body)
        assert response.status_code == 429
        assert "this account" in response.json()["detail"]

    def test_other_accounts_are_not_blocked_by_one_account_limit(self, client, db_session):
        """TC-API-LOG-007 | AC-02.4 | T05 | business | exhausting one account's limit does not lock out a different account"""
        make_user(db_session, email="victim@gmail.com", password="Passw0rd1")
        make_user(db_session, email="other@gmail.com", password="Passw0rd1")
        for _ in range(10):
            client.post(LOGIN, json={"email": "victim@gmail.com", "password": "Wrongpass1"})
        rate_limit.login_limiter._requests.clear()
        response = client.post(LOGIN, json={"email": "other@gmail.com", "password": "Passw0rd1"})
        assert response.status_code == 200

    def test_password_longer_than_100_is_rejected(self, client):
        """TC-API-LOG-008 | AC-02.2 | T05 | boundary | a 101-character password is a 422, not a hash comparison"""
        response = client.post(LOGIN, json={"email": "x@gmail.com", "password": "a" * 101})
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "body",
        [{"email": "x@gmail.com"}, {"password": "Passw0rd1"}, {"email": "not-an-email", "password": "Passw0rd1"}, {}],
        ids=["no-password", "no-email", "bad-email", "empty"],
    )
    def test_malformed_login_bodies_are_422(self, client, body):
        """TC-API-LOG-009 | AC-02.2 | T05 | negative | missing or malformed fields are rejected before any lookup"""
        assert client.post(LOGIN, json=body).status_code == 422


class TestIdentityApi:
    def test_me_endpoints_return_same_profile(self, client, db_session):
        """TC-API-IDN-001 | AC-03.1 | T06, T07 | positive | /api/auth/me and /api/users/me return the caller's profile"""
        user = make_user(db_session)
        first = client.get(ME, headers=auth_headers(user)).json()
        second = client.get("/api/users/me", headers=auth_headers(user)).json()
        assert first == second
        assert first["id"] == user.id
        assert "password_hash" not in first

    def test_expired_token_is_401(self, client, db_session):
        """TC-API-IDN-002 | AC-03.2 | T06 | negative | an expired token yields 401 'Invalid or expired token'"""
        user = make_user(db_session)
        response = client.get(ME, headers={"Authorization": f"Bearer {_token(str(user.id), minutes=-1)}"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired token"

    def test_token_for_deleted_user_is_401(self, client, db_session):
        """TC-API-IDN-003 | AC-03.2 | T06 | negative | a valid token whose user no longer exists yields 401 'User not found'"""
        user = make_user(db_session)
        headers = auth_headers(user)
        db_session.delete(user)
        db_session.commit()
        response = client.get(ME, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "User not found"

    @pytest.mark.parametrize(
        "token",
        [_token("not-a-number"), _token(None), _token("1", key="some-other-secret-key-value-123456")],
        ids=["non-numeric-sub", "missing-sub", "wrong-secret"],
    )
    def test_structurally_invalid_tokens_are_401(self, client, token):
        """TC-API-IDN-004 | AC-03.2 | T06 | negative | tokens with a bad subject or bad signature never authenticate"""
        response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_non_bearer_scheme_is_rejected(self, client, db_session):
        """TC-API-IDN-005 | AC-03.2 | T06 | negative | 'Basic' credentials are not accepted as a token"""
        response = client.get(ME, headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code in (401, 403)

    def test_deactivated_user_gets_403_with_message(self, client, db_session):
        """TC-API-IDN-006 | AC-03.3 | T06 | negative | a deactivated account is refused with 403 and an explanatory message"""
        user = make_user(db_session, is_active=False)
        response = client.get("/api/users/me", headers=auth_headers(user))
        assert response.status_code == 403
        assert "deactivated" in response.json()["detail"].lower()
