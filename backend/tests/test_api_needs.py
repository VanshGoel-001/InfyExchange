"""API tests: needs (tasks T11, T13)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Need
from app.services import rate_limit
from app.utils.enums import ListingCategory, NeedStatus, NeedType
from tests.conftest import auth_headers, make_user
from tests.support import add_need, need_payload

NEEDS = "/api/needs"


def _count(db) -> int:
    return db.scalar(select(func.count()).select_from(Need))


def _create(client, user, **overrides):
    return client.post(NEEDS, json=need_payload(**overrides), headers=auth_headers(user))


class TestCreateNeed:
    def test_valid_need_is_created_active(self, client, db_session):
        """TC-API-NED-001 | AC-08.1 | T11 | positive | 201 with caller as owner, status ACTIVE and echoed fields"""
        user = make_user(db_session)
        response = _create(client, user)
        assert response.status_code == 201
        body = response.json()
        assert body["user_id"] == user.id
        assert body["status"] == "ACTIVE"
        assert body["title"] == "Need a squash racket"
        assert body["need_type"] == "BORROW"
        assert body["budget"] == 0

    def test_expiry_is_listing_expiry_days_after_creation(self, client, db_session):
        """TC-API-NED-002 | AC-08.1 | T11 | business | expires_at is created_at + LISTING_EXPIRY_DAYS (30)"""
        body = _create(client, make_user(db_session)).json()
        assert datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["created_at"]) == timedelta(
            days=settings.listing_expiry_days)

    def test_text_fields_are_trimmed(self, client, db_session):
        """TC-API-NED-003 | AC-08.2 | T11 | business | whitespace around title, location and description is stripped"""
        body = _create(client, make_user(db_session), title="  Racket  ", location="  ECC ", description="  need it  ").json()
        assert (body["title"], body["location"], body["description"]) == ("Racket", "ECC", "need it")

    def test_unauthenticated_create_is_rejected(self, client):
        """TC-API-NED-004 | AC-08.1 | T11 | negative | no token: 401/403"""
        assert client.post(NEEDS, json=need_payload()).status_code in (401, 403)

    @pytest.mark.parametrize(
        "field, value, expected",
        [
            ("title", "x", 422), ("title", "xx", 201), ("title", "x" * 150, 201), ("title", "x" * 151, 422),
            ("location", "x", 422), ("location", "xx", 201), ("location", "x" * 100, 201), ("location", "x" * 101, 422),
            ("description", "x", 422), ("description", "xx", 201), ("description", "x" * 2000, 201), ("description", "x" * 2001, 422),
            ("duration", "x" * 100, 201), ("duration", "x" * 101, 422), ("duration", None, 201),
            ("budget", -1, 422), ("budget", 0, 201), ("budget", 1, 201),
        ],
    )
    def test_field_boundaries(self, client, db_session, field, value, expected):
        """TC-API-NED-005 | AC-08.2 | T11 | boundary | title 2-150, location 2-100, description 2-2000, duration <= 100, budget >= 0"""
        assert _create(client, make_user(db_session), **{field: value}).status_code == expected

    @pytest.mark.parametrize(
        "overrides",
        [{"need_type": "STEAL"}, {"category": "GOLF"}, {"budget": "lots"}],
        ids=["bad-need-type", "bad-category", "non-numeric-budget"],
    )
    def test_invalid_enum_or_type_is_422(self, client, db_session, overrides):
        """TC-API-NED-006 | AC-08.2 | T11 | negative | unknown enum values and non-numeric budget are rejected"""
        assert _create(client, make_user(db_session), **overrides).status_code == 422

    def test_missing_required_fields_are_422(self, client, db_session):
        """TC-API-NED-007 | AC-08.2 | T11 | negative | an empty body is rejected"""
        assert client.post(NEEDS, json={}, headers=auth_headers(make_user(db_session))).status_code == 422

    def test_budget_and_duration_are_optional(self, client, db_session):
        """TC-API-NED-008 | AC-08.2 | T11 | positive | omitting budget and duration defaults them to 0 and null"""
        body = {k: v for k, v in need_payload().items() if k not in ("budget", "duration")}
        response = client.post(NEEDS, json=body, headers=auth_headers(make_user(db_session)))
        assert response.status_code == 201
        assert response.json()["budget"] == 0
        assert response.json()["duration"] is None

    def test_identical_resubmission_returns_existing_need(self, client, db_session):
        """TC-API-NED-009 | AC-08.3 | T11 | business | the same need within the window returns the first one; one row exists"""
        user = make_user(db_session)
        first, second = _create(client, user), _create(client, user)
        assert first.json()["id"] == second.json()["id"]
        assert _count(db_session) == 1

    def test_changed_content_creates_a_new_need(self, client, db_session):
        """TC-API-NED-010 | AC-08.3 | T11 | business | a different description is not a duplicate"""
        user = make_user(db_session)
        _create(client, user, description="version one")
        _create(client, user, description="version two")
        assert _count(db_session) == 2

    def test_creation_is_throttled(self, client, db_session, monkeypatch):
        """TC-API-NED-011 | AC-08.7 | T11, T13 | boundary | with the create limit at 2 the third need is 429"""
        monkeypatch.setattr(rate_limit.create_limiter, "max_requests", 2)
        user = make_user(db_session)
        assert _create(client, user, title="one").status_code == 201
        assert _create(client, user, title="two").status_code == 201
        assert _create(client, user, title="three").status_code == 429


class TestBrowseNeeds:
    def test_public_list_shows_only_active_unexpired(self, client, db_session):
        """TC-API-NED-020 | AC-08.4 | T11 | business | anonymous callers see ACTIVE, unexpired needs with the poster's name"""
        user = make_user(db_session)
        add_need(db_session, user, title="visible")
        add_need(db_session, user, title="fulfilled", status=NeedStatus.FULFILLED)
        add_need(db_session, user, title="closed", status=NeedStatus.CLOSED)
        add_need(db_session, user, title="expired", expires_at=datetime.utcnow() - timedelta(seconds=1))
        response = client.get(NEEDS)
        assert response.status_code == 200
        assert [n["title"] for n in response.json()] == ["visible"]
        assert response.json()[0]["user_name"] == user.name

    def test_list_never_exposes_contact_details(self, client, db_session):
        """TC-API-NED-021 | AC-08.4, AC-10.4 | T11 | business | need payloads contain no email, phone or hash"""
        add_need(db_session, make_user(db_session))
        item = client.get(NEEDS).json()[0]
        for secret in ("email", "phone", "password_hash", "user_email"):
            assert secret not in item

    def test_filters(self, client, db_session):
        """TC-API-NED-022 | AC-08.4 | T11 | positive | search (title substring, any case), category, need_type and location filter results"""
        user = make_user(db_session)
        add_need(db_session, user, title="Cricket Bat", category=ListingCategory.CRICKET, need_type=NeedType.BUY,
                 location="Hostel Block A")
        add_need(db_session, user, title="Other")
        for params in ({"search": "cricket"}, {"category": "CRICKET"}, {"need_type": "BUY"}, {"location": "block a"}):
            assert [n["title"] for n in client.get(NEEDS, params=params).json()] == ["Cricket Bat"], params
        assert client.get(NEEDS, params={"search": "zzz"}).json() == []

    def test_newest_first_and_pagination(self, client, db_session):
        """TC-API-NED-023 | AC-08.4 | T11 | boundary | ordered newest first; limit/skip page the results"""
        user = make_user(db_session)
        now = datetime.utcnow()
        for age, title in ((3, "oldest"), (2, "middle"), (1, "newest")):
            add_need(db_session, user, title=title, created_at=now - timedelta(minutes=age))
        assert [n["title"] for n in client.get(NEEDS).json()] == ["newest", "middle", "oldest"]
        assert [n["title"] for n in client.get(NEEDS, params={"limit": 1, "skip": 1}).json()] == ["middle"]

    @pytest.mark.parametrize(
        "params, expected",
        [({"limit": 0}, 422), ({"limit": 100}, 200), ({"limit": 101}, 422), ({"skip": -1}, 422), ({"need_type": "STEAL"}, 422)],
    )
    def test_query_parameter_boundaries(self, client, params, expected):
        """TC-API-NED-024 | AC-08.4 | T11 | boundary | limit 1-100, skip >= 0, enum filters validated"""
        assert client.get(NEEDS, params=params).status_code == expected

    def test_read_throttle(self, client, monkeypatch):
        """TC-API-NED-025 | AC-08.7 | T11, T13 | boundary | with the read limit at 2 the third browse is 429"""
        monkeypatch.setattr(rate_limit.read_limiter, "max_requests", 2)
        assert [client.get(NEEDS).status_code for _ in range(2)] == [200, 200]
        assert client.get(NEEDS).status_code == 429


