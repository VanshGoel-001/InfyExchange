"""API tests: the enquiry and deal flow (accept -> chat -> close deal -> return).

Statuses are stored as before (ACCEPTED is shown to people as "Chatting", REJECTED as "Declined");
CLOSED is new. TC ids are new; the AC/T columns reuse the nearest derived criteria (AC-09/10 for
interests, AC-07 for listings) because no approved spec exists for this feature yet (see test.md).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Interest, Listing, Notification
from app.services.cleanup import cleanup_expired_data
from app.utils.enums import InterestStatus, ListingStatus, ListingType
from tests.conftest import auth_headers, make_user
from tests.support import add_interest, add_listing, install_fake_cloudinary

INTERESTS = "/api/interests"
LISTINGS = "/api/listings"


def _notes(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id)).all()


def _fresh(db, obj):
    db.expire_all()
    return db.get(type(obj), obj.id)


@pytest.fixture()
def owner(db_session):
    return make_user(db_session)


class TestAccept:
    def test_accept_opens_a_chat_and_keeps_the_listing_available(self, client, db_session, owner):
        """TC-API-ENQ-001 | AC-09.3 | T10 | business | accepting sets ACCEPTED (Chatting), leaves the listing ACTIVE and tells the buyer"""
        buyer = make_user(db_session)
        listing = add_listing(db_session, owner)
        interest = add_interest(db_session, listing, buyer)
        response = client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["status"] == "ACCEPTED"
        assert _fresh(db_session, listing).status == ListingStatus.ACTIVE
        notes = _notes(db_session, buyer)
        assert [(n.kind, n.interest_id) for n in notes] == [("enquiry_accepted", interest.id)]

    def test_owner_can_accept_several_enquiries(self, client, db_session, owner):
        """TC-API-ENQ-002 | AC-09.3 | T10 | business | multiple buyers can be in a chat for one item at the same time"""
        listing = add_listing(db_session, owner)
        buyers = [make_user(db_session) for _ in range(3)]
        for buyer in buyers:
            interest = add_interest(db_session, listing, buyer)
            assert client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner)).status_code == 200
        statuses = db_session.scalars(select(Interest.status).where(Interest.listing_id == listing.id)).all()
        assert statuses == [InterestStatus.ACCEPTED] * 3

    def test_accept_sets_up_the_inactivity_clock(self, client, db_session, owner):
        """TC-API-ENQ-003 | AC-09.3 | T10 | business | accepting stamps last_activity_at and clears any old reminder"""
        listing = add_listing(db_session, owner)
        interest = add_interest(db_session, listing, make_user(db_session))
        client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
        db_session.expire_all()
        assert db_session.get(Interest, interest.id).last_activity_at is not None
        assert db_session.get(Interest, interest.id).reminder_sent_at is None

    @pytest.mark.parametrize("status", [ListingStatus.SOLD, ListingStatus.RENTED, ListingStatus.UNAVAILABLE])
    def test_cannot_accept_on_an_unavailable_item(self, client, db_session, owner, status):
        """TC-API-ENQ-004 | AC-09.3 | T10 | negative | accepting an enquiry on a sold/lent-out/unlisted item is 400"""
        listing = add_listing(db_session, owner, status=status)
        interest = add_interest(db_session, listing, make_user(db_session))
        response = client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
        assert response.status_code == 400
        assert _fresh(db_session, interest).status == InterestStatus.PENDING


class TestDecline:
    def test_decline_needs_no_body(self, client, db_session, owner):
        """TC-API-ENQ-010 | AC-09.4 | T10 | positive | one-tap decline: no body gives REJECTED with no reply stored"""
        buyer = make_user(db_session)
        interest = add_interest(db_session, add_listing(db_session, owner), buyer)
        response = client.patch(f"{INTERESTS}/{interest.id}/reject", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["status"] == "REJECTED"
        assert response.json()["decline_reply"] is None
        assert [n.kind for n in _notes(db_session, buyer)] == ["enquiry_declined"]

    def test_decline_with_a_quick_reply(self, client, db_session, owner):
        """TC-API-ENQ-011 | AC-09.4 | T10 | positive | an optional reply is stored, shown to the buyer and included in their notification"""
        buyer = make_user(db_session)
        interest = add_interest(db_session, add_listing(db_session, owner), buyer)
        response = client.patch(
            f"{INTERESTS}/{interest.id}/reject", json={"reply": "Already promised to someone"}, headers=auth_headers(owner)
        )
        assert response.status_code == 200
        assert response.json()["decline_reply"] == "Already promised to someone"
        assert "Already promised to someone" in _notes(db_session, buyer)[0].message
        sent = client.get(f"{INTERESTS}/sent", headers=auth_headers(buyer)).json()
        assert sent[0]["decline_reply"] == "Already promised to someone"

    @pytest.mark.parametrize("length, expected", [(200, 200), (201, 422)])
    def test_reply_length_boundary(self, client, db_session, owner, length, expected):
        """TC-API-ENQ-012 | AC-09.4 | T10 | boundary | a 200-character reply is accepted, 201 is rejected"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session))
        response = client.patch(
            f"{INTERESTS}/{interest.id}/reject", json={"reply": "r" * length}, headers=auth_headers(owner)
        )
        assert response.status_code == expected

    def test_blank_reply_is_stored_as_none(self, client, db_session, owner):
        """TC-API-ENQ-013 | AC-09.4 | T10 | boundary | a whitespace-only reply is treated as no reply"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session))
        response = client.patch(f"{INTERESTS}/{interest.id}/reject", json={"reply": "   "}, headers=auth_headers(owner))
        assert response.json()["decline_reply"] is None

    @pytest.mark.parametrize("status", [InterestStatus.ACCEPTED, InterestStatus.REJECTED, InterestStatus.CLOSED])
    def test_only_pending_can_be_declined(self, client, db_session, owner, status):
        """TC-API-ENQ-014 | AC-09.4 | T10 | negative | declining a chatting, declined or closed enquiry is 400"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), status)
        assert client.patch(f"{INTERESTS}/{interest.id}/reject", headers=auth_headers(owner)).status_code == 400


