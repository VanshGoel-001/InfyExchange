"""Service tests: Google ID-token verification (app/services/google.py).

Tokens are signed here with a throwaway RSA key and Google's key endpoint is replaced
by a stub, so no network access happens. AC-21.x = Google sign-in (see test_api_google_auth.py).
"""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientConnectionError

from app.config import settings
from app.services import google as google_service
from app.services.google import (
    GoogleNotConfigured,
    GoogleTokenError,
    GoogleUnavailable,
    verify_google_id_token,
)

CLIENT_ID = "test-client-id.apps.googleusercontent.com"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def configured(monkeypatch, private_key):
    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)
    stub = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key()))
    monkeypatch.setattr(google_service, "_jwks_client", stub)


def _token(private_key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "123",
        "email": "ok@gmail.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 3600,
    }
    claims.update({k: v for k, v in overrides.items() if v is not None})
    for key in [k for k, v in overrides.items() if v is None]:
        claims.pop(key, None)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


class TestValidTokens:
    def test_valid_token_returns_its_claims(self, private_key):
        """TC-SVC-GGL-001 | AC-21.5 | T05 | positive | a correctly signed, current token for this client id is accepted"""
        assert verify_google_id_token(_token(private_key))["email"] == "ok@gmail.com"

    def test_bare_issuer_form_is_accepted(self, private_key):
        """TC-SVC-GGL-002 | AC-21.5 | T05 | positive | Google may issue 'accounts.google.com' without the scheme"""
        assert verify_google_id_token(_token(private_key, iss="accounts.google.com"))["sub"] == "123"

    def test_small_clock_skew_is_tolerated(self, private_key):
        """TC-SVC-GGL-003 | AC-21.5 | T05 | boundary | a token that expired 5 seconds ago is still accepted (10 s leeway)"""
        assert verify_google_id_token(_token(private_key, exp=int(time.time()) - 5))


class TestRejectedTokens:
    @pytest.mark.parametrize("overrides", [
        {"aud": "someone-elses-client"},                       # token minted for another app
        {"exp": int(time.time()) - 3600},                      # expired an hour ago
        {"iss": "https://evil.example"},                       # not Google
        {"email_verified": False},                             # mailbox not proven
        {"email_verified": None},                              # claim missing
        {"email": None},                                       # no address
        {"email": "   "},                                      # blank address
        {"sub": None},                                         # no account id
    ])
    def test_bad_claims_are_rejected(self, private_key, overrides):
        """TC-SVC-GGL-010 | AC-21.5 | T05 | negative | wrong audience, expiry, issuer or missing/unverified identity claims are refused"""
        with pytest.raises(GoogleTokenError):
            verify_google_id_token(_token(private_key, **overrides))

    def test_token_signed_with_another_key_is_rejected(self):
        """TC-SVC-GGL-011 | AC-21.5 | T05 | negative | a forged signature is refused"""
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(GoogleTokenError):
            verify_google_id_token(_token(other))

    def test_unsigned_token_is_rejected(self):
        """TC-SVC-GGL-012 | AC-21.5 | T05 | negative | alg=none is refused (algorithm is pinned to RS256)"""
        unsigned = jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1",
                               "email": "a@gmail.com", "email_verified": True, "iat": 1, "exp": 9999999999},
                              None, algorithm="none")
        with pytest.raises(GoogleTokenError):
            verify_google_id_token(unsigned)

    def test_symmetric_algorithm_confusion_is_rejected(self, private_key):
        """TC-SVC-GGL-013 | AC-21.5 | T05 | negative | an HS256 token cannot pass, even if signed with a public value"""
        forged = jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "1",
                             "email": "a@gmail.com", "email_verified": True, "iat": 1, "exp": 9999999999},
                            "a-shared-secret-of-sufficient-length-1234567890", algorithm="HS256")
        with pytest.raises(GoogleTokenError):
            verify_google_id_token(forged)

    @pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c"])
    def test_garbage_is_rejected(self, garbage):
        """TC-SVC-GGL-014 | AC-21.5 | T05 | boundary | strings that are not tokens fail cleanly with the same error"""
        with pytest.raises(GoogleTokenError):
            verify_google_id_token(garbage)


class TestAvailability:
    def test_no_client_id_means_disabled(self, private_key, monkeypatch):
        """TC-SVC-GGL-020 | AC-21.6 | T05 | negative | without GOOGLE_CLIENT_ID nothing is accepted"""
        monkeypatch.setattr(settings, "google_client_id", "")
        with pytest.raises(GoogleNotConfigured):
            verify_google_id_token(_token(private_key))

    def test_unreachable_key_endpoint_is_reported_as_unavailable(self, private_key, monkeypatch):
        """TC-SVC-GGL-021 | AC-21.6 | T05 | negative | a network failure fetching Google's keys is distinct from a bad token"""
        def down(token):
            raise PyJWKClientConnectionError("network down")
        monkeypatch.setattr(google_service, "_jwks_client", SimpleNamespace(get_signing_key_from_jwt=down))
        with pytest.raises(GoogleUnavailable):
            verify_google_id_token(_token(private_key))
