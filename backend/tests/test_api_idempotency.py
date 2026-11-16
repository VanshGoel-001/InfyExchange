"""API tests: idempotency keys on the four writes that create something.

A retried request with the same `Idempotency-Key` answers with the first result and creates nothing new.
A request that failed leaves no trace, so a retry really runs. Without the header nothing changes.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models import IdempotencyKey, Interest, Listing, Message, Need
from app.utils.enums import InterestStatus
from tests.conftest import auth_headers, make_user
from tests.support import (
    add_interest,
    add_listing,
    image_part,
    install_fake_cloudinary,
    listing_form,
    need_payload,
)

LISTINGS = "/api/listings"
NEEDS = "/api/needs"
INTERESTS = "/api/interests"


def _key() -> str:
    return uuid.uuid4().hex


def _with(user, key: str) -> dict:
    return {**auth_headers(user), "Idempotency-Key": key}


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _post_listing(client, user, key=None, files=None, **form):
    headers = _with(user, key) if key else auth_headers(user)
    return client.post(LISTINGS, data=listing_form(**form), files=files or None, headers=headers)


class TestListingRetry:
    def test_same_key_returns_the_first_listing_and_uploads_once(self, client, db_session, monkeypatch):
        """TC-API-IDM-001 | AC-19.3 | T02 | business | a retry with the same key returns the same listing, with no second row and no second upload"""
        fake = install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        first = _post_listing(client, user, key, files=[image_part()])
        second = _post_listing(client, user, key, files=[image_part()])
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json()["id"] == second.json()["id"]
        assert len(second.json()["images"]) == 1
        assert _count(db_session, Listing) == 1
        assert fake.upload_calls == 1

    def test_without_a_key_nothing_changes(self, client, db_session, monkeypatch):
        """TC-API-IDM-002 | AC-19.3 | T02 | positive | requests without the header are never remembered"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        assert _post_listing(client, user, title="First one").status_code == 201
        assert _post_listing(client, user, title="Second one").status_code == 201
        assert _count(db_session, Listing) == 2
        assert _count(db_session, IdempotencyKey) == 0

    def test_a_failed_upload_frees_the_key(self, client, db_session, monkeypatch):
        """TC-API-IDM-003 | AC-19.3 | T02 | business | when the photos fail the listing is undone and so is the key, so the retry creates it"""
        fake = install_fake_cloudinary(monkeypatch, fail_on={1})
        user, key = make_user(db_session), _key()
        assert _post_listing(client, user, key, files=[image_part()]).status_code == 400
        assert _count(db_session, Listing) == 0
        assert _count(db_session, IdempotencyKey) == 0
        fake.fail_on = set()
        retry = _post_listing(client, user, key, files=[image_part()])
        assert retry.status_code == 201
        assert _count(db_session, Listing) == 1

    def test_a_rejected_request_frees_the_key(self, client, db_session, monkeypatch):
        """TC-API-IDM-004 | AC-19.3 | T02 | business | a request refused by a rule leaves no key behind"""
        install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        assert _post_listing(client, user, key, price=0).status_code == 400
        assert _count(db_session, IdempotencyKey) == 0
        assert _post_listing(client, user, key, price=500).status_code == 201

    def test_the_result_is_saved_with_the_key(self, client, db_session, monkeypatch):
        """TC-API-IDM-005 | AC-19.3 | T02 | positive | the stored key points at the listing that was created"""
        install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        created = _post_listing(client, user, key).json()
        row = db_session.scalar(select(IdempotencyKey))
        assert (row.user_id, row.key, row.scope, row.resource_id) == (user.id, key, "listing.create", created["id"])

    def test_the_same_key_from_two_people_is_two_requests(self, client, db_session, monkeypatch):
        """TC-API-IDM-006 | AC-19.3 | T02 | business | keys are per member, so one person's key can never return another's listing"""
        install_fake_cloudinary(monkeypatch)
        a, b, key = make_user(db_session), make_user(db_session), _key()
        first = _post_listing(client, a, key)
        second = _post_listing(client, b, key)
        assert first.json()["id"] != second.json()["id"]
        assert _count(db_session, Listing) == 2

    def test_a_replay_after_the_listing_was_removed_is_a_conflict(self, client, db_session, monkeypatch):
        """TC-API-IDM-007 | AC-19.3 | T02 | negative | retrying a request whose listing has since been deleted says so, instead of creating it again"""
        install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        listing_id = _post_listing(client, user, key).json()["id"]
        assert client.delete(f"{LISTINGS}/{listing_id}", headers=auth_headers(user)).status_code == 200
        retry = _post_listing(client, user, key)
        assert retry.status_code == 409
        assert "already submitted" in retry.json()["detail"]
        assert _count(db_session, Listing) == 0


