"""API tests: finishing a profile and editing it later (POST/PATCH /api/users/me...).

AC-22.x = profile completion and editing (additions to the derived baseline in test.md).
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import User
from app.utils.enums import UserRole
from tests.conftest import auth_headers, make_user
from tests.support import install_fake_cloudinary, listing_form

COMPLETE = "/api/users/me/complete-profile"
ME = "/api/users/me"


def _google_user(db, email="g@gmail.com") -> User:
    user = User(name="Google Person", email=email, google_sub=f"sub-{email}")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _details(**overrides) -> dict:
    body = {"phone": "9876543210", "role": "DSE", "joining_date": "2026-01-15"}
    body.update(overrides)
    return body


class TestCompleteProfile:
    def test_saves_details_and_marks_profile_complete(self, client, db_session):
        """TC-API-PRF-001 | AC-22.1 | T05 | positive | phone, role and joining date are stored and the profile becomes complete"""
        user = _google_user(db_session)
        response = client.post(COMPLETE, json=_details(), headers=auth_headers(user))
        assert response.status_code == 200
        body = response.json()
        assert (body["phone"], body["role"], body["joining_date"], body["profile_complete"]) == (
            "9876543210", "DSE", "2026-01-15", True)

    def test_unlocks_posting(self, client, db_session, monkeypatch):
        """TC-API-PRF-002 | AC-22.2 | T08 | business | after completing, the same account can create a listing"""
        install_fake_cloudinary(monkeypatch)
        user = _google_user(db_session)
        headers = auth_headers(user)
        assert client.post("/api/listings", data=listing_form(), headers=headers).status_code == 403
        client.post(COMPLETE, json=_details(), headers=headers)
        assert client.post("/api/listings", data=listing_form(), headers=headers).status_code == 201

    def test_second_completion_is_refused(self, client, db_session):
        """TC-API-PRF-003 | AC-22.3 | T05 | negative | completing twice is 409; later changes go through PATCH"""
        user = _google_user(db_session)
        client.post(COMPLETE, json=_details(), headers=auth_headers(user))
        response = client.post(COMPLETE, json=_details(phone="9999999999"), headers=auth_headers(user))
        assert response.status_code == 409
        db_session.refresh(user)
        assert user.phone == "9876543210"

    def test_phone_already_used_by_someone_else(self, client, db_session):
        """TC-API-PRF-004 | AC-22.4, AC-19.1 | T05 | negative | a phone number belonging to another user is 409"""
        other = make_user(db_session)
        user = _google_user(db_session)
        response = client.post(COMPLETE, json=_details(phone=other.phone), headers=auth_headers(user))
        assert response.status_code == 409
        assert response.json()["detail"] == "Phone number already registered"
        db_session.refresh(user)
        assert user.phone is None

    @pytest.mark.parametrize("phone, ok", [
        ("1" * 9, False), ("1" * 10, True), ("1" * 15, True), ("1" * 16, False),
        ("98765abc10", False), ("+919876543210", False), ("", False),
    ])
    def test_phone_format(self, client, db_session, phone, ok):
        """TC-API-PRF-005 | AC-22.4 | T05 | boundary | digits only, 10 to 15 long"""
        user = _google_user(db_session)
        status = client.post(COMPLETE, json=_details(phone=phone), headers=auth_headers(user)).status_code
        assert status == (200 if ok else 422)

    @pytest.mark.parametrize("overrides", [
        {"role": "ADMIN"}, {"role": "dse"}, {"role": ""},
        {"joining_date": "2026-13-01"}, {"joining_date": "yesterday"}, {"joining_date": ""},
    ])
    def test_invalid_role_or_date(self, client, db_session, overrides):
        """TC-API-PRF-006 | AC-22.4 | T05 | negative | undefined roles and impossible dates are rejected"""
        user = _google_user(db_session)
        assert client.post(COMPLETE, json=_details(**overrides), headers=auth_headers(user)).status_code == 422

    @pytest.mark.parametrize("days, ok", [(0, True), (-1, True), (1, False), (365, False)])
    def test_joining_date_cannot_be_in_the_future(self, client, db_session, days, ok):
        """TC-API-PRF-007 | AC-22.4 | T05 | boundary | today and the past are fine, tomorrow is not"""
        user = _google_user(db_session)
        when = (date.today() + timedelta(days=days)).isoformat()
        status = client.post(COMPLETE, json=_details(joining_date=when), headers=auth_headers(user)).status_code
        assert status == (200 if ok else 422)

    @pytest.mark.parametrize("missing", ["phone", "role", "joining_date"])
    def test_every_field_is_required(self, client, db_session, missing):
        """TC-API-PRF-008 | AC-22.4 | T05 | negative | leaving out any one field is a 422 and nothing is saved"""
        user = _google_user(db_session)
        body = {k: v for k, v in _details().items() if k != missing}
        assert client.post(COMPLETE, json=body, headers=auth_headers(user)).status_code == 422
        db_session.refresh(user)
        assert user.profile_complete is False

    def test_cannot_smuggle_other_fields(self, client, db_session):
        """TC-API-PRF-009 | AC-22.4, AC-12.1 | T05 | negative | is_admin, name, email or password in the body are rejected, not ignored"""
        user = _google_user(db_session)
        for extra in ({"is_admin": True}, {"name": "Other"}, {"email": "x@gmail.com"}, {"password": "Passw0rd1"}):
            response = client.post(COMPLETE, json={**_details(), **extra}, headers=auth_headers(user))
            assert response.status_code == 422
        db_session.refresh(user)
        assert user.is_admin is False

    def test_requires_authentication(self, client):
        """TC-API-PRF-010 | AC-22.1, AC-03.1 | T05 | negative | no token, no access"""
        assert client.post(COMPLETE, json=_details()).status_code in (401, 403)


class TestEditProfile:
    def test_role_and_joining_date_can_be_changed(self, client, db_session):
        """TC-API-PRF-020 | AC-22.5 | T05 | positive | both editable fields update together"""
        user = make_user(db_session)
        response = client.patch(ME, json={"role": "SP_L2", "joining_date": "2025-06-01"}, headers=auth_headers(user))
        assert response.status_code == 200
        assert (response.json()["role"], response.json()["joining_date"]) == ("SP_L2", "2025-06-01")

    def test_one_field_leaves_the_other_untouched(self, client, db_session):
        """TC-API-PRF-021 | AC-22.5 | T05 | business | updating only the role keeps the joining date"""
        user = make_user(db_session)
        before = user.joining_date
        client.patch(ME, json={"role": "DSE"}, headers=auth_headers(user))
        db_session.refresh(user)
        assert (user.role, user.joining_date) == (UserRole.DSE, before)

    @pytest.mark.parametrize("body", [{"name": "New Name"}, {"phone": "9000000000"}, {"email": "n@gmail.com"},
                                      {"is_admin": True}, {"role": "DSE", "phone": "9000000000"}])
    def test_name_email_phone_and_admin_flag_cannot_be_edited(self, client, db_session, body):
        """TC-API-PRF-022 | AC-22.6, AC-12.1 | T05 | negative | anything beyond role and joining date is rejected and nothing changes"""
        user = make_user(db_session)
        snapshot = (user.name, user.email, user.phone, user.is_admin, user.role)
        assert client.patch(ME, json=body, headers=auth_headers(user)).status_code == 422
        db_session.refresh(user)
        assert (user.name, user.email, user.phone, user.is_admin, user.role) == snapshot

    def test_empty_update_is_rejected(self, client, db_session):
        """TC-API-PRF-023 | AC-22.5 | T05 | boundary | an update with nothing to change is a 422"""
        assert client.patch(ME, json={}, headers=auth_headers(make_user(db_session))).status_code == 422

    @pytest.mark.parametrize("body", [{"role": "BOSS"}, {"joining_date": "2999-01-01"}, {"joining_date": "soon"}])
    def test_invalid_values_are_rejected(self, client, db_session, body):
        """TC-API-PRF-024 | AC-22.5 | T05 | negative | undefined role, future or malformed date"""
        user = make_user(db_session)
        assert client.patch(ME, json=body, headers=auth_headers(user)).status_code == 422

    def test_incomplete_profile_must_be_completed_first(self, client, db_session):
        """TC-API-PRF-025 | AC-22.3 | T05 | negative | editing before completing is 409"""
        user = _google_user(db_session)
        assert client.patch(ME, json={"role": "SE"}, headers=auth_headers(user)).status_code == 409

    def test_users_only_edit_themselves(self, client, db_session):
        """TC-API-PRF-026 | AC-22.5, AC-03.2 | T05 | business | the endpoint has no id: another user's profile is unreachable"""
        victim, attacker = make_user(db_session), make_user(db_session)
        original = victim.role
        client.patch(ME, json={"role": "SP_L2"}, headers=auth_headers(attacker))
        db_session.refresh(victim)
        assert victim.role == original

    def test_requires_authentication(self, client):
        """TC-API-PRF-027 | AC-22.5, AC-03.1 | T05 | negative | no token, no access"""
        assert client.patch(ME, json={"role": "SE"}).status_code in (401, 403)
