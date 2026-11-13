"""API tests: activity summary (tasks T07, T10)."""

from tests.conftest import auth_headers, make_user
from tests.support import add_interest, add_listing, add_need
from app.utils.enums import InterestStatus

SUMMARY = "/api/users/me/summary"


class TestActivitySummary:
    def test_new_user_has_all_zero_counters(self, client, db_session):
        """TC-API-USR-001 | AC-11.1 | T07 | boundary | a user with no activity gets five zero counters"""
        response = client.get(SUMMARY, headers=auth_headers(make_user(db_session)))
        assert response.status_code == 200
        assert response.json() == {
            "my_listings_count": 0,
            "my_needs_count": 0,
            "my_interests_count": 0,
            "requests_received_count": 0,
            "pending_requests_received_count": 0,
        }

    def test_counters_reflect_listings_needs_and_interests(self, client, db_session):
        """TC-API-USR-002 | AC-11.1 | T07 | positive | counters match 2 listings, 1 need, 1 sent interest, 2 received (1 pending)"""
        me, other = make_user(db_session), make_user(db_session)
        mine_a, mine_b = add_listing(db_session, me), add_listing(db_session, me)
        add_need(db_session, me)
        theirs = add_listing(db_session, other)
        add_interest(db_session, theirs, me)                                   # sent by me
        add_interest(db_session, mine_a, other, InterestStatus.PENDING)        # received, pending
        add_interest(db_session, mine_b, other, InterestStatus.ACCEPTED)       # received, decided
        body = client.get(SUMMARY, headers=auth_headers(me)).json()
        assert body == {
            "my_listings_count": 2,
            "my_needs_count": 1,
            "my_interests_count": 1,
            "requests_received_count": 2,
            "pending_requests_received_count": 1,
        }

    def test_other_users_activity_is_not_counted(self, client, db_session):
        """TC-API-USR-003 | AC-11.1 | T07 | business | counters are scoped to the caller"""
        me, other = make_user(db_session), make_user(db_session)
        add_listing(db_session, other)
        add_need(db_session, other)
        body = client.get(SUMMARY, headers=auth_headers(me)).json()
        assert body["my_listings_count"] == 0 and body["my_needs_count"] == 0

    def test_requires_authentication(self, client):
        """TC-API-USR-004 | AC-11.1 | T07 | negative | anonymous callers get 401/403"""
        assert client.get(SUMMARY).status_code in (401, 403)
