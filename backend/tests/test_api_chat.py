"""API tests: the one-to-one chat on an enquiry (messages, unread badges, polling, block, report).

TC ids are new; AC/T columns reuse the nearest derived criteria (AC-09/10 for interests and
contact privacy, AC-13 for admin) because no approved spec exists for this feature yet (see test.md).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Listing, Message, Notification, Report, UserBlock
from app.services import rate_limit
from app.utils.enums import InterestStatus, ListingStatus
from tests.conftest import auth_headers, make_user
from tests.support import add_interest, add_listing

INTERESTS = "/api/interests"


@pytest.fixture()
def pair(db_session):
    """(owner, buyer, listing, interest) with the enquiry accepted, i.e. a chat is open."""
    owner, buyer = make_user(db_session), make_user(db_session)
    listing = add_listing(db_session, owner)
    interest = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
    return owner, buyer, listing, interest


def _say(client, interest, who, body="hello"):
    return client.post(f"{INTERESTS}/{interest.id}/messages", json={"body": body}, headers=auth_headers(who))


def _chat(client, interest, who, after_id=0):
    return client.get(f"{INTERESTS}/{interest.id}/chat", params={"after_id": after_id}, headers=auth_headers(who))


def _notes(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id)).all()


class TestChatState:
    def test_each_side_sees_the_other_person(self, client, pair):
        """TC-API-CHT-001 | AC-09.3 | T10 | positive | the owner sees the buyer's name and the buyer sees the owner's; i_am_owner differs"""
        owner, buyer, listing, interest = pair
        as_owner, as_buyer = _chat(client, interest, owner).json(), _chat(client, interest, buyer).json()
        assert (as_owner["other_name"], as_owner["i_am_owner"]) == (buyer.name, True)
        assert (as_buyer["other_name"], as_buyer["i_am_owner"]) == (owner.name, False)
        for body in (as_owner, as_buyer):
            assert body["listing_id"] == listing.id and body["can_send"] is True and body["status"] == "ACCEPTED"
            assert body["messages"] == []

    def test_only_the_two_people_can_open_it(self, client, db_session, pair):
        """TC-API-CHT-002 | AC-10.1 | T13 | negative | a stranger gets 403 on read, send, report and block; an unknown id is 404; no token is 401/403"""
        _, _, _, interest = pair
        stranger = make_user(db_session)
        headers = auth_headers(stranger)
        assert _chat(client, interest, stranger).status_code == 403
        assert _say(client, interest, stranger).status_code == 403
        assert client.post(f"{INTERESTS}/{interest.id}/report", json={"reason": "spam spam"}, headers=headers).status_code == 403
        assert client.post(f"{INTERESTS}/{interest.id}/block", headers=headers).status_code == 403
        assert client.get(f"{INTERESTS}/999999/chat", headers=headers).status_code == 404
        assert client.get(f"{INTERESTS}/{interest.id}/chat").status_code in (401, 403)

    def test_the_chat_payload_never_carries_contact_details(self, client, pair):
        """TC-API-CHT-003 | AC-10.4 | T13 | business | neither email nor phone of either person appears anywhere in the chat response"""
        owner, buyer, _, interest = pair
        _say(client, interest, buyer, "hi")
        text = _chat(client, interest, owner).text
        for secret in (owner.email, owner.phone, buyer.email, buyer.phone):
            assert secret not in text

    def test_a_pending_or_declined_enquiry_has_no_open_chat(self, client, db_session, pair):
        """TC-API-CHT-004 | AC-09.3 | T10 | business | the screen can load for a pending or declined enquiry but can_send is false"""
        owner, buyer, listing, _ = pair
        for status in (InterestStatus.PENDING, InterestStatus.REJECTED):
            other = make_user(db_session)
            interest = add_interest(db_session, listing, other, status)
            assert _chat(client, interest, other).json()["can_send"] is False
            assert _chat(client, interest, owner).json()["can_send"] is False

    def test_the_reminder_flag_is_for_the_owner_only(self, client, db_session, pair):
        """TC-API-CHT-005 | AC-09.8 | T10 | business | reminder_pending is true for the owner once the reminder fired, and false for the buyer"""
        owner, buyer, _, interest = pair
        assert _chat(client, interest, owner).json()["reminder_pending"] is False
        interest.reminder_sent_at = datetime.utcnow()
        db_session.commit()
        assert _chat(client, interest, owner).json()["reminder_pending"] is True
        assert _chat(client, interest, buyer).json()["reminder_pending"] is False


class TestSendMessage:
    def test_both_people_can_talk_and_both_see_it_in_order(self, client, pair):
        """TC-API-CHT-010 | AC-09.3 | T10 | positive | messages from both sides are stored with the right sender and returned oldest first"""
        owner, buyer, _, interest = pair
        first = _say(client, interest, buyer, "Is it available?")
        second = _say(client, interest, owner, "Yes, come at 6")
        assert first.status_code == second.status_code == 201
        assert first.json()["sender_id"] == buyer.id
        seen = _chat(client, interest, buyer).json()["messages"]
        assert [(m["sender_id"], m["body"]) for m in seen] == [(buyer.id, "Is it available?"), (owner.id, "Yes, come at 6")]

    def test_text_is_stored_as_typed_after_trimming(self, client, db_session, pair):
        """TC-API-CHT-011 | AC-18.2 | T16 | business | surrounding whitespace is trimmed and markup is kept as plain text (React escapes it on screen)"""
        _, buyer, _, interest = pair
        assert _say(client, interest, buyer, "  <b>hi</b>  ").json()["body"] == "<b>hi</b>"

    @pytest.mark.parametrize("body, expected", [("", 422), ("   ", 422), ("a", 201), ("a" * 1000, 201), ("a" * 1001, 422)])
    def test_message_length_boundary(self, client, pair, body, expected):
        """TC-API-CHT-012 | AC-18.1 | T16 | boundary | blank messages are refused; 1-1000 characters are accepted; 1001 is not"""
        _, buyer, _, interest = pair
        assert _say(client, interest, buyer, body).status_code == expected

    @pytest.mark.parametrize("status", [InterestStatus.PENDING, InterestStatus.REJECTED, InterestStatus.CLOSED])
    def test_no_messages_unless_the_chat_is_open(self, client, db_session, status):
        """TC-API-CHT-013 | AC-09.3 | T10 | negative | pending, declined and closed-out enquiries cannot be messaged (403, nothing stored)"""
        owner, buyer = make_user(db_session), make_user(db_session)
        interest = add_interest(db_session, add_listing(db_session, owner), buyer, status)
        for who in (owner, buyer):
            assert _say(client, interest, who).status_code == 403
        assert db_session.scalar(select(func.count()).select_from(Message)) == 0

    def test_the_deal_winner_can_keep_talking_until_the_item_is_returned(self, client, db_session):
        """TC-API-CHT-014 | AC-09.6 | T10 | business | after the deal closes the two can arrange the handover; once a lent item is returned the chat is read-only"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, listing_type="LEND", price=0)
        interest = add_interest(db_session, listing, buyer, InterestStatus.ACCEPTED)
        client.post(f"{INTERESTS}/{interest.id}/close-deal", headers=auth_headers(owner))
        assert _say(client, interest, buyer, "where do I collect it?").status_code == 201
        client.post(f"/api/listings/{listing.id}/mark-returned", headers=auth_headers(owner))
        assert _chat(client, interest, buyer).json()["can_send"] is False
        assert _say(client, interest, buyer).status_code == 403
        assert len(_chat(client, interest, buyer).json()["messages"]) == 1  # history stays readable

    def test_sending_is_rate_limited_per_user(self, client, pair, monkeypatch):
        """TC-API-CHT-015 | AC-09.3 | T13 | boundary | with the chat limit at 2 the third message in a window is 429, and it is per user, not per address"""
        owner, buyer, _, interest = pair
        monkeypatch.setattr(rate_limit.chat_limiter, "max_requests", 2)
        assert _say(client, interest, buyer).status_code == 201
        assert _say(client, interest, buyer).status_code == 201
        assert _say(client, interest, buyer).status_code == 429
        assert _say(client, interest, owner).status_code == 201

    def test_the_other_person_is_notified_once_until_they_read(self, client, db_session, pair):
        """TC-API-CHT-016 | AC-09.3 | T10 | business | the first unread message adds one bell entry; more while it is unread add none; after they open the chat the next one adds another"""
        owner, buyer, _, interest = pair
        _say(client, interest, buyer, "one")
        _say(client, interest, buyer, "two")
        mine = [n for n in _notes(db_session, owner) if n.kind == "new_message"]
        assert len(mine) == 1 and mine[0].interest_id == interest.id and buyer.name in mine[0].message
        assert [n for n in _notes(db_session, buyer) if n.kind == "new_message"] == []
        _chat(client, interest, owner)  # owner reads
        _say(client, interest, buyer, "three")
        assert len([n for n in _notes(db_session, owner) if n.kind == "new_message"]) == 2

    def test_a_message_resets_the_inactivity_clock(self, client, db_session, pair):
        """TC-API-CHT-017 | AC-09.8 | T10 | business | sending a message refreshes last_activity_at and clears a fired reminder"""
        _, buyer, _, interest = pair
        old = datetime.utcnow() - timedelta(hours=60)
        interest.last_activity_at, interest.reminder_sent_at = old, old
        db_session.commit()
        _say(client, interest, buyer)
        db_session.refresh(interest)
        assert interest.last_activity_at > old and interest.reminder_sent_at is None