class TestCloseDeal:
    def _chat(self, db, owner, listing_type=ListingType.SELL, n_buyers=1):
        listing = add_listing(db, owner, listing_type=listing_type)
        buyers = [make_user(db) for _ in range(n_buyers)]
        interests = [add_interest(db, listing, b, InterestStatus.ACCEPTED) for b in buyers]
        return listing, buyers, interests

    @pytest.mark.parametrize(
        "listing_type, expected",
        [(ListingType.SELL, ListingStatus.SOLD), (ListingType.GIVEAWAY, ListingStatus.SOLD),
         (ListingType.RENT, ListingStatus.RENTED), (ListingType.LEND, ListingStatus.RENTED)],
    )
    def test_closing_marks_the_listing_sold_or_lent_out(self, client, db_session, owner, listing_type, expected):
        """TC-API-ENQ-020 | AC-09.5 | T10 | business | sell/giveaway become SOLD, rent/lend become RENTED (Lent out); the chosen enquiry is CLOSED with deal_closed_at"""
        listing, _, (interest,) = self._chat(db_session, owner, listing_type)
        response = client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["status"] == "CLOSED"
        assert response.json()["deal_closed_at"] is not None
        assert _fresh(db_session, listing).status == expected

    def test_closing_closes_every_other_open_enquiry_and_tells_them(self, client, db_session, owner):
        """TC-API-ENQ-021 | AC-09.5 | T10 | business | pending and chatting rivals become CLOSED and are told the item is gone; declined ones are left alone"""
        listing, (winner, chatting, _), (deal, other_chat, _) = self._chat(db_session, owner, n_buyers=3)
        pending_user, declined_user = make_user(db_session), make_user(db_session)
        pending = add_interest(db_session, listing, pending_user, InterestStatus.PENDING)
        declined = add_interest(db_session, listing, declined_user, InterestStatus.REJECTED)

        client.post(f"{INTERESTS}/{deal.id}/close-deal", headers=auth_headers(owner))

        db_session.expire_all()
        assert db_session.get(Interest, other_chat.id).status == InterestStatus.CLOSED
        assert db_session.get(Interest, pending.id).status == InterestStatus.CLOSED
        assert db_session.get(Interest, declined.id).status == InterestStatus.REJECTED
        # Rivals are closed without a deal; only the winner carries deal_closed_at.
        assert db_session.get(Interest, other_chat.id).deal_closed_at is None
        for user in (chatting, pending_user):
            (note,) = _notes(db_session, user)
            assert note.kind == "enquiry_closed" and "no longer available" in note.message
        assert _notes(db_session, declined_user) == []
        assert [n.kind for n in _notes(db_session, winner)] == ["deal_closed"]

    def test_only_the_owner_can_close(self, client, db_session, owner):
        """TC-API-ENQ-022 | AC-09.5 | T10 | negative | the buyer or a stranger gets 403 and nothing changes"""
        listing, (buyer,), (interest,) = self._chat(db_session, owner)
        stranger = make_user(db_session)
        for who in (buyer, stranger):
            assert client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(who)).status_code == 403
        assert _fresh(db_session, listing).status == ListingStatus.ACTIVE

    @pytest.mark.parametrize("status", [InterestStatus.PENDING, InterestStatus.REJECTED, InterestStatus.CLOSED])
    def test_can_only_close_with_someone_you_are_chatting_with(self, client, db_session, owner, status):
        """TC-API-ENQ-023 | AC-09.5 | T10 | negative | closing with a pending, declined or already-closed enquiry is 400"""
        listing = add_listing(db_session, owner)
        interest = add_interest(db_session, listing, make_user(db_session), status)
        assert client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner)).status_code == 400
        assert _fresh(db_session, listing).status == ListingStatus.ACTIVE

    def test_a_deal_cannot_be_closed_twice(self, client, db_session, owner):
        """TC-API-ENQ-024 | AC-09.5 | T10 | negative | once the listing is no longer Available, a second close attempt is 400 and the first winner is kept"""
        listing = add_listing(db_session, owner)
        first = add_interest(db_session, listing, make_user(db_session), InterestStatus.ACCEPTED)
        second = add_interest(db_session, listing, make_user(db_session), InterestStatus.ACCEPTED)
        assert client.post(f"{INTERESTS}/{first.id}/close-deal", headers=auth_headers(owner)).status_code == 200
        # The second was auto-closed, so this fails on the enquiry state before the listing state.
        assert client.post(f"{INTERESTS}/{second.id}/close-deal", headers=auth_headers(owner)).status_code == 400
        assert _fresh(db_session, second).deal_closed_at is None

    def test_a_listing_taken_off_the_market_cannot_be_closed(self, client, db_session, owner):
        """TC-API-ENQ-025 | AC-09.5 | T10 | negative | if an admin already marked the item unavailable, closing a chat is 400"""
        listing, _, (interest,) = self._chat(db_session, owner)
        listing.status = ListingStatus.UNAVAILABLE
        db_session.commit()
        assert client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner)).status_code == 400

    def test_close_is_rate_limited(self, client, db_session, owner, monkeypatch):
        """TC-API-ENQ-026 | AC-09.5 | T13 | boundary | with the action limit at 1 the second close attempt is 429"""
        from app.services import rate_limit

        monkeypatch.setattr(rate_limit.action_limiter, "max_requests", 1)
        _, _, (first, second) = self._chat(db_session, owner, n_buyers=2)
        assert client.post(f"{INTERESTS}/{first.id}/close-deal", headers=auth_headers(owner)).status_code == 200
        assert client.post(f"{INTERESTS}/{second.id}/close-deal", headers=auth_headers(owner)).status_code == 429


