"""API tests: deleting and clearing notifications, 30-day expiry, hidden senders, and the actor rule."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Notification
from app.services import rate_limit
from app.services.cleanup import cleanup_expired_data
from app.services.notify import notify
from tests.conftest import auth_headers, make_user
from tests.support import add_interest, add_listing

URL = "/api/notifications"
INTERESTS = "/api/interests"


def _add(db, user, actor=None, minutes_ago=0, read=False, kind="enquiry_received", **extra):
    row = Notification(
        user_id=user.id, kind=kind, message="m", actor_id=actor.id if actor else None,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        read_at=datetime.utcnow() if read else None, **extra,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestDelete:
    def test_delete_one_returns_the_new_unread_count(self, client, db_session):
        """TC-API-NOT-030 | AC-09.1 | T10 | positive | deleting one notification removes only it and returns the unread count the badge should show"""
        me, other = make_user(db_session), make_user(db_session)
        keep, gone, read = _add(db_session, me, other), _add(db_session, me, other), _add(db_session, me, other, read=True)
        response = client.delete(f"{URL}/{gone.id}", headers=auth_headers(me))
        assert response.json() == {"unread_count": 1}
        assert sorted(i["id"] for i in client.get(URL, headers=auth_headers(me)).json()["items"]) == sorted([keep.id, read.id])

    def test_clear_all_deletes_only_my_notifications(self, client, db_session):
        """TC-API-NOT-031 | AC-09.1 | T10 | positive | clearing deletes every notification of the caller, none of anyone else's, and returns an unread count of 0"""
        me, other, sender = make_user(db_session), make_user(db_session), make_user(db_session)
        _add(db_session, me, sender), _add(db_session, me, sender, read=True)
        theirs = _add(db_session, other, sender)
        assert client.delete(URL, headers=auth_headers(me)).json() == {"unread_count": 0}
        assert client.get(URL, headers=auth_headers(me)).json() == {"unread_count": 0, "items": []}
        db_session.expire_all()
        assert db_session.get(Notification, theirs.id) is not None

    def test_someone_elses_notification_is_a_404_and_untouched(self, client, db_session):
        """TC-API-NOT-032 | AC-09.1 | T10 | negative | deleting or reading another member's notification is a 404 and changes nothing"""
        me, other, sender = make_user(db_session), make_user(db_session), make_user(db_session)
        theirs = _add(db_session, other, sender)
        assert client.delete(f"{URL}/{theirs.id}", headers=auth_headers(me)).status_code == 404
        assert client.post(f"{URL}/{theirs.id}/read", headers=auth_headers(me)).status_code == 404
        db_session.expire_all()
        row = db_session.get(Notification, theirs.id)
        assert row is not None and row.read_at is None

    def test_reading_returns_the_new_unread_count(self, client, db_session):
        """TC-API-NOT-033 | AC-09.1 | T10 | positive | marking one read answers with the new unread count"""
        me, sender = make_user(db_session), make_user(db_session)
        first, _second = _add(db_session, me, sender), _add(db_session, me, sender)
        assert client.post(f"{URL}/{first.id}/read", headers=auth_headers(me)).json() == {"unread_count": 1}

    def test_deleting_needs_a_login_and_is_rate_limited(self, client, db_session, monkeypatch):
        """TC-API-NOT-034 | AC-09.1 | T10 | negative | no token is rejected; with the action limit at 1 the second delete is 429"""
        me, sender = make_user(db_session), make_user(db_session)
        a, b = _add(db_session, me, sender), _add(db_session, me, sender)
        assert client.delete(f"{URL}/{a.id}").status_code in (401, 403)
        assert client.delete(URL).status_code in (401, 403)
        monkeypatch.setattr(rate_limit.action_limiter, "max_requests", 1)
        assert client.delete(f"{URL}/{a.id}", headers=auth_headers(me)).status_code == 200
        assert client.delete(f"{URL}/{b.id}", headers=auth_headers(me)).status_code == 429