class TestNeedDetailAndOwnership:
    def test_my_needs_returns_only_own_including_expired(self, client, db_session):
        """TC-API-NED-030 | AC-08.5 | T11 | business | /me lists the caller's needs of any status or age and none of others'"""
        me, other = make_user(db_session), make_user(db_session)
        add_need(db_session, me, title="mine")
        add_need(db_session, me, title="mine-expired", expires_at=datetime.utcnow() - timedelta(days=1))
        add_need(db_session, other, title="theirs")
        response = client.get(f"{NEEDS}/me", headers=auth_headers(me))
        assert sorted(n["title"] for n in response.json()) == ["mine", "mine-expired"]

    def test_my_needs_requires_authentication(self, client):
        """TC-API-NED-031 | AC-08.5 | T11 | negative | /me without a token is 401/403"""
        assert client.get(f"{NEEDS}/me").status_code in (401, 403)

    def test_detail_is_public(self, client, db_session):
        """TC-API-NED-032 | AC-08.5 | T11 | positive | GET by id works anonymously"""
        need = add_need(db_session, make_user(db_session), title="open")
        response = client.get(f"{NEEDS}/{need.id}")
        assert response.status_code == 200
        assert response.json()["title"] == "open"

    def test_unknown_need_is_404(self, client):
        """TC-API-NED-033 | AC-08.5 | T11 | negative | unknown id gives 404 'Need not found'"""
        response = client.get(f"{NEEDS}/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Need not found"

    def test_expired_active_need_is_404(self, client, db_session):
        """TC-API-NED-034 | AC-08.5 | T11 | boundary | an ACTIVE need past expires_at gives 404 'Need has expired'"""
        need = add_need(db_session, make_user(db_session), expires_at=datetime.utcnow() - timedelta(seconds=1))
        response = client.get(f"{NEEDS}/{need.id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Need has expired"

    def test_owner_can_delete(self, client, db_session):
        """TC-API-NED-040 | AC-08.6 | T11 | positive | the owner deletes their need; it is gone afterwards"""
        owner = make_user(db_session)
        need = add_need(db_session, owner)
        response = client.delete(f"{NEEDS}/{need.id}", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json() == {"message": "Need deleted successfully"}
        assert _count(db_session) == 0

    def test_non_owner_cannot_delete(self, client, db_session):
        """TC-API-NED-041 | AC-08.6 | T11 | negative | a different user gets 403 and the need remains"""
        owner, stranger = make_user(db_session), make_user(db_session)
        need = add_need(db_session, owner)
        response = client.delete(f"{NEEDS}/{need.id}", headers=auth_headers(stranger))
        assert response.status_code == 403
        assert _count(db_session) == 1

    def test_delete_unknown_and_anonymous(self, client, db_session):
        """TC-API-NED-042 | AC-08.6 | T11 | negative | DELETE of a missing id is 404; without a token it is 401/403"""
        owner = make_user(db_session)
        assert client.delete(f"{NEEDS}/999999", headers=auth_headers(owner)).status_code == 404
        need = add_need(db_session, owner)
        assert client.delete(f"{NEEDS}/{need.id}").status_code in (401, 403)