class TestUnreadAndPolling:
    def test_unread_counts_show_on_the_enquiry_lists_and_clear_on_open(self, client, pair):
        """TC-API-CHT-020 | AC-09.3 | T10 | business | unread_count is the other person's unopened messages, per side, and drops to zero once the chat is opened"""
        owner, buyer, _, interest = pair
        _say(client, interest, owner, "a")
        _say(client, interest, owner, "b")
        _say(client, interest, buyer, "c")
        sent = client.get(f"{INTERESTS}/sent", headers=auth_headers(buyer)).json()
        received = client.get(f"{INTERESTS}/received", headers=auth_headers(owner)).json()
        assert sent[0]["unread_count"] == 2 and received[0]["unread_count"] == 1
        _chat(client, interest, buyer)
        sent = client.get(f"{INTERESTS}/sent", headers=auth_headers(buyer)).json()
        received = client.get(f"{INTERESTS}/received", headers=auth_headers(owner)).json()
        assert sent[0]["unread_count"] == 0 and received[0]["unread_count"] == 1  # the owner has not opened it yet

    def test_unread_is_counted_per_enquiry(self, client, db_session, pair):
        """TC-API-CHT-021 | AC-09.3 | T10 | business | each enquiry keeps its own unread count"""
        owner, buyer, listing, first = pair
        other = make_user(db_session)
        second = add_interest(db_session, listing, other, InterestStatus.ACCEPTED)
        _say(client, first, buyer)
        _say(client, second, other)
        _say(client, second, other)
        counts = {item["id"]: item["unread_count"] for item in client.get(f"{INTERESTS}/received", headers=auth_headers(owner)).json()}
        assert counts == {first.id: 1, second.id: 2}

    def test_after_id_returns_only_newer_messages(self, client, pair):
        """TC-API-CHT-022 | AC-09.3 | T10 | positive | polling with after_id returns just what arrived since, oldest first"""
        owner, buyer, _, interest = pair
        ids = [_say(client, interest, who, text).json()["id"] for who, text in ((buyer, "1"), (owner, "2"), (buyer, "3"))]
        assert [m["body"] for m in _chat(client, interest, owner, after_id=ids[0]).json()["messages"]] == ["2", "3"]
        assert _chat(client, interest, owner, after_id=ids[-1]).json()["messages"] == []

    def test_the_first_load_returns_the_latest_page_in_order(self, client, db_session, pair):
        """TC-API-CHT-023 | AC-09.3 | T10 | boundary | a long thread opens with its newest 200 messages, oldest of those first"""
        owner, buyer, _, interest = pair
        for n in range(205):
            db_session.add(Message(interest_id=interest.id, sender_id=buyer.id, body=str(n), created_at=datetime.utcnow()))
        db_session.commit()
        bodies = [m["body"] for m in _chat(client, interest, owner).json()["messages"]]
        assert len(bodies) == 200 and bodies[0] == "5" and bodies[-1] == "204"

    def test_opening_the_chat_marks_only_the_other_persons_messages_read(self, client, db_session, pair):
        """TC-API-CHT-024 | AC-09.3 | T10 | business | fetching the thread stamps read_at on incoming messages and leaves your own alone"""
        owner, buyer, _, interest = pair
        _say(client, interest, owner, "from owner")
        _say(client, interest, buyer, "from buyer")
        _chat(client, interest, buyer)
        db_session.expire_all()
        by_sender = {m.sender_id: m.read_at for m in db_session.scalars(select(Message)).all()}
        assert by_sender[owner.id] is not None and by_sender[buyer.id] is None

    def test_polling_is_rate_limited_per_user(self, client, pair, monkeypatch):
        """TC-API-CHT-025 | AC-09.3 | T13 | boundary | with the poll limit at 2 the third fetch is 429 for that user, while the other person is unaffected"""
        owner, buyer, _, interest = pair
        monkeypatch.setattr(rate_limit.poll_limiter, "max_requests", 2)
        assert [_chat(client, interest, buyer).status_code for _ in range(3)] == [200, 200, 429]
        assert _chat(client, interest, owner).status_code == 200


