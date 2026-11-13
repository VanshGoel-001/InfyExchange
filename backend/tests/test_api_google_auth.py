"""API tests: Sign in with Google (POST /api/auth/google) and the profile-completion gate.

Google's servers are never contacted: the token verifier is replaced by a stub that
returns the claims a real, valid token would carry. The verifier itself (signature,
audience, expiry...) is covered in test_service_google.py.

AC-21.x = Google sign-in; AC-22.x = profile completion. These are additions made after
the derived baseline in test.md was written (see "Additions" there).
"""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import User
from app.services.google import GoogleNotConfigured, GoogleTokenError, GoogleUnavailable
from tests.conftest import auth_headers, make_listing, make_user
from tests.support import install_fake_cloudinary, listing_form, need_payload

GOOGLE = "/api/auth/google"
ME = "/api/auth/me"


def _claims(**overrides) -> dict:
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-1",
        "email": "newcomer@gmail.com",
        "email_verified": True,
        "name": "New Comer",
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def sign_in_as(monkeypatch):
    """Make the verifier accept any credential and return the given claims."""

    def _install(**overrides):
        claims = _claims(**overrides)
        monkeypatch.setattr("app.routers.auth.verify_google_id_token", lambda credential: claims)
        return claims

    return _install


def _post(client, credential="any-credential"):
    return client.post(GOOGLE, json={"credential": credential})


def _count_users(db) -> int:
    return db.scalar(select(func.count()).select_from(User))


class TestFirstSignIn:
    def test_creates_account_and_returns_a_token(self, client, db_session, sign_in_as):
        """TC-API-GGL-001 | AC-21.1 | T05 | positive | first Google sign-in creates the user and returns a bearer token"""
        sign_in_as()
        response = _post(client)
        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"
        user = db_session.scalar(select(User))
        assert (user.email, user.name, user.google_sub) == ("newcomer@gmail.com", "New Comer", "google-sub-1")

    def test_new_account_has_no_password_and_an_incomplete_profile(self, client, db_session, sign_in_as):
        """TC-API-GGL-002 | AC-21.1, AC-22.1 | T05 | business | the account starts without password, phone, role or joining date"""
        sign_in_as()
        token = _post(client).json()["access_token"]
        body = client.get(ME, headers={"Authorization": f"Bearer {token}"}).json()
        assert body["profile_complete"] is False
        assert (body["phone"], body["role"], body["joining_date"]) == (None, None, None)
        assert db_session.scalar(select(User)).password_hash is None

    def test_email_is_stored_in_lowercase(self, client, db_session, sign_in_as):
        """TC-API-GGL-003 | AC-21.1 | T05 | boundary | mixed-case addresses are normalised"""
        sign_in_as(email="Mixed.Case@Gmail.com")
        _post(client)
        assert db_session.scalar(select(User)).email == "mixed.case@gmail.com"

    @pytest.mark.parametrize("name, expected", [
        ("", "newcomer"),               # blank name: use the part before @
        (None, "newcomer"),
        ("A", "newcomer"),              # shorter than the 2-character minimum
        ("  Padded Name  ", "Padded Name"),
        ("N" * 150, "N" * 100),         # longer than the column: truncated
    ])
    def test_display_name_is_always_valid(self, client, db_session, sign_in_as, name, expected):
        """TC-API-GGL-004 | AC-21.1 | T05 | boundary | the stored name always satisfies the 2-100 character rule"""
        sign_in_as(name=name)
        _post(client)
        assert db_session.scalar(select(User)).name == expected

    def test_tiny_mailbox_name_falls_back_to_generic_name(self, client, db_session, sign_in_as):
        """TC-API-GGL-005 | AC-21.1 | T05 | boundary | a one-letter mailbox and no name still yields a valid name"""
        sign_in_as(email="a@gmail.com", name=None)
        _post(client)
        assert db_session.scalar(select(User)).name == "Google user"


class TestReturningSignIn:
    def test_second_sign_in_reuses_the_account(self, client, db_session, sign_in_as):
        """TC-API-GGL-010 | AC-21.2 | T05 | positive | the same Google account maps to one user, never two"""
        sign_in_as()
        first = _post(client)
        second = _post(client)
        assert first.status_code == second.status_code == 200
        assert _count_users(db_session) == 1

    def test_user_is_matched_by_google_id_even_if_email_changed(self, client, db_session, sign_in_as):
        """TC-API-GGL-011 | AC-21.2 | T05 | business | a changed Google email does not create a second account"""
        sign_in_as()
        _post(client)
        sign_in_as(email="renamed@gmail.com")
        assert _post(client).status_code == 200
        assert _count_users(db_session) == 1

    def test_deactivated_user_is_refused(self, client, db_session, sign_in_as):
        """TC-API-GGL-012 | AC-21.2, AC-14.1 | T05 | negative | a deactivated Google account gets 403 and no token"""
        sign_in_as()
        _post(client)
        db_session.scalar(select(User)).is_active = False
        db_session.commit()
        response = _post(client)
        assert response.status_code == 403
        assert "access_token" not in response.json()