class TestMarkReturned:
    def _lent(self, client, db, owner, listing_type=ListingType.LEND):
        listing = add_listing(db, owner, listing_type=listing_type, price=0 if listing_type == ListingType.LEND else 50)
        buyer = make_user(db)
        interest = add_interest(db, listing, buyer, InterestStatus.ACCEPTED)
        client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner))
        return listing, buyer, interest

    @pytest.mark.parametrize("listing_type", [ListingType.LEND, ListingType.RENT])
    def test_return_makes_the_item_available_again(self, client, db_session, owner, listing_type):
        """TC-API-ENQ-030 | AC-09.6 | T10 | business | 'Mark returned' puts a lent or rented item back to ACTIVE, stamps returned_at and thanks the borrower"""
        listing, buyer, interest = self._lent(client, db_session, owner, listing_type)
        response = client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["status"] == "ACTIVE"
        assert _fresh(db_session, interest).returned_at is not None
        assert _notes(db_session, buyer)[-1].kind == "item_returned"

    def test_returned_item_shows_in_browse_again(self, client, db_session, owner):
        """TC-API-ENQ-031 | AC-09.6 | T10 | business | the item leaves browse while lent out and comes back after it is returned"""
        listing, _, _ = self._lent(client, db_session, owner)
        assert client.get(LISTINGS).json() == []
        client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(owner))
        assert [item["id"] for item in client.get(LISTINGS).json()] == [listing.id]

    def test_only_a_lent_out_item_can_be_returned(self, client, db_session, owner):
        """TC-API-ENQ-032 | AC-09.6 | T10 | negative | an Available or Sold item cannot be 'returned' (400)"""
        available = add_listing(db_session, owner)
        sold = add_listing(db_session, owner, status=ListingStatus.SOLD)
        for listing in (available, sold):
            assert client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(owner)).status_code == 400

    def test_only_the_owner_can_mark_returned(self, client, db_session, owner):
        """TC-API-ENQ-033 | AC-09.6 | T10 | negative | the borrower or a stranger gets 403; unknown id is 404"""
        listing, buyer, _ = self._lent(client, db_session, owner)
        assert client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(buyer)).status_code == 403
        assert client.post(f"{LISTINGS}/999999/mark-returned", headers=auth_headers(owner)).status_code == 404
        assert _fresh(db_session, listing).status == ListingStatus.RENTED

    def test_an_item_lent_past_its_listing_expiry_is_renewed_on_return(self, client, db_session, owner):
        """TC-API-ENQ-034 | AC-09.6 | T10 | business | a loan that outlasted the 30 days gets a fresh expiry so the Available item does not vanish"""
        listing, _, _ = self._lent(client, db_session, owner)
        listing.expires_at = datetime.utcnow() - timedelta(days=3)
        db_session.commit()
        response = client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(owner))
        assert response.status_code == 200
        assert _fresh(db_session, listing).expires_at > datetime.utcnow() + timedelta(days=20)

    def test_cleanup_leaves_an_expired_item_that_is_still_lent_out(self, db_session, owner):
        """TC-API-ENQ-035 | AC-19.3 | T14 | business | expiry cleanup deletes an expired ACTIVE listing but not one that is out on loan"""
        past = datetime.utcnow() - timedelta(days=1)
        lent = add_listing(db_session, owner, status=ListingStatus.RENTED, expires_at=past)
        active = add_listing(db_session, owner, expires_at=past)
        lent_id, active_id = lent.id, active.id
        cleanup_expired_data()
        db_session.expire_all()
        assert db_session.get(Listing, lent_id) is not None
        assert db_session.get(Listing, active_id) is None