class TestBlock:
    def test_blocking_stops_messages_in_both_directions_without_saying_who(self, client, pair):
        """TC-API-CHT-030 | AC-09.3 | T10 | business | after one side blocks, neither can send (403, neutral wording); only the blocker sees blocked_by_me"""
        owner, buyer, _, interest = pair
        assert client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(buyer)).json() == {"blocked": True}
        for who in (owner, buyer):
            response = _say(client, interest, who)
            assert response.status_code == 403 and "block" not in response.json()["detail"].lower()
        as_buyer, as_owner = _chat(client, interest, buyer).json(), _chat(client, interest, owner).json()
        assert (as_buyer["blocked_by_me"], as_buyer["can_send"]) == (True, False)
        assert (as_owner["blocked_by_me"], as_owner["can_send"]) == (False, False)

    def test_unblocking_restores_the_chat(self, client, pair):
        """TC-API-CHT-031 | AC-09.3 | T10 | positive | DELETE on block lets both talk again; repeating it is harmless"""
        owner, buyer, _, interest = pair
        client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(owner))
        assert client.delete(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(owner)).json() == {"blocked": False}
        assert client.delete(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(owner)).status_code == 200
        assert _say(client, interest, buyer).status_code == 201

    def test_blocking_twice_stores_one_row(self, client, db_session, pair):
        """TC-API-CHT-032 | AC-19.1 | T02 | boundary | the block is idempotent: repeating it neither errors nor duplicates the row"""
        _, buyer, _, interest = pair
        for _ in range(3):
            assert client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(buyer)).status_code == 200
        assert db_session.scalar(select(func.count()).select_from(UserBlock)) == 1

    def test_the_other_side_cannot_remove_my_block(self, client, pair):
        """TC-API-CHT-033 | AC-09.3 | T10 | negative | the blocked person's DELETE removes only their own (non-existent) block; the chat stays blocked"""
        owner, buyer, _, interest = pair
        client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(owner))
        client.delete(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(buyer))
        assert _say(client, interest, buyer).status_code == 403

    def test_a_block_applies_to_every_enquiry_between_the_two(self, client, db_session, pair):
        """TC-API-CHT-034 | AC-09.3 | T10 | business | a block is between two people, so it also silences a second chat they share"""
        owner, buyer, _, interest = pair
        second = add_interest(db_session, add_listing(db_session, owner), buyer, InterestStatus.ACCEPTED)
        client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(owner))
        assert _say(client, second, buyer).status_code == 403

    def test_block_is_rate_limited(self, client, pair, monkeypatch):
        """TC-API-CHT-035 | AC-09.3 | T13 | boundary | with the action limit at 1 the second block/unblock call is 429"""
        _, buyer, _, interest = pair
        monkeypatch.setattr(rate_limit.action_limiter, "max_requests", 1)
        assert client.post(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(buyer)).status_code == 200
        assert client.delete(f"{INTERESTS}/{interest.id}/block", headers=auth_headers(buyer)).status_code == 429