class TestExpiry:
    def test_a_new_notification_expires_30_days_after_creation(self, db_session):
        """TC-API-NOT-035 | AC-09.1 | T10 | positive | notify() sets expires_at to created_at plus NOTIFICATION_EXPIRY_DAYS (30)"""
        me, other = make_user(db_session), make_user(db_session)
        notify(db_session, me.id, "enquiry_received", "x", actor_id=other.id)
        db_session.commit()
        row = db_session.scalars(select(Notification)).one()
        assert settings.notification_expiry_days == 30
        assert row.expires_at - row.created_at == timedelta(days=30)

    def test_expired_notifications_are_never_returned_or_counted(self, client, db_session):
        """TC-API-NOT-036 | AC-09.1 | T10 | business | a notification past expires_at is not listed, not counted in the badge, and cannot be read or deleted"""
        me, sender = make_user(db_session), make_user(db_session)
        live = _add(db_session, me, sender, minutes_ago=5)
        old = _add(db_session, me, sender, minutes_ago=60 * 24 * 40, expires_at=datetime.utcnow() - timedelta(days=10))
        body = client.get(URL, headers=auth_headers(me)).json()
        assert [i["id"] for i in body["items"]] == [live.id]
        assert body["unread_count"] == 1
        assert client.post(f"{URL}/{old.id}/read", headers=auth_headers(me)).status_code == 404
        assert client.delete(f"{URL}/{old.id}", headers=auth_headers(me)).status_code == 404

    def test_the_daily_cleanup_deletes_expired_rows_only(self, db_session):
        """TC-API-NOT-037 | AC-14.1 | T15 | business | cleanup removes notifications past expires_at and keeps the rest"""
        me, sender = make_user(db_session), make_user(db_session)
        live = _add(db_session, me, sender)
        _add(db_session, me, sender, expires_at=datetime.utcnow() - timedelta(minutes=1))
        cleanup_expired_data()
        db_session.expire_all()
        assert [r.id for r in db_session.scalars(select(Notification))] == [live.id]


class TestHiddenWithoutSender:
    def test_a_notification_that_needs_a_sender_is_hidden_without_one(self, client, db_session):
        """TC-API-NOT-038 | AC-09.1 | T10 | business | no actor and no enquiry to find one in: hidden from the list and the badge, never shown under a made-up name"""
        me = make_user(db_session)
        _add(db_session, me, None, kind="new_message")
        _add(db_session, me, None, kind="enquiry_received", interest_id=999)
        assert client.get(URL, headers=auth_headers(me)).json() == {"unread_count": 0, "items": []}

    def test_system_notices_need_no_sender(self, client, db_session):
        """TC-API-NOT-039 | AC-09.1 | T10 | positive | an expired or closed enquiry notice is shown without a sender"""
        me = make_user(db_session)
        _add(db_session, me, None, kind="enquiry_expired", listing_title="Racket")
        _add(db_session, me, None, kind="enquiry_closed", listing_title="Bat")
        body = client.get(URL, headers=auth_headers(me)).json()
        assert body["unread_count"] == 2
        assert {i["kind"]: i["actor_name"] for i in body["items"]} == {"enquiry_expired": None, "enquiry_closed": None}

    def test_a_sender_whose_name_is_only_junk_is_hidden(self, client, db_session):
        """TC-API-NOT-040 | AC-09.1 | T10 | boundary | a stored name that cleans down to nothing (markup or a link) is not replaced by a fallback: the notification is hidden"""
        me, sender = make_user(db_session), make_user(db_session)
        sender.name = "<<>> 123"
        db_session.commit()
        _add(db_session, me, sender)
        assert client.get(URL, headers=auth_headers(me)).json()["items"] == []


class TestActorRule:
    def test_a_whole_deal_never_notifies_the_person_who_acted(self, client, db_session):
        """TC-API-NOT-041 | AC-09.1 | T10 | business | enquiry, accept, chat, price change and close-deal leave no notification whose recipient is its actor"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, price=500)
        interest = client.post(f"{INTERESTS}/listing/{listing.id}", json={"message": "hi"}, headers=auth_headers(buyer)).json()
        client.patch(f"{INTERESTS}/{interest['id']}/accept", headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{interest['id']}/messages", json={"body": "hello"}, headers=auth_headers(buyer))
        client.put(f"/api/listings/{listing.id}", json={"price": 450}, headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{interest['id']}/close-deal", headers=auth_headers(owner))
        rows = db_session.scalars(select(Notification)).all()
        assert rows, "the flow should have produced notifications"
        assert all(row.actor_id != row.user_id for row in rows)

    def test_price_change_text_uses_rupees_with_indian_grouping(self, client, db_session):
        """TC-API-NOT-042 | AC-07.4 | T08 | business | the price-change detail reads ₹1,23,456 to ₹99,000 style"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, price=123456)
        interest = add_interest(db_session, listing, buyer)
        client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
        client.put(f"/api/listings/{listing.id}", json={"price": 99000}, headers=auth_headers(owner))
        row = db_session.scalars(select(Notification).where(Notification.kind == "price_changed")).one()
        assert row.detail == "₹1,23,456 to ₹99,000"