class TestKeyRules:
    def test_a_key_for_a_different_action_is_refused(self, client, db_session, monkeypatch):
        """TC-API-IDM-010 | AC-19.3 | T02 | negative | one key cannot stand for two different actions"""
        install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        assert client.post(NEEDS, json=need_payload(), headers=_with(user, key)).status_code == 201
        reused = _post_listing(client, user, key)
        assert reused.status_code == 422
        assert _count(db_session, Listing) == 0

    def test_malformed_keys_are_refused(self, client, db_session):
        """TC-API-IDM-011 | AC-19.3 | T02 | boundary | a key must be 16-64 letters, digits, - or _"""
        user = make_user(db_session)
        for bad in ("short", "x" * 65, "has spaces in it here", "semi;colon;semi;colon"):
            response = client.post(NEEDS, json=need_payload(), headers=_with(user, bad))
            assert response.status_code == 422, bad
        for good in ("a" * 16, "b" * 64, "uuid-like_KEY-0123456789"):
            assert client.post(NEEDS, json=need_payload(title=good), headers=_with(user, good)).status_code == 201, good

    def test_a_claim_that_is_still_running_asks_the_client_to_wait(self, client, db_session):
        """TC-API-IDM-012 | AC-19.3 | T02 | business | a key claimed moments ago with no result yet answers 409 and creates nothing"""
        user, key = make_user(db_session), _key()
        db_session.add(IdempotencyKey(user_id=user.id, key=key, scope="need.create", created_at=datetime.utcnow()))
        db_session.commit()
        response = client.post(NEEDS, json=need_payload(), headers=_with(user, key))
        assert response.status_code == 409
        assert "still being processed" in response.json()["detail"]
        assert _count(db_session, Need) == 0

    def test_an_abandoned_claim_is_taken_over(self, client, db_session):
        """TC-API-IDM-013 | AC-19.3 | T02 | business | a claim with no result after two minutes belongs to a dead request and is reused"""
        user, key = make_user(db_session), _key()
        db_session.add(
            IdempotencyKey(user_id=user.id, key=key, scope="need.create", created_at=datetime.utcnow() - timedelta(minutes=10))
        )
        db_session.commit()
        response = client.post(NEEDS, json=need_payload(), headers=_with(user, key))
        assert response.status_code == 201
        db_session.expire_all()
        assert db_session.scalar(select(IdempotencyKey)).resource_id == response.json()["id"]

    def test_a_key_older_than_a_day_is_forgotten(self, client, db_session, monkeypatch):
        """TC-API-IDM-014 | AC-19.3 | T02 | boundary | after 24 hours the same key starts a new request"""
        install_fake_cloudinary(monkeypatch)
        user, key = make_user(db_session), _key()
        first = _post_listing(client, user, key, title="Old one").json()["id"]
        row = db_session.scalar(select(IdempotencyKey))
        row.created_at = datetime.utcnow() - timedelta(hours=25)
        db_session.commit()
        second = _post_listing(client, user, key, title="New one")
        assert second.status_code == 201
        assert second.json()["id"] != first

    def test_a_claim_lost_to_a_simultaneous_request_is_retried(self, client, db_session, monkeypatch):
        """TC-API-IDM-015 | AC-19.3 | T02 | business | if another request claims the key between our check and our insert, the second pass finds its result"""
        user, key = make_user(db_session), _key()
        first = client.post(NEEDS, json=need_payload(), headers=_with(user, key)).json()["id"]

        real_scalar = type(db_session).scalar
        calls = {"n": 0}

        def blind_once(self, statement, *args, **kwargs):
            # The first look sees nothing, as it would while the other request's claim is uncommitted.
            calls["n"] += 1
            return None if calls["n"] == 1 else real_scalar(self, statement, *args, **kwargs)

        monkeypatch.setattr("sqlalchemy.orm.Session.scalar", blind_once)
        response = client.post(NEEDS, json=need_payload(), headers=_with(user, key))
        monkeypatch.undo()
        assert calls["n"] >= 2  # the blind first look, then the second pass that finds the saved result
        assert response.status_code == 201
        assert response.json()["id"] == first
        assert _count(db_session, Need) == 1


class TestNeedRetry:
    def test_same_key_returns_the_first_need(self, client, db_session):
        """TC-API-IDM-020 | AC-19.3 | T02 | business | a retried need answers with the first one and makes no second"""
        user, key = make_user(db_session), _key()
        first = client.post(NEEDS, json=need_payload(), headers=_with(user, key))
        second = client.post(NEEDS, json=need_payload(), headers=_with(user, key))
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json()["id"] == second.json()["id"]
        assert _count(db_session, Need) == 1


