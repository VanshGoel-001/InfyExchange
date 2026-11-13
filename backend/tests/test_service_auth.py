"""Service tests: password hashing and JWT access tokens (task T04)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.services.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def _encode(payload: dict, key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, key or settings.secret_key, algorithm=algorithm)


def _in(minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


class TestPasswordService:
    def test_hash_is_argon2id_and_not_plaintext(self):
        """TC-SVC-AUT-001 | AC-01.4, AC-19.6 | T04 | positive | hash is Argon2id and never equals the plaintext"""
        hashed = hash_password("Passw0rd1")
        assert hashed.startswith("$argon2id$")
        assert "Passw0rd1" not in hashed

    def test_same_password_produces_different_hashes(self):
        """TC-SVC-AUT-002 | AC-01.4 | T04 | business | each hash uses a fresh salt, yet both verify"""
        first, second = hash_password("Passw0rd1"), hash_password("Passw0rd1")
        assert first != second
        assert verify_password("Passw0rd1", first)
        assert verify_password("Passw0rd1", second)

    def test_verify_accepts_correct_password(self):
        """TC-SVC-AUT-003 | AC-02.1 | T04 | positive | correct password verifies"""
        assert verify_password("Passw0rd1", hash_password("Passw0rd1")) is True

    def test_verify_rejects_wrong_password(self):
        """TC-SVC-AUT-004 | AC-02.2 | T04 | negative | wrong password does not verify"""
        assert verify_password("Wrongpass1", hash_password("Passw0rd1")) is False

    def test_verify_is_case_sensitive(self):
        """TC-SVC-AUT-005 | AC-02.2 | T04 | boundary | a case change makes the password invalid"""
        assert verify_password("passw0rd1", hash_password("Passw0rd1")) is False

    def test_hash_roundtrip_at_max_length(self):
        """TC-SVC-AUT-006 | AC-01.4 | T04 | boundary | a 100-character password hashes and verifies"""
        password = "a" * 99 + "1"
        assert verify_password(password, hash_password(password)) is True

    def test_hash_roundtrip_with_unicode(self):
        """TC-SVC-AUT-007 | AC-01.4 | T04 | positive | non-ASCII passwords hash and verify"""
        password = "Pässw0rd-ñ-1"
        assert verify_password(password, hash_password(password)) is True


class TestAccessTokenService:
    def test_create_then_decode_returns_user_id(self):
        """TC-SVC-AUT-010 | AC-02.1, AC-03.1 | T04 | positive | token round-trips to the same integer user id"""
        assert decode_access_token(create_access_token(42)) == 42

    def test_subject_claim_is_stringified_user_id(self):
        """TC-SVC-AUT-011 | AC-02.1 | T04 | positive | 'sub' claim carries the user id as a string"""
        payload = jwt.decode(create_access_token(7), settings.secret_key, algorithms=[settings.algorithm])
        assert payload["sub"] == "7"

    def test_expiry_matches_configured_lifetime(self):
        """TC-SVC-AUT-012 | AC-02.1 | T04 | boundary | 'exp' is now + ACCESS_TOKEN_EXPIRE_MINUTES (within 10 s)"""
        payload = jwt.decode(create_access_token(1), settings.secret_key, algorithms=[settings.algorithm])
        expected = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        actual = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert abs((actual - expected).total_seconds()) < 10

    def test_expired_token_is_rejected(self):
        """TC-SVC-AUT-013 | AC-03.2 | T04 | negative | a token whose exp is in the past is rejected"""
        token = _encode({"sub": "1", "exp": _in(-1)})
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_token_signed_with_other_key_is_rejected(self):
        """TC-SVC-AUT-014 | AC-03.2 | T04 | negative | a token signed with a different secret is rejected"""
        token = _encode({"sub": "1", "exp": _in(5)}, key="a-completely-different-secret-key-value")
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)

    def test_token_without_subject_is_rejected(self):
        """TC-SVC-AUT-015 | AC-03.2 | T04 | negative | a validly signed token with no 'sub' raises ValueError"""
        with pytest.raises(ValueError):
            decode_access_token(_encode({"exp": _in(5)}))

    def test_token_with_non_numeric_subject_is_rejected(self):
        """TC-SVC-AUT-016 | AC-03.2 | T04 | negative | a non-numeric 'sub' raises ValueError"""
        with pytest.raises(ValueError):
            decode_access_token(_encode({"sub": "abc", "exp": _in(5)}))

    def test_garbage_token_is_rejected(self):
        """TC-SVC-AUT-017 | AC-03.2 | T04 | negative | a malformed string is rejected"""
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_algorithm_is_pinned(self):
        """TC-SVC-AUT-018 | AC-03.2 | T04 | negative | a token signed with HS512 is rejected even with the right secret"""
        token = _encode({"sub": "1", "exp": _in(5)}, algorithm="HS512")
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(token)
