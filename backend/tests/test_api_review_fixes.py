"""Regression tests for problems found in the whole-project review.

Each class pins one fixed problem. TC ids are new (TC-REV-*); AC/T columns reuse the nearest
derived criteria because no approved spec exists for these (see test.md).
"""

import asyncio
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Interest, Listing, Notification
from app.services import cleanup
from app.services.maintenance import run_maintenance
from app.utils.enums import InterestStatus, ListingStatus, ListingType
from tests.conftest import auth_headers, make_user
from tests.support import (
    add_interest,
    add_listing,
    image_part,
    install_fake_cloudinary,
    listing_form,
    need_payload,
)

INTERESTS = "/api/interests"
LISTINGS = "/api/listings"
NEEDS = "/api/needs"
NOW = datetime(2026, 11, 14, 12, 0, 0)


def _enquire(client, user, listing, message="hi"):
    return client.post(f"{INTERESTS}/listing/{listing.id}", json={"message": message}, headers=auth_headers(user))


class TestReEnquiryAfterClosure:
    """A closed enquiry used to block the person from ever enquiring about the same item again."""

    def _returned_loan(self, client, db):
        owner, borrower, rival = make_user(db), make_user(db), make_user(db)
        listing = add_listing(db, owner, listing_type=ListingType.LEND, price=0)
        won = add_interest(db, listing, borrower, InterestStatus.ACCEPTED)
        lost = add_interest(db, listing, rival, InterestStatus.PENDING)
        client.post(f"{INTERESTS}/{won.id}/close-deal", headers=auth_headers(owner))
        client.post(f"{LISTINGS}/{listing.id}/mark-returned", headers=auth_headers(owner))
        db.expire_all()
        return owner, borrower, rival, listing, won.id, lost.id

    def test_everyone_can_enquire_again_once_the_item_is_available(self, client, db_session):
        """TC-REV-001 | AC-09.2 | T10 | business | after a loan is returned both the borrower and the auto-closed rival can enquire again (201), reusing their enquiry"""
        owner, borrower, rival, listing, won_id, lost_id = self._returned_loan(client, db_session)
        assert db_session.get(Interest, lost_id).status == InterestStatus.CLOSED
        for user, old_id in ((rival, lost_id), (borrower, won_id)):
            response = _enquire(client, user, listing, "can I have it this weekend?")
            assert response.status_code == 201
            assert response.json()["id"] == old_id  # one row per person and item, as the constraint requires
            assert response.json()["status"] == "PENDING"
        db_session.expire_all()
        reopened = db_session.get(Interest, won_id)
        assert reopened.message == "can I have it this weekend?"
        assert (reopened.deal_closed_at, reopened.returned_at, reopened.received_confirmed) == (None, None, None)

    def test_a_reopened_enquiry_notifies_the_owner_and_alerts_the_admin_again(self, client, db_session, brevo):
        """TC-REV-002 | AC-09.1 | T10 | business | reopening behaves like a new enquiry: bell notification for the owner and one admin alert"""
        owner, _, rival, listing, _, _ = self._returned_loan(client, db_session)
        before_notes = db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == owner.id))
        brevo.requests.clear()
        assert _enquire(client, rival, listing).status_code == 201
        after_notes = db_session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == owner.id))
        assert after_notes == before_notes + 1
        assert len(brevo.requests) == 1

    def test_the_seven_day_clock_restarts_on_reopening(self, client, db_session):
        """TC-REV-003 | AC-14.1 | T15 | business | a buyer whose enquiry expired can enquire again, and that new enquiry expires 7 days after the new request, not at once"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        enquiry = add_interest(db_session, listing, buyer)
        enquiry.created_at = datetime.utcnow() - timedelta(days=8)
        db_session.commit()
        assert run_maintenance()["expired"] == 1
        assert _enquire(client, buyer, listing).status_code == 201
        assert run_maintenance()["expired"] == 0  # not expired again straight away
        db_session.expire_all()
        assert db_session.get(Interest, enquiry.id).status == InterestStatus.PENDING
        assert run_maintenance(datetime.utcnow() + timedelta(days=7, minutes=1))["expired"] == 1

    @pytest.mark.parametrize("status", [InterestStatus.PENDING, InterestStatus.ACCEPTED, InterestStatus.REJECTED])
    def test_pending_chatting_and_declined_stay_final(self, client, db_session, status):
        """TC-REV-004 | AC-09.2 | T10 | negative | only CLOSED reopens; a pending, chatting or declined enquiry is still 409 (a decline is the owner's explicit no)"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        enquiry = add_interest(db_session, listing, buyer, status)
        response = _enquire(client, buyer, listing)
        assert response.status_code == 409 and response.json()["detail"] == "You already showed interest"
        db_session.refresh(enquiry)
        assert enquiry.status == status

    def test_no_reopening_while_the_item_is_not_available(self, client, db_session):
        """TC-REV-005 | AC-09.2 | T10 | negative | a closed-out buyer still cannot enquire about an item that is Sold or Lent out (400)"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, status=ListingStatus.SOLD)
        add_interest(db_session, listing, buyer, InterestStatus.CLOSED)
        assert _enquire(client, buyer, listing).status_code == 400


class TestBlankText:
    """Spaces counted toward min_length, so "   " was saved as an empty title, location or description."""

    @pytest.mark.parametrize("field", ["title", "location", "description"])
    def test_listing_text_of_only_spaces_is_rejected(self, client, db_session, monkeypatch, field):
        """TC-REV-010 | AC-06.1 | T08 | negative | a listing whose title, location or description is only spaces is 422 naming the field, and nothing is created"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        response = client.post(LISTINGS, data=listing_form(**{field: "   "}), headers=auth_headers(user))
        assert response.status_code == 422
        assert response.json()["detail"].startswith(f"{field}:")
        assert db_session.scalar(select(func.count()).select_from(Listing)) == 0

    def test_listing_text_is_judged_after_trimming(self, client, db_session, monkeypatch):
        """TC-REV-011 | AC-06.1 | T08 | boundary | ' a ' is one character (422); '  ab  ' is two and is stored trimmed"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        assert client.post(LISTINGS, data=listing_form(title=" a "), headers=auth_headers(user)).status_code == 422
        response = client.post(LISTINGS, data=listing_form(title="  ab  "), headers=auth_headers(user))
        assert response.status_code == 201 and response.json()["title"] == "ab"

    @pytest.mark.parametrize("field", ["title", "location", "description"])
    def test_need_text_of_only_spaces_is_rejected(self, client, db_session, field):
        """TC-REV-012 | AC-08.2 | T11 | negative | a request whose title, location or description is only spaces is 422"""
        user = make_user(db_session)
        response = client.post(NEEDS, json=need_payload(**{field: "   "}), headers=auth_headers(user))
        assert response.status_code == 422
        assert response.json()["detail"].startswith(field)

    def test_need_text_is_stored_trimmed(self, client, db_session):
        """TC-REV-013 | AC-08.2 | T11 | business | surrounding spaces are removed from need text before it is saved"""
        user = make_user(db_session)
        body = client.post(NEEDS, json=need_payload(title="  Squash racket  ", location="  ECC "), headers=auth_headers(user)).json()
        assert (body["title"], body["location"]) == ("Squash racket", "ECC")


class TestAmountCaps:
    """Amounts above PostgreSQL's 32-bit integer made the database error out as a 500."""

    @pytest.mark.parametrize("price, expected", [(10_000_000, 201), (10_000_001, 422), (3_000_000_000, 422)])
    def test_listing_price_cap(self, client, db_session, monkeypatch, price, expected):
        """TC-REV-020 | AC-06.1 | T08 | boundary | a listing price up to 10,000,000 is accepted; more is a 422, never a 500"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        assert client.post(LISTINGS, data=listing_form(price=price), headers=auth_headers(user)).status_code == expected

    @pytest.mark.parametrize("budget, expected", [(10_000_000, 201), (10_000_001, 422), (3_000_000_000, 422)])
    def test_need_budget_cap(self, client, db_session, budget, expected):
        """TC-REV-021 | AC-08.2 | T11 | boundary | a request budget up to 10,000,000 is accepted; more is a 422, never a 500"""
        user = make_user(db_session)
        assert client.post(NEEDS, json=need_payload(budget=budget), headers=auth_headers(user)).status_code == expected


class TestAdminSelfProtection:
    def test_an_admin_cannot_deactivate_their_own_account(self, client, db_session):
        """TC-REV-030 | AC-13.2 | T12 | negative | deactivating yourself is 400 and leaves you able to use the API; other members can still be deactivated"""
        admin, member = make_user(db_session, is_admin=True), make_user(db_session)
        response = client.patch(f"/api/admin/users/{admin.id}", json={"is_active": False}, headers=auth_headers(admin))
        assert response.status_code == 400 and "own account" in response.json()["detail"]
        assert client.get("/api/auth/me", headers=auth_headers(admin)).status_code == 200
        assert client.patch(f"/api/admin/users/{member.id}", json={"is_active": False}, headers=auth_headers(admin)).status_code == 200


class TestCleanupLoopDoesNotBlock:
    def test_the_event_loop_keeps_running_while_cleanup_works(self, monkeypatch):
        """TC-REV-040 | AC-14.1 | T15 | business | while the cleanup does 0.4 s of slow work the event loop never stalls for anywhere near that long (the old loop ran it inline and froze every request)"""

        def slow_cleanup():
            time.sleep(0.4)  # stands in for slow database and Cloudinary calls

        monkeypatch.setattr(cleanup, "cleanup_expired_data", slow_cleanup)

        async def scenario():
            longest_stall = 0.0

            async def ticker():
                nonlocal longest_stall
                last = time.monotonic()
                while True:
                    await asyncio.sleep(0.01)
                    now = time.monotonic()
                    longest_stall = max(longest_stall, now - last)
                    last = now

            tick_task = asyncio.create_task(ticker())
            loop_task = asyncio.create_task(cleanup.cleanup_loop())
            await asyncio.sleep(0.7)
            for task in (loop_task, tick_task):
                task.cancel()
            await asyncio.gather(loop_task, tick_task, return_exceptions=True)
            return longest_stall

        # Blocked inline: about 0.4 s. Off the loop: a few milliseconds.
        assert asyncio.run(scenario()) < 0.2


class TestFailedImageCleanup:
    def test_a_cloudinary_outage_while_undoing_a_failed_upload_does_not_leave_a_half_listing(self, client, db_session, monkeypatch):
        """TC-REV-050 | AC-06.4 | T09 | negative | if an upload fails and removing the images already uploaded also fails, the listing is still deleted and the answer is the normal 400"""
        install_fake_cloudinary(monkeypatch, fail_on={2}, delete_raises=True)
        user = make_user(db_session)
        files = [image_part("a.png"), image_part("b.png")]
        response = client.post(LISTINGS, data=listing_form(), files=files, headers=auth_headers(user))
        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to upload images. Please try again."
        assert db_session.scalar(select(func.count()).select_from(Listing)) == 0