class TestReceivedAnswer:
    def _closed(self, client, db, owner):
        listing = add_listing(db, owner)
        buyer = make_user(db)
        interest = add_interest(db, listing, buyer, InterestStatus.ACCEPTED)
        client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner))
        return buyer, interest

    @pytest.mark.parametrize("answer", [True, False])
    def test_buyer_can_answer_yes_or_no(self, client, db_session, owner, answer):
        """TC-API-ENQ-040 | AC-09.7 | T10 | positive | 'Did you get it?' Yes/No is stored and the seller is told"""
        buyer, interest = self._closed(client, db_session, owner)
        response = client.post(f"{INTERESTS}/{interest.id}/received", json={"received": answer}, headers=auth_headers(buyer))
        assert response.status_code == 200
        assert response.json()["received_confirmed"] is answer
        assert _notes(db_session, owner)[-1].kind == "received_answer"

    def test_the_answer_is_optional(self, client, db_session, owner):
        """TC-API-ENQ-041 | AC-09.7 | T10 | business | not answering blocks nothing: received_confirmed stays null and chat still works"""
        buyer, interest = self._closed(client, db_session, owner)
        assert _fresh(db_session, interest).received_confirmed is None
        response = client.post(f"{INTERESTS}/{interest.id}/messages", json={"body": "thanks"}, headers=auth_headers(buyer))
        assert response.status_code == 201

    def test_only_the_buyer_and_only_after_the_deal_closed(self, client, db_session, owner):
        """TC-API-ENQ-042 | AC-09.7 | T10 | negative | the owner or a stranger gets 403; before the deal is closed it is 400; a missing field is 422"""
        buyer, interest = self._closed(client, db_session, owner)
        body = {"received": True}
        assert client.post(f"{INTERESTS}/{interest.id}/received", json=body, headers=auth_headers(owner)).status_code == 403
        assert client.post(f"{INTERESTS}/{interest.id}/received", json=body, headers=auth_headers(make_user(db_session))).status_code == 403
        assert client.post(f"{INTERESTS}/{interest.id}/received", json={}, headers=auth_headers(buyer)).status_code == 422
        open_chat = add_interest(db_session, add_listing(db_session, owner), buyer, InterestStatus.ACCEPTED)
        assert client.post(f"{INTERESTS}/{open_chat.id}/received", json=body, headers=auth_headers(buyer)).status_code == 400


