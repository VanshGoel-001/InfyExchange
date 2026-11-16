"""API tests: the listing detail returns every photo in upload order; admin overview counts and member filter."""

import pytest

from tests.conftest import auth_headers, make_user
from tests.support import add_image, add_interest, add_listing, image_part, install_fake_cloudinary, listing_form
from app.models import FailedEmail, Report
from app.utils.enums import InterestStatus
from datetime import datetime

LISTINGS = "/api/listings"
ADMIN = "/api/admin"


class TestDetailPhotos:
    def test_detail_returns_every_uploaded_photo_in_upload_order(self, client, db_session, monkeypatch):
        """TC-API-DTL-001 | AC-04.5, AC-05.3 | T08, T09 | positive | five uploaded photos are saved and GET /listings/{id} returns all five, first upload first"""
        install_fake_cloudinary(monkeypatch)
        owner = make_user(db_session)
        created = client.post(
            LISTINGS,
            data=listing_form(),
            files=[image_part(f"{i}.png") for i in range(5)],
            headers=auth_headers(owner),
        ).json()
        detail = client.get(f"{LISTINGS}/{created['id']}").json()
        urls = [image["image_url"] for image in detail["images"]]
        assert urls == [f"https://res.cloudinary.com/test/{created['id']}/{n}.png" for n in range(1, 6)]
        assert detail["image_url"] == urls[0]

    def test_photos_come_back_in_upload_order_even_if_inserted_out_of_order(self, client, db_session):
        """TC-API-DTL-002 | AC-05.3 | T08 | boundary | the images list is ordered by id, not by whatever order the database returns"""
        listing = add_listing(db_session, make_user(db_session))
        for n in (3, 1, 2):
            add_image(db_session, listing, url=f"https://res.cloudinary.com/test/{n}.png")
        urls = [i["image_url"] for i in client.get(f"{LISTINGS}/{listing.id}").json()["images"]]
        assert urls == [f"https://res.cloudinary.com/test/{n}.png" for n in (3, 1, 2)]


class TestAdminOverview:
    @pytest.fixture()
    def admin(self, db_session):
        return make_user(db_session, is_admin=True)

    def test_stats_include_enquiry_breakdown_reports_and_failed_emails(self, client, db_session, admin):
        """TC-API-ADM-040 | AC-12.2 | T12 | positive | stats report pending/declined enquiries, reports and failed emails next to the existing totals"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        add_interest(db_session, listing, buyer, InterestStatus.PENDING)
        add_interest(db_session, listing, make_user(db_session), InterestStatus.ACCEPTED)
        add_interest(db_session, listing, make_user(db_session), InterestStatus.REJECTED)
        db_session.add(FailedEmail(
            to_email="a@gmail.com", subject="s", html="h", error="e", attempts=1,
            created_at=datetime.utcnow(), last_attempt_at=datetime.utcnow(),
        ))
        db_session.commit()
        body = client.get(f"{ADMIN}/stats", headers=auth_headers(admin)).json()
        assert (body["pending_interests"], body["accepted_interests"], body["rejected_interests"]) == (1, 1, 1)
        assert body["total_interests"] == 3
        assert body["failed_emails"] == 1
        assert body["total_reports"] == 0

    def test_members_can_be_filtered_by_status(self, client, db_session, admin):
        """TC-API-ADM-041 | AC-12.2 | T12 | positive | ?status=deactivated lists only deactivated members; ?status=active only active ones"""
        blocked = make_user(db_session, is_active=False)
        active = make_user(db_session)
        headers = auth_headers(admin)
        deactivated = client.get(f"{ADMIN}/users", params={"status": "deactivated"}, headers=headers).json()
        assert [u["id"] for u in deactivated["items"]] == [blocked.id]
        actives = {u["id"] for u in client.get(f"{ADMIN}/users", params={"status": "active"}, headers=headers).json()["items"]}
        assert {admin.id, active.id} == actives
        assert client.get(f"{ADMIN}/users", params={"status": "nonsense"}, headers=headers).status_code == 422
