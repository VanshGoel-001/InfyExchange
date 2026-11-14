"""Service tests: the timed enquiry rules (7-day expiry of pending enquiries, 48-hour chat reminder).

``run_maintenance(now=...)`` takes the clock as a parameter, so these tests move time instead of sleeping.
The PostgreSQL advisory-lock branch cannot run on SQLite and is not covered here (see test.md).
TC ids are new; AC/T columns reuse the nearest derived criteria (AC-14 cleanup) because no approved
spec exists for this feature yet.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Interest, Notification
from app.services.maintenance import run_maintenance
from app.utils.enums import InterestStatus, ListingStatus
from tests.conftest import make_user
from tests.support import add_interest, add_listing

NOW = datetime(2026, 11, 14, 12, 0, 0)


@pytest.fixture()
def owner(db_session):
    return make_user(db_session)


def _notes(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id)).all()


def _fresh(db, obj):
    db.expire_all()
    return db.get(type(obj), obj.id)


class TestPendingExpiry:
    @pytest.mark.parametrize(
        "age, expired",
        [(timedelta(days=7), True), (timedelta(days=7, seconds=1), True), (timedelta(days=6, hours=23, minutes=59), False)],
    )
    def test_boundary_at_seven_days(self, db_session, owner, age, expired):
        """TC-SVC-MNT-001 | AC-14.1 | T15 | boundary | a pending enquiry closes at 7 days old, not a minute earlier"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session))
        interest.created_at = NOW - age
        db_session.commit()
        result = run_maintenance(NOW)
        assert result["expired"] == (1 if expired else 0)
        assert _fresh(db_session, interest).status == (InterestStatus.CLOSED if expired else InterestStatus.PENDING)

    def test_the_buyer_is_told_and_only_the_buyer(self, db_session, owner):
        """TC-SVC-MNT-002 | AC-14.1 | T15 | business | the buyer gets a notification naming the item and the 7 days; the owner gets none"""
        buyer = make_user(db_session)
        listing = add_listing(db_session, owner, title="Squash racket")
        interest = add_interest(db_session, listing, buyer)
        interest.created_at = NOW - timedelta(days=8)
        db_session.commit()
        run_maintenance(NOW)
        (note,) = _notes(db_session, buyer)
        assert note.kind == "enquiry_expired" and note.interest_id == interest.id
        assert "Squash racket" in note.message and "7 days" in note.message
        assert _notes(db_session, owner) == []

    @pytest.mark.parametrize("status", [InterestStatus.ACCEPTED, InterestStatus.REJECTED, InterestStatus.CLOSED])
    def test_only_pending_enquiries_expire(self, db_session, owner, status):
        """TC-SVC-MNT-003 | AC-14.1 | T15 | negative | chatting, declined and closed enquiries are never touched by the 7-day rule"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), status)
        interest.created_at = NOW - timedelta(days=30)
        interest.last_activity_at = NOW  # keep the reminder rule out of this test
        db_session.commit()
        run_maintenance(NOW)
        assert _fresh(db_session, interest).status == status

    def test_running_again_does_not_notify_twice(self, db_session, owner):
        """TC-SVC-MNT-004 | AC-14.1 | T15 | business | the job is idempotent: a second run finds nothing new"""
        buyer = make_user(db_session)
        interest = add_interest(db_session, add_listing(db_session, owner), buyer)
        interest.created_at = NOW - timedelta(days=9)
        db_session.commit()
        assert run_maintenance(NOW)["expired"] == 1
        assert run_maintenance(NOW + timedelta(hours=1))["expired"] == 0
        assert len(_notes(db_session, buyer)) == 1


class TestInactivityReminder:
    def _chat(self, db, owner, idle, **listing_fields):
        interest = add_interest(db, add_listing(db, owner, **listing_fields), make_user(db), InterestStatus.ACCEPTED)
        interest.created_at = NOW - timedelta(days=3)
        interest.last_activity_at = NOW - idle
        db.commit()
        return interest

    @pytest.mark.parametrize(
        "idle, reminded",
        [(timedelta(hours=48), True), (timedelta(hours=49), True), (timedelta(hours=47, minutes=59), False)],
    )
    def test_boundary_at_forty_eight_hours(self, db_session, owner, idle, reminded):
        """TC-SVC-MNT-010 | AC-14.1 | T15 | boundary | a chat idle for 48 hours is reminded about, one idle for 47h59m is not"""
        interest = self._chat(db_session, owner, idle)
        assert run_maintenance(NOW)["reminded"] == (1 if reminded else 0)
        assert (_fresh(db_session, interest).reminder_sent_at is not None) is reminded

    def test_the_owner_gets_a_close_or_still_available_nudge(self, db_session, owner):
        """TC-SVC-MNT-011 | AC-09.8 | T10 | business | the notification goes to the owner, names the buyer and the item, and points at the chat"""
        interest = self._chat(db_session, owner, timedelta(hours=50), title="Squash racket")
        buyer = interest.interested_user
        run_maintenance(NOW)
        (note,) = _notes(db_session, owner)
        assert note.kind == "completion_reminder" and note.interest_id == interest.id
        assert buyer.name in note.message and "Squash racket" in note.message
        assert "Close the deal" in note.message and "still available" in note.message
        assert _notes(db_session, buyer) == []

    def test_one_reminder_per_quiet_spell(self, db_session, owner):
        """TC-SVC-MNT-012 | AC-09.8 | T10 | business | later runs do not repeat the reminder while nothing has happened"""
        self._chat(db_session, owner, timedelta(hours=50))
        assert run_maintenance(NOW)["reminded"] == 1
        assert run_maintenance(NOW + timedelta(hours=24))["reminded"] == 0
        assert len(_notes(db_session, owner)) == 1

    def test_activity_re_arms_the_reminder(self, db_session, owner):
        """TC-SVC-MNT-013 | AC-09.8 | T10 | business | after a message (reminder cleared, clock reset) a new quiet 48 hours produces a second reminder"""
        interest = self._chat(db_session, owner, timedelta(hours=50))
        run_maintenance(NOW)
        interest.last_activity_at, interest.reminder_sent_at = NOW, None  # what sending a message does
        db_session.commit()
        assert run_maintenance(NOW + timedelta(hours=47))["reminded"] == 0
        assert run_maintenance(NOW + timedelta(hours=49))["reminded"] == 1
        assert len(_notes(db_session, owner)) == 2

    def test_enquiries_without_a_clock_fall_back_to_their_creation_time(self, db_session, owner):
        """TC-SVC-MNT-014 | AC-09.8 | T10 | boundary | an accepted enquiry with no last_activity_at is judged by created_at rather than skipped or reminded instantly"""
        old = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), InterestStatus.ACCEPTED)
        recent = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), InterestStatus.ACCEPTED)
        old.created_at, recent.created_at = NOW - timedelta(days=3), NOW - timedelta(hours=1)
        db_session.commit()
        assert run_maintenance(NOW)["reminded"] == 1
        assert _fresh(db_session, old).reminder_sent_at is not None
        assert _fresh(db_session, recent).reminder_sent_at is None

    @pytest.mark.parametrize("status", [InterestStatus.PENDING, InterestStatus.REJECTED, InterestStatus.CLOSED])
    def test_only_open_chats_are_reminded(self, db_session, owner, status):
        """TC-SVC-MNT-015 | AC-09.8 | T10 | negative | pending, declined and closed enquiries never get the reminder"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), status)
        interest.last_activity_at = NOW - timedelta(days=5)
        interest.created_at = NOW - timedelta(days=5)
        db_session.commit()
        assert run_maintenance(NOW)["reminded"] == 0

    @pytest.mark.parametrize("status", [ListingStatus.SOLD, ListingStatus.RENTED, ListingStatus.UNAVAILABLE])
    def test_no_reminder_once_the_item_is_not_available(self, db_session, owner, status):
        """TC-SVC-MNT-016 | AC-09.8 | T10 | negative | a chat about an item that is already sold, lent out or unlisted is not nagged about"""
        self._chat(db_session, owner, timedelta(hours=60), status=status)
        assert run_maintenance(NOW)["reminded"] == 0

    def test_still_available_endpoint_stops_the_nag(self, client, db_session, owner):
        """TC-SVC-MNT-017 | AC-09.8 | T10 | business | 'Still available' resets the clock, so the next run, even days later but within 48h of the click, stays quiet"""
        from tests.conftest import auth_headers

        interest = self._chat(db_session, owner, timedelta(hours=60))
        client.post(f"/api/interests/{interest.id}/still-available", headers=auth_headers(owner))
        # The endpoint stamps the real clock, so judge "now" relative to that stamp.
        soon = datetime.utcnow() + timedelta(hours=47)
        assert run_maintenance(soon)["reminded"] == 0
        assert run_maintenance(soon + timedelta(hours=2))["reminded"] == 1


def test_result_shape_and_both_rules_in_one_run(db_session, owner):
    """TC-SVC-MNT-020 | AC-14.1 | T15 | business | one run applies both rules and reports skipped=False with the two counts"""
    stale = add_interest(db_session, add_listing(db_session, owner), make_user(db_session))
    stale.created_at = NOW - timedelta(days=8)
    quiet = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), InterestStatus.ACCEPTED)
    quiet.created_at = quiet.last_activity_at = NOW - timedelta(days=3)
    db_session.commit()
    assert run_maintenance(NOW) == {"skipped": False, "expired": 1, "reminded": 1}
    assert db_session.scalar(select(Interest).where(Interest.id == stale.id)).status == InterestStatus.CLOSED