class TestStillAvailable:
    def test_owner_can_snooze_the_reminder(self, client, db_session, owner):
        """TC-API-ENQ-050 | AC-09.8 | T10 | positive | 'Still available' resets the inactivity clock and clears the reminder"""
        interest = add_interest(db_session, add_listing(db_session, owner), make_user(db_session), InterestStatus.ACCEPTED)
        old = datetime.utcnow() - timedelta(hours=60)
        interest.last_activity_at, interest.reminder_sent_at = old, old
        db_session.commit()
        assert client.post(f"{INTERESTS}/{interest.id}/still-available", headers=auth_headers(owner)).status_code == 200
        fresh = _fresh(db_session, interest)
        assert fresh.reminder_sent_at is None and fresh.last_activity_at > old

    def test_only_the_owner_of_an_open_chat(self, client, db_session, owner):
        """TC-API-ENQ-051 | AC-09.8 | T10 | negative | the buyer gets 403; a non-chatting enquiry is 400"""
        buyer = make_user(db_session)
        listing = add_listing(db_session, owner)
        chatting = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
        pending = add_interest(db_session, listing, make_user(db_session))
        assert client.post(f"{INTERESTS}/{chatting.id}/still-available", headers=auth_headers(buyer)).status_code == 403
        assert client.post(f"{INTERESTS}/{pending.id}/still-available", headers=auth_headers(owner)).status_code == 400


class TestContactAfterTheFlowChanges:
    def test_contact_is_available_while_chatting_and_to_the_deal_winner_only(self, client, db_session, owner):
        """TC-API-ENQ-060 | AC-10.1 | T13 | business | phone/email show for a chatting enquiry and for the deal winner; never for declined, pending or closed-out ones"""
        listing = add_listing(db_session, owner)
        winner, rival, declined, pending = (make_user(db_session) for _ in range(4))
        won = add_interest(db_session, listing, winner, InterestStatus.ACCEPTED)
        lost = add_interest(db_session, listing, rival, InterestStatus.ACCEPTED)
        no = add_interest(db_session, listing, declined, InterestStatus.REJECTED)
        wait = add_interest(db_session, listing, pending, InterestStatus.PENDING)

        assert client.get(f"{INTERESTS}/{won.id}/contact", headers=auth_headers(owner)).status_code == 200
        client.post(f"{INTERESTS}/{won.id}/close-deal", headers=auth_headers(owner))

        body = client.get(f"{INTERESTS}/{won.id}/contact", headers=auth_headers(winner)).json()
        assert body == {"name": owner.name, "email": owner.email, "phone": owner.phone}
        for interest, who in ((lost, rival), (no, declined), (wait, pending)):
            assert client.get(f"{INTERESTS}/{interest.id}/contact", headers=auth_headers(who)).status_code == 403
            assert client.get(f"{INTERESTS}/{interest.id}/contact", headers=auth_headers(owner)).status_code == 403

    def test_no_notification_ever_contains_contact_details(self, client, db_session, owner):
        """TC-API-ENQ-061 | AC-10.4 | T13 | business | phone numbers and email addresses never appear in bell notification text"""
        listing = add_listing(db_session, owner)
        buyer = make_user(db_session)
        enquiry = client.post(f"{INTERESTS}/listing/{listing.id}", json={}, headers=auth_headers(buyer)).json()
        client.patch(f"{INTERESTS}/{enquiry['id']}/accept", headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{enquiry['id']}/messages", json={"body": "hi"}, headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{enquiry['id']}/close-deal", headers=auth_headers(owner))

        secrets = {owner.phone, buyer.phone, owner.email, buyer.email}
        texts = [n.message for n in db_session.scalars(select(Notification)).all()]
        assert texts and not any(secret in text for text in texts for secret in secrets)