class TestReport:
    def test_a_report_is_stored_against_the_other_person(self, client, db_session, pair):
        """TC-API-CHT-040 | AC-09.3 | T10 | positive | reporting stores who reported whom, for which enquiry, and why"""
        owner, buyer, _, interest = pair
        response = client.post(f"{INTERESTS}/{interest.id}/report", json={"reason": "  Asked for money upfront  "}, headers=auth_headers(buyer))
        assert response.status_code == 201
        (report,) = db_session.scalars(select(Report)).all()
        assert (report.reporter_id, report.reported_user_id, report.interest_id) == (buyer.id, owner.id, interest.id)
        assert report.reason == "Asked for money upfront"

    @pytest.mark.parametrize("reason, expected", [("", 422), ("abcd", 422), ("     ", 422), ("abcde", 201), ("r" * 500, 201), ("r" * 501, 422)])
    def test_reason_length_boundary(self, client, pair, reason, expected):
        """TC-API-CHT-041 | AC-18.1 | T16 | boundary | a reason needs at least 5 characters after trimming and at most 500"""
        _, buyer, _, interest = pair
        assert client.post(f"{INTERESTS}/{interest.id}/report", json={"reason": reason}, headers=auth_headers(buyer)).status_code == expected

    def test_reporting_does_not_block_or_close_the_chat(self, client, pair):
        """TC-API-CHT-042 | AC-09.3 | T10 | business | a report alone changes nothing for the two people; blocking is a separate choice"""
        owner, buyer, _, interest = pair
        client.post(f"{INTERESTS}/{interest.id}/report", json={"reason": "rude messages"}, headers=auth_headers(buyer))
        assert _say(client, interest, owner).status_code == 201

    def test_admin_can_read_reports_and_nobody_else_can(self, client, db_session, pair):
        """TC-API-CHT-043 | AC-13.1 | T12 | positive | GET /admin/reports lists reporter, reported person, item and reason for admins only"""
        owner, buyer, listing, interest = pair
        client.post(f"{INTERESTS}/{interest.id}/report", json={"reason": "Asked for money upfront"}, headers=auth_headers(buyer))
        admin = make_user(db_session, is_admin=True)
        body = client.get("/api/admin/reports", headers=auth_headers(admin)).json()
        assert body["total"] == 1
        (item,) = body["items"]
        assert (item["reporter_name"], item["reported_name"], item["listing_title"], item["reason"]) == (
            buyer.name, owner.name, listing.title, "Asked for money upfront")
        assert client.get("/api/admin/reports", headers=auth_headers(buyer)).status_code == 403

    def test_report_is_rate_limited(self, client, pair, monkeypatch):
        """TC-API-CHT-044 | AC-09.3 | T13 | boundary | with the action limit at 1 the second report is 429"""
        _, buyer, _, interest = pair
        monkeypatch.setattr(rate_limit.action_limiter, "max_requests", 1)
        body = {"reason": "spam spam spam"}
        assert client.post(f"{INTERESTS}/{interest.id}/report", json=body, headers=auth_headers(buyer)).status_code == 201
        assert client.post(f"{INTERESTS}/{interest.id}/report", json=body, headers=auth_headers(buyer)).status_code == 429


class TestCascades:
    def test_deleting_the_listing_removes_its_messages(self, client, db_session, pair, monkeypatch):
        """TC-API-CHT-050 | AC-19.3 | T09 | business | deleting an item deletes its enquiries and their chat messages"""
        from tests.support import install_fake_cloudinary

        install_fake_cloudinary(monkeypatch)
        owner, buyer, listing, interest = pair
        listing_id = listing.id
        _say(client, interest, buyer)
        assert client.delete(f"/api/listings/{listing_id}", headers=auth_headers(owner)).status_code == 200
        db_session.expire_all()
        assert db_session.scalar(select(func.count()).select_from(Message)) == 0
        assert db_session.get(Listing, listing_id) is None

    def test_an_admin_unlisting_does_not_delete_the_chat(self, client, db_session, pair):
        """TC-API-CHT-051 | AC-13.1 | T12 | business | changing an item's status leaves the thread readable"""
        owner, buyer, listing, interest = pair
        _say(client, interest, buyer)
        listing.status = ListingStatus.UNAVAILABLE
        db_session.commit()
        assert len(_chat(client, interest, owner).json()["messages"]) == 1
