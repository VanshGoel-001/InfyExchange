"""API tests: interests, accept/reject and contact reveal (tasks T10, T13).

test_authorization.py already covers: own-listing interest, contact blocked before acceptance,
blocked for a third party, and visible to both participants. Those are not repeated here.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Interest, Listing
from app.services import rate_limit
from app.utils.enums import InterestStatus, ListingStatus
from tests.conftest import auth_headers, make_user
from tests.support import add_image, add_interest, add_listing

BASE = "/api/interests"


def _interest_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Interest))


@pytest.fixture()
def trio(db_session):
    """(owner, buyer, active listing owned by owner)."""
    owner, buyer = make_user(db_session), make_user(db_session)
    return owner, buyer, add_listing(db_session, owner)


def _send(client, user, listing, **body):
    return client.post(f"{BASE}/listing/{listing.id}", json=body, headers=auth_headers(user))


class TestCreateInterest:
    def test_creates_pending_interest_with_message(self, client, trio):
        """TC-API-INT-001 | AC-09.1 | T10 | positive | 201, status PENDING, message and ids stored"""
        owner, buyer, listing = trio
        response = _send(client, buyer, listing, message="Is it available?")
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "PENDING"
        assert body["message"] == "Is it available?"
        assert body["listing_id"] == listing.id
        assert body["interested_user_id"] == buyer.id

    def test_message_is_optional(self, client, trio):
        """TC-API-INT-002 | AC-09.1 | T10 | boundary | an empty JSON body creates an interest with a null message"""
        _, buyer, listing = trio
        response = _send(client, buyer, listing)
        assert response.status_code == 201
        assert response.json()["message"] is None

    @pytest.mark.parametrize("length, expected", [(500, 201), (501, 422)])
    def test_message_length_boundary(self, client, trio, length, expected):
        """TC-API-INT-003 | AC-09.1 | T10 | boundary | a 500-character message is accepted, 501 is rejected"""
        _, buyer, listing = trio
        assert _send(client, buyer, listing, message="m" * length).status_code == expected

    def test_requires_authentication(self, client, trio):
        """TC-API-INT-004 | AC-09.2 | T10 | negative | no token: 401/403"""
        _, _, listing = trio
        assert client.post(f"{BASE}/listing/{listing.id}", json={}).status_code in (401, 403)

    def test_unknown_listing_is_404(self, client, db_session):
        """TC-API-INT-005 | AC-09.2 | T10 | negative | interest in a missing listing gives 404"""
        buyer = make_user(db_session)
        response = client.post(f"{BASE}/listing/999999", json={}, headers=auth_headers(buyer))
        assert response.status_code == 404
        assert response.json()["detail"] == "Listing not found"

    @pytest.mark.parametrize("status", [ListingStatus.SOLD, ListingStatus.RENTED, ListingStatus.UNAVAILABLE])
    def test_inactive_listing_is_refused(self, client, db_session, status):
        """TC-API-INT-006 | AC-09.2 | T10 | negative | interest in a non-ACTIVE listing gives 400"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, status=status)
        response = _send(client, buyer, listing)
        assert response.status_code == 400
        assert response.json()["detail"] == "This listing is no longer active"

    def test_expired_listing_is_refused(self, client, db_session):
        """TC-API-INT-007 | AC-09.2 | T10 | boundary | an ACTIVE listing past expires_at gives 400 'expired'"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, expires_at=datetime.utcnow() - timedelta(seconds=1))
        response = _send(client, buyer, listing)
        assert response.status_code == 400
        assert response.json()["detail"] == "This listing has expired"

    def test_second_interest_by_same_user_conflicts(self, client, trio, db_session):
        """TC-API-INT-008 | AC-09.2, AC-19.1 | T10 | negative | repeating interest gives 409 and keeps a single row"""
        _, buyer, listing = trio
        assert _send(client, buyer, listing).status_code == 201
        response = _send(client, buyer, listing)
        assert response.status_code == 409
        assert response.json()["detail"] == "You already showed interest"
        assert _interest_count(db_session) == 1

    def test_different_users_may_each_show_interest(self, client, trio, db_session):
        """TC-API-INT-009 | AC-09.2 | T10 | positive | two users can both express interest in the same listing"""
        _, buyer, listing = trio
        second = make_user(db_session)
        assert _send(client, buyer, listing).status_code == 201
        assert _send(client, second, listing).status_code == 201

    def test_same_user_can_show_interest_in_different_listings(self, client, db_session):
        """TC-API-INT-010 | AC-09.2 | T10 | business | the uniqueness rule is per (listing, user), not per user"""
        owner, buyer = make_user(db_session), make_user(db_session)
        first, second = add_listing(db_session, owner), add_listing(db_session, owner)
        assert _send(client, buyer, first).status_code == 201
        assert _send(client, buyer, second).status_code == 201

    def test_creation_is_throttled(self, client, db_session, monkeypatch):
        """TC-API-INT-011 | AC-09.1 | T10, T13 | boundary | with the create limit at 1 the second interest is 429"""
        monkeypatch.setattr(rate_limit.create_limiter, "max_requests", 1)
        owner, buyer = make_user(db_session), make_user(db_session)
        first, second = add_listing(db_session, owner), add_listing(db_session, owner)
        assert _send(client, buyer, first).status_code == 201
        assert _send(client, buyer, second).status_code == 429


class TestInterestLists:
    def test_received_lists_interests_on_my_listings_with_context(self, client, trio, db_session):
        """TC-API-INT-020 | AC-09.3 | T10 | positive | owner sees buyer name/role, listing title and image; no contact details"""
        owner, buyer, listing = trio
        add_image(db_session, listing, url="https://res.cloudinary.com/test/pic.png")
        add_interest(db_session, listing, buyer)
        response = client.get(f"{BASE}/received", headers=auth_headers(owner))
        assert response.status_code == 200
        item = response.json()[0]
        assert item["interested_user_name"] == buyer.name
        assert item["interested_user_role"] == "SE"
        assert item["listing_title"] == listing.title
        assert item["listing_image_url"] == "https://res.cloudinary.com/test/pic.png"
        for secret in ("email", "phone", "interested_user_email", "interested_user_phone"):
            assert secret not in item

    def test_received_excludes_interests_on_other_owners_listings(self, client, trio, db_session):
        """TC-API-INT-021 | AC-09.3 | T10 | business | a user only sees requests for their own listings"""
        owner, buyer, listing = trio
        other_owner = make_user(db_session)
        add_interest(db_session, listing, buyer)
        assert client.get(f"{BASE}/received", headers=auth_headers(other_owner)).json() == []

    def test_sent_lists_only_my_interests(self, client, trio, db_session):
        """TC-API-INT-022 | AC-09.3 | T10 | positive | the buyer sees their own interest (name = themselves); others do not"""
        owner, buyer, listing = trio
        stranger = make_user(db_session)
        add_interest(db_session, listing, buyer)
        mine = client.get(f"{BASE}/sent", headers=auth_headers(buyer)).json()
        assert len(mine) == 1
        assert mine[0]["interested_user_name"] == buyer.name
        assert client.get(f"{BASE}/sent", headers=auth_headers(stranger)).json() == []

    def test_lists_require_authentication(self, client):
        """TC-API-INT-023 | AC-09.3 | T10 | negative | /received and /sent reject anonymous callers"""
        assert client.get(f"{BASE}/received").status_code in (401, 403)
        assert client.get(f"{BASE}/sent").status_code in (401, 403)

    def test_list_pagination_and_bounds(self, client, trio, db_session):
        """TC-API-INT-024 | AC-09.3 | T10 | boundary | limit/skip page the lists; limit 101 and skip -1 are rejected"""
        owner, _, _ = trio
        for _ in range(3):
            listing = add_listing(db_session, owner)
            add_interest(db_session, listing, make_user(db_session))
        headers = auth_headers(owner)
        assert len(client.get(f"{BASE}/received", params={"limit": 2}, headers=headers).json()) == 2
        assert len(client.get(f"{BASE}/received", params={"limit": 2, "skip": 2}, headers=headers).json()) == 1
        assert client.get(f"{BASE}/received", params={"limit": 101}, headers=headers).status_code == 422
        assert client.get(f"{BASE}/sent", params={"skip": -1}, headers=headers).status_code == 422

    def test_received_is_newest_first(self, client, trio, db_session):
        """TC-API-INT-025 | AC-09.3 | T10 | business | requests are ordered by creation time, newest first"""
        owner, _, listing = trio
        first, second = make_user(db_session), make_user(db_session)
        older = add_interest(db_session, listing, first, message="older")
        older.created_at = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()
        add_interest(db_session, listing, second, message="newer")
        messages = [i["message"] for i in client.get(f"{BASE}/received", headers=auth_headers(owner)).json()]
        assert messages == ["newer", "older"]


class TestAcceptReject:
    @pytest.mark.parametrize("action, expected", [("accept", "ACCEPTED"), ("reject", "REJECTED")])
    def test_owner_decides_a_pending_interest(self, client, trio, db_session, action, expected):
        """TC-API-INT-030 | AC-09.4 | T10 | positive | the listing owner moves PENDING to ACCEPTED or REJECTED"""
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer)
        response = client.patch(f"{BASE}/{interest.id}/{action}", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["status"] == expected

    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_only_the_owner_may_decide(self, client, trio, db_session, action):
        """TC-API-INT-031 | AC-09.4 | T10 | negative | the interested user and strangers get 403; status stays PENDING"""
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer)
        for actor in (buyer, make_user(db_session)):
            assert client.patch(f"{BASE}/{interest.id}/{action}", headers=auth_headers(actor)).status_code == 403
        db_session.expire_all()
        assert db_session.get(Interest, interest.id).status == InterestStatus.PENDING

    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_unknown_interest_is_404(self, client, db_session, action):
        """TC-API-INT-032 | AC-09.4 | T10 | negative | a missing interest id gives 404"""
        response = client.patch(f"{BASE}/999999/{action}", headers=auth_headers(make_user(db_session)))
        assert response.status_code == 404

    @pytest.mark.parametrize("start", [InterestStatus.ACCEPTED, InterestStatus.REJECTED])
    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_only_pending_interests_can_be_decided(self, client, trio, db_session, start, action):
        """TC-API-INT-033 | AC-09.4 | T10 | negative | accepted/rejected interests are final: any further accept/reject is 400"""
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer, start)
        response = client.patch(f"{BASE}/{interest.id}/{action}", headers=auth_headers(owner))
        assert response.status_code == 400
        db_session.expire_all()
        assert db_session.get(Interest, interest.id).status == start

    def test_decisions_require_authentication(self, client, trio, db_session):
        """TC-API-INT-034 | AC-09.4 | T10 | negative | anonymous accept/reject is 401/403"""
        _, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer)
        assert client.patch(f"{BASE}/{interest.id}/accept").status_code in (401, 403)
        assert client.patch(f"{BASE}/{interest.id}/reject").status_code in (401, 403)

    def test_accepting_does_not_change_listing_or_other_requests(self, client, trio, db_session):
        """TC-API-INT-035 | AC-09.5 | T10 | business | accepting one interest leaves the listing ACTIVE and other pending requests untouched"""
        owner, buyer, listing = trio
        other_buyer = make_user(db_session)
        accepted = add_interest(db_session, listing, buyer)
        pending = add_interest(db_session, listing, other_buyer)
        client.patch(f"{BASE}/{accepted.id}/accept", headers=auth_headers(owner))
        db_session.expire_all()
        assert db_session.get(Listing, listing.id).status == ListingStatus.ACTIVE
        assert db_session.get(Interest, pending.id).status == InterestStatus.PENDING

    def test_owner_may_accept_several_interests(self, client, trio, db_session):
        """TC-API-INT-036 | AC-09.5 | T10 | business | multiple buyers can be accepted for the same listing"""
        owner, buyer, listing = trio
        second = make_user(db_session)
        ids = [add_interest(db_session, listing, user).id for user in (buyer, second)]
        statuses = [client.patch(f"{BASE}/{i}/accept", headers=auth_headers(owner)).json()["status"] for i in ids]
        assert statuses == ["ACCEPTED", "ACCEPTED"]


class TestContactReveal:
    def test_payload_contains_exactly_name_email_phone_of_counterpart(self, client, trio, db_session):
        """TC-API-INT-040 | AC-10.1 | T10 | positive | each side receives only {name, email, phone} of the other party"""
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
        to_owner = client.get(f"{BASE}/{interest.id}/contact", headers=auth_headers(owner)).json()
        to_buyer = client.get(f"{BASE}/{interest.id}/contact", headers=auth_headers(buyer)).json()
        assert to_owner == {"name": buyer.name, "email": buyer.email, "phone": buyer.phone}
        assert to_buyer == {"name": owner.name, "email": owner.email, "phone": owner.phone}

    def test_rejected_interest_never_reveals_contact(self, client, trio, db_session):
        """TC-API-INT-041 | AC-10.2 | T10 | negative | a REJECTED interest gives 403 to both parties"""
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer, InterestStatus.REJECTED)
        for actor in (owner, buyer):
            assert client.get(f"{BASE}/{interest.id}/contact", headers=auth_headers(actor)).status_code == 403

    def test_unknown_interest_is_404(self, client, db_session):
        """TC-API-INT-042 | AC-10.2 | T10 | negative | a missing interest id gives 404"""
        assert client.get(f"{BASE}/999999/contact", headers=auth_headers(make_user(db_session))).status_code == 404

    def test_requires_authentication(self, client, trio, db_session):
        """TC-API-INT-043 | AC-10.2 | T10 | negative | anonymous reveal is 401/403"""
        _, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
        assert client.get(f"{BASE}/{interest.id}/contact").status_code in (401, 403)

    def test_reveal_is_throttled(self, client, trio, db_session, monkeypatch):
        """TC-API-INT-044 | AC-10.3 | T10, T13 | boundary | with the contact limit at 1 the second reveal is 429 with Retry-After"""
        monkeypatch.setattr(rate_limit.contact_limiter, "max_requests", 1)
        owner, buyer, listing = trio
        interest = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
        headers = auth_headers(owner)
        assert client.get(f"{BASE}/{interest.id}/contact", headers=headers).status_code == 200
        response = client.get(f"{BASE}/{interest.id}/contact", headers=headers)
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_full_flow_pending_to_contact(self, client, trio):
        """TC-API-INT-045 | AC-09.1, AC-09.4, AC-10.1 | T10 | business | send -> blocked -> accept -> contact available, end to end"""
        owner, buyer, listing = trio
        interest_id = _send(client, buyer, listing, message="hello").json()["id"]
        assert client.get(f"{BASE}/{interest_id}/contact", headers=auth_headers(buyer)).status_code == 403
        assert client.patch(f"{BASE}/{interest_id}/accept", headers=auth_headers(owner)).status_code == 200
        assert client.get(f"{BASE}/{interest_id}/contact", headers=auth_headers(buyer)).status_code == 200