class TestNewEnquiry:
    def test_new_enquiry_notifies_the_owner_in_the_app(self, client, db_session, owner):
        """TC-API-ENQ-070 | AC-09.1 | T10 | business | an enquiry adds a bell notification for the owner naming the item"""
        buyer = make_user(db_session)
        listing = add_listing(db_session, owner, title="Yonex racket")
        response = client.post(f"{INTERESTS}/listing/{listing.id}", json={"message": "hi"}, headers=auth_headers(buyer))
        assert response.status_code == 201
        (note,) = _notes(db_session, owner)
        assert note.kind == "enquiry_received" and "Yonex racket" in note.message
        assert note.interest_id == response.json()["id"]

    def test_only_the_enquiry_itself_sends_an_email(self, client, db_session, owner, brevo):
        """TC-API-ENQ-072 | AC-09.4 | T10 | business | the admin alert is the only email in the flow: accepting, declining, chatting and closing send none"""
        listing = add_listing(db_session, owner)
        buyer, other = make_user(db_session), make_user(db_session)
        first = client.post(f"{INTERESTS}/listing/{listing.id}", json={}, headers=auth_headers(buyer)).json()
        second = client.post(f"{INTERESTS}/listing/{listing.id}", json={}, headers=auth_headers(other)).json()
        assert len(brevo.requests) == 2  # one alert per enquiry

        client.patch(f"{INTERESTS}/{first['id']}/accept", headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{first['id']}/messages", json={"body": "hello"}, headers=auth_headers(owner))
        client.patch(f"{INTERESTS}/{second['id']}/reject", headers=auth_headers(owner))
        client.post(f"{INTERESTS}/{first['id']}/close-deal", headers=auth_headers(owner))
        assert len(brevo.requests) == 2

    def test_blocked_user_cannot_enquire_and_is_not_told_why(self, client, db_session, owner):
        """TC-API-ENQ-073 | AC-09.2 | T10 | negative | after the owner blocks someone their new enquiry is 403 with a neutral message"""
        from app.models import UserBlock

        buyer = make_user(db_session)
        listing = add_listing(db_session, owner)
        db_session.add(UserBlock(blocker_id=owner.id, blocked_id=buyer.id))
        db_session.commit()
        response = client.post(f"{INTERESTS}/listing/{listing.id}", json={}, headers=auth_headers(buyer))
        assert response.status_code == 403
        assert "block" not in response.json()["detail"].lower()


class TestDeleteListing:
    def test_deleting_tells_everyone_still_involved_and_removes_the_enquiries(self, client, db_session, owner, monkeypatch):
        """TC-API-ENQ-080 | AC-07.4 | T08 | business | delete notifies pending, chatting and borrowing buyers (not declined ones) and removes all enquiries"""
        install_fake_cloudinary(monkeypatch)
        listing = add_listing(db_session, owner, title="Squash racket")
        pending, chatting, declined, borrower = (make_user(db_session) for _ in range(4))
        add_interest(db_session, listing, pending, InterestStatus.PENDING)
        add_interest(db_session, listing, chatting, InterestStatus.ACCEPTED)
        add_interest(db_session, listing, declined, InterestStatus.REJECTED)
        loan = add_interest(db_session, listing, borrower, InterestStatus.CLOSED)
        loan.deal_closed_at = datetime.utcnow()
        db_session.commit()

        assert client.delete(f"{LISTINGS}/{listing.id}", headers=auth_headers(owner)).status_code == 200

        db_session.expire_all()
        assert db_session.scalars(select(Interest)).all() == []
        for user in (pending, chatting, borrower):
            (note,) = _notes(db_session, user)
            assert note.kind == "listing_removed" and "Squash racket" in note.message and note.interest_id is None
        assert _notes(db_session, declined) == []