class TestRefusals:
    def test_existing_password_account_is_not_merged(self, client, db_session, sign_in_as):
        """TC-API-GGL-020 | AC-21.3 | T05 | business | an address already registered with a password gets 409, not an account takeover"""
        existing = make_user(db_session, email="newcomer@gmail.com")
        sign_in_as()
        response = _post(client)
        assert response.status_code == 409
        assert "log in with your password" in response.json()["detail"]
        db_session.refresh(existing)
        assert existing.google_sub is None
        assert _count_users(db_session) == 1

    def test_email_domain_policy_applies(self, client, db_session, sign_in_as):
        """TC-API-GGL-021 | AC-21.4, AC-01.2 | T05 | negative | addresses outside the allowed domains cannot sign up"""
        sign_in_as(email="someone@yahoo.com")
        response = _post(client)
        assert response.status_code == 400
        assert _count_users(db_session) == 0

    def test_invalid_token_gives_a_generic_401(self, client, db_session, monkeypatch):
        """TC-API-GGL-022 | AC-21.5 | T05 | negative | a bad credential is 401 with no detail about why"""
        def reject(credential):
            raise GoogleTokenError()
        monkeypatch.setattr("app.routers.auth.verify_google_id_token", reject)
        response = _post(client)
        assert response.status_code == 401
        assert response.json()["detail"] == "Google sign-in failed. Please try again."
        assert _count_users(db_session) == 0

    @pytest.mark.parametrize("error", [GoogleNotConfigured, GoogleUnavailable])
    def test_unavailable_google_is_503(self, client, monkeypatch, error):
        """TC-API-GGL-023 | AC-21.6 | T05 | negative | not configured, or Google unreachable, is 503 pointing to password login"""
        def fail(credential):
            raise error()
        monkeypatch.setattr("app.routers.auth.verify_google_id_token", fail)
        response = _post(client)
        assert response.status_code == 503
        assert "email and password" in response.json()["detail"]

    def test_disabled_when_no_client_id_is_set(self, client, monkeypatch):
        """TC-API-GGL-024 | AC-21.6 | T05 | boundary | with GOOGLE_CLIENT_ID empty the real verifier refuses everything"""
        monkeypatch.setattr(settings, "google_client_id", "")
        assert _post(client).status_code == 503

    @pytest.mark.parametrize("body", [{}, {"credential": ""}, {"credential": "x" * 4097}])
    def test_credential_is_required_and_bounded(self, client, body):
        """TC-API-GGL-025 | AC-21.5 | T05 | boundary | missing, empty or oversized credential is a 422"""
        assert client.post(GOOGLE, json=body).status_code == 422

    def test_sign_in_is_rate_limited(self, client, sign_in_as):
        """TC-API-GGL-026 | AC-21.7, AC-02.4 | T05 | boundary | the shared login limit (10 per window) returns 429 with Retry-After"""
        sign_in_as()
        statuses = [_post(client).status_code for _ in range(11)]
        assert statuses[:10] == [200] * 10
        response = _post(client)
        assert response.status_code == 429
        assert "Retry-After" in response.headers


class TestPasswordLoginAndGoogleAccounts:
    def test_google_account_cannot_log_in_with_a_password(self, client, db_session, sign_in_as):
        """TC-API-GGL-030 | AC-21.8, AC-02.3 | T05 | negative | a Google-only account has no password, so every password attempt is a normal 401"""
        sign_in_as()
        _post(client)
        response = client.post("/api/auth/login", json={"email": "newcomer@gmail.com", "password": "Passw0rd1"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


class TestIncompleteProfileGate:
    @pytest.fixture
    def newcomer(self, client, db_session, sign_in_as):
        sign_in_as()
        token = _post(client).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_cannot_post_a_listing(self, client, newcomer, monkeypatch):
        """TC-API-GGL-040 | AC-22.2 | T08 | negative | creating a listing needs a complete profile"""
        install_fake_cloudinary(monkeypatch)
        response = client.post("/api/listings", data=listing_form(), headers=newcomer)
        assert response.status_code == 403
        assert response.json()["detail"] == "Please complete your profile first."

    def test_cannot_post_a_need(self, client, newcomer):
        """TC-API-GGL-041 | AC-22.2 | T11 | negative | creating a need needs a complete profile"""
        assert client.post("/api/needs", json=need_payload(), headers=newcomer).status_code == 403

    def test_cannot_show_interest(self, client, db_session, newcomer):
        """TC-API-GGL-042 | AC-22.2 | T10 | negative | showing interest needs a complete profile"""
        listing = make_listing(db_session, make_user(db_session))
        assert client.post(f"/api/interests/listing/{listing.id}", json={}, headers=newcomer).status_code == 403

    def test_can_still_read_public_pages_and_own_profile(self, client, newcomer):
        """TC-API-GGL-043 | AC-22.2 | T07 | boundary | reading is not blocked, only actions that publish contact details"""
        assert client.get("/api/listings").status_code == 200
        assert client.get("/api/users/me", headers=newcomer).status_code == 200

    def test_password_registered_user_is_complete_from_the_start(self, client, db_session):
        """TC-API-GGL-044 | AC-22.2, AC-01.1 | T05 | positive | classic registration is unaffected: profile_complete is true"""
        user = make_user(db_session)
        assert client.get(ME, headers=auth_headers(user)).json()["profile_complete"] is True