class TestEnquiryRetry:
    def test_same_key_returns_the_first_enquiry_and_one_notification(self, client, db_session):
        """TC-API-IDM-030 | AC-19.3 | T02 | business | a retried enquiry returns the first one instead of a 409, with one row and one bell entry"""
        from app.models import Notification

        owner, buyer = make_user(db_session), make_user(db_session)
        listing, key = add_listing(db_session, owner), _key()
        url = f"{INTERESTS}/listing/{listing.id}"
        first = client.post(url, json={"message": "Still free?"}, headers=_with(buyer, key))
        second = client.post(url, json={"message": "Still free?"}, headers=_with(buyer, key))
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json()["id"] == second.json()["id"]
        assert _count(db_session, Interest) == 1
        assert _count(db_session, Notification) == 1

    def test_without_a_key_a_second_enquiry_is_still_a_conflict(self, client, db_session):
        """TC-API-IDM-031 | AC-19.3 | T02 | positive | the existing duplicate rule is untouched for requests with no key"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        url = f"{INTERESTS}/listing/{listing.id}"
        assert client.post(url, json={}, headers=auth_headers(buyer)).status_code == 201
        assert client.post(url, json={}, headers=auth_headers(buyer)).status_code == 409

    def test_a_refused_enquiry_frees_the_key(self, client, db_session):
        """TC-API-IDM-032 | AC-19.3 | T02 | business | an enquiry on your own listing is refused and leaves no key"""
        owner = make_user(db_session)
        listing, key = add_listing(db_session, owner), _key()
        response = client.post(f"{INTERESTS}/listing/{listing.id}", json={}, headers=_with(owner, key))
        assert response.status_code == 400
        assert _count(db_session, IdempotencyKey) == 0


class TestMessageRetry:
    def _chat(self, db_session):
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        interest = add_interest(db_session, listing, buyer, status=InterestStatus.ACCEPTED)
        return owner, buyer, f"{INTERESTS}/{interest.id}/messages"

    def test_same_key_sends_the_message_once(self, client, db_session):
        """TC-API-IDM-040 | AC-19.3 | T02 | business | a message whose answer was lost and is sent again appears once"""
        _, buyer, url = self._chat(db_session)
        key = _key()
        first = client.post(url, json={"body": "Hello"}, headers=_with(buyer, key))
        second = client.post(url, json={"body": "Hello"}, headers=_with(buyer, key))
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json()["id"] == second.json()["id"]
        assert _count(db_session, Message) == 1

    def test_a_new_key_is_a_new_message(self, client, db_session):
        """TC-API-IDM-041 | AC-19.3 | T02 | positive | sending the same words twice on purpose still sends two messages"""
        _, buyer, url = self._chat(db_session)
        assert client.post(url, json={"body": "Hi"}, headers=_with(buyer, _key())).status_code == 201
        assert client.post(url, json={"body": "Hi"}, headers=_with(buyer, _key())).status_code == 201
        assert _count(db_session, Message) == 2

    def test_a_closed_chat_leaves_no_key(self, client, db_session):
        """TC-API-IDM-042 | AC-19.3 | T02 | negative | a send refused because the chat is closed frees its key"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        interest = add_interest(db_session, listing, buyer, status=InterestStatus.PENDING)
        response = client.post(
            f"{INTERESTS}/{interest.id}/messages", json={"body": "Hi"}, headers=_with(buyer, _key())
        )
        assert response.status_code == 403
        assert _count(db_session, IdempotencyKey) == 0


class TestCorsAndCleanup:
    def test_browsers_may_send_the_header(self, client):
        """TC-API-IDM-050 | AC-19.3 | T02 | positive | the CORS preflight allows Idempotency-Key from the site"""
        response = client.options(
            NEEDS,
            headers={
                "Origin": "http://allowed.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "idempotency-key,content-type,authorization",
            },
        )
        assert response.status_code == 200
        assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()

    def test_cleanup_forgets_keys_after_a_day(self, client, db_session):
        """TC-API-IDM-051 | AC-14.1 | T15 | positive | the daily cleanup deletes keys older than 24 hours and keeps newer ones"""
        from app.services.cleanup import cleanup_expired_data

        user = make_user(db_session)
        now = datetime.utcnow()
        db_session.add_all(
            [
                IdempotencyKey(user_id=user.id, key="old-" + "k" * 16, scope="need.create", resource_id=1, created_at=now - timedelta(hours=25)),
                IdempotencyKey(user_id=user.id, key="new-" + "k" * 16, scope="need.create", resource_id=2, created_at=now - timedelta(hours=1)),
            ]
        )
        db_session.commit()
        cleanup_expired_data()
        db_session.expire_all()
        assert [row.key[:3] for row in db_session.scalars(select(IdempotencyKey))] == ["new"]
