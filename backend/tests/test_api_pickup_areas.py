"""API tests: pickup areas on listings (area dropdown, optional block number, filter, admin editing).

Cloudinary is replaced by ``tests.support.FakeCloudinary``. The areas themselves are seeded by
``tests/conftest.py`` the way the migration seeds them (id 1 = ECC with blocks).
"""

import pytest
from sqlalchemy import select

from app.models import AuditLog, Listing, PickupArea
from tests.conftest import auth_headers, make_user
from tests.support import add_listing, image_part, install_fake_cloudinary, listing_form

LISTINGS = "/api/listings"
AREAS = "/api/pickup-areas"
ADMIN_AREAS = "/api/admin/pickup-areas"
ECC, GEC1, OTHER = 1, 2, 6


def _post(client, user, **form):
    return client.post(LISTINGS, data=listing_form(**form), headers=auth_headers(user))


class TestPublicAreaList:
    def test_lists_active_areas_in_order_without_login(self, client, db_session):
        """TC-API-PKA-001 | AC-04.3 | T08 | positive | GET /pickup-areas is public and returns the active areas in sort order"""
        db_session.get(PickupArea, GEC1).is_active = False
        db_session.commit()
        body = client.get(AREAS).json()
        assert [a["name"] for a in body] == ["ECC", "GEC 2", "Recreational Center", "Food Court", "Other"]
        assert body[0] == {"id": ECC, "name": "ECC", "has_blocks": True}


class TestCreateWithArea:
    def test_area_and_block_are_stored_separately_and_shown_together(self, client, db_session, monkeypatch):
        """TC-API-PKA-002 | AC-04.3 | T08 | positive | ECC + block 87 is stored as two fields and displayed as 'ECC - 87'"""
        install_fake_cloudinary(monkeypatch)
        body = _post(client, make_user(db_session), pickup_area_id=ECC, block_no=87).json()
        assert (body["pickup_area_id"], body["pickup_area"], body["block_no"]) == (ECC, "ECC", 87)
        assert body["location"] == "ECC - 87"

    def test_block_is_optional(self, client, db_session, monkeypatch):
        """TC-API-PKA-003 | AC-04.3 | T08 | positive | ECC without a block displays as 'ECC'"""
        install_fake_cloudinary(monkeypatch)
        body = _post(client, make_user(db_session), pickup_area_id=ECC).json()
        assert (body["block_no"], body["location"]) == (None, "ECC")

    @pytest.mark.parametrize("block, expected", [(0, 422), (1, 201), (100, 201), (101, 422), (-5, 422)])
    def test_block_number_boundaries(self, client, db_session, monkeypatch, block, expected):
        """TC-API-PKA-004 | AC-04.3 | T08 | boundary | block number must be 1-100"""
        install_fake_cloudinary(monkeypatch)
        assert _post(client, make_user(db_session), pickup_area_id=ECC, block_no=block).status_code == expected

    def test_block_on_an_area_without_blocks_is_rejected(self, client, db_session, monkeypatch):
        """TC-API-PKA-005 | AC-04.3 | T08 | negative | GEC 1 has no blocks, so a block number is 422 and nothing is created"""
        install_fake_cloudinary(monkeypatch)
        assert _post(client, make_user(db_session), pickup_area_id=GEC1, block_no=3).status_code == 422
        assert db_session.scalars(select(Listing)).all() == []

    def test_inactive_or_unknown_area_is_rejected(self, client, db_session, monkeypatch):
        """TC-API-PKA-006 | AC-04.3 | T08 | negative | a deactivated or non-existent area cannot be chosen"""
        install_fake_cloudinary(monkeypatch)
        db_session.get(PickupArea, GEC1).is_active = False
        db_session.commit()
        user = make_user(db_session)
        assert _post(client, user, pickup_area_id=GEC1).status_code == 422
        assert _post(client, user, pickup_area_id=999).status_code == 422

    def test_area_is_required_and_free_text_location_is_ignored(self, client, db_session, monkeypatch):
        """TC-API-PKA-007 | AC-04.3 | T08 | negative | without pickup_area_id the request is 422 even if an old-style location is sent"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        assert _post(client, user, pickup_area_id=None).status_code == 422
        assert _post(client, user, pickup_area_id=None, location="ECC 87").status_code == 422

    def test_upload_validation_message_reaches_the_user(self, client, db_session, monkeypatch):
        """TC-API-PKA-008 | AC-16.1 | T09 | business | a too-small image is a 400 that says so, and the listing is rolled back"""
        install_fake_cloudinary(monkeypatch, invalid_on=(1,))
        response = client.post(
            LISTINGS, data=listing_form(), files=[image_part()], headers=auth_headers(make_user(db_session))
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Image is too small. Use a photo at least 600 pixels wide."
        assert db_session.scalars(select(Listing)).all() == []


class TestFilterByArea:
    def test_filter_by_area_and_block(self, client, db_session):
        """TC-API-PKA-009 | AC-05.2 | T08 | positive | pickup_area_id narrows to that area; block_no narrows further"""
        owner = make_user(db_session)
        add_listing(db_session, owner, title="ecc87", pickup_area_id=ECC, block_no=87, location="ECC - 87")
        add_listing(db_session, owner, title="ecc92", pickup_area_id=ECC, block_no=92, location="ECC - 92")
        add_listing(db_session, owner, title="gec", pickup_area_id=GEC1, location="GEC 1")

        def titles(params):
            return sorted(i["title"] for i in client.get(LISTINGS, params=params).json())

        assert titles({"pickup_area_id": ECC}) == ["ecc87", "ecc92"]
        assert titles({"pickup_area_id": ECC, "block_no": 87}) == ["ecc87"]
        assert titles({"pickup_area_id": GEC1}) == ["gec"]

    def test_block_filter_range(self, client):
        """TC-API-PKA-010 | AC-05.2 | T08 | boundary | block_no outside 1-100 is 422"""
        assert client.get(LISTINGS, params={"block_no": 0}).status_code == 422
        assert client.get(LISTINGS, params={"block_no": 101}).status_code == 422


class TestAdminAreas:
    @pytest.fixture()
    def admin(self, db_session):
        return make_user(db_session, is_admin=True)

    def test_non_admin_cannot_manage_areas(self, client, db_session):
        """TC-API-PKA-011 | AC-12.1 | T12 | negative | members get 403 and anonymous callers are rejected on every area route"""
        member = make_user(db_session)
        assert client.get(ADMIN_AREAS, headers=auth_headers(member)).status_code == 403
        assert client.post(ADMIN_AREAS, json={"name": "Gym"}, headers=auth_headers(member)).status_code == 403
        assert client.patch(f"{ADMIN_AREAS}/{OTHER}", json={"is_active": False}, headers=auth_headers(member)).status_code == 403
        assert client.get(ADMIN_AREAS).status_code in (401, 403)

    def test_create_appends_and_is_audited(self, client, db_session, admin):
        """TC-API-PKA-012 | AC-12.4 | T12 | positive | a new area goes to the end of the list, is active, and writes an audit entry"""
        response = client.post(ADMIN_AREAS, json={"name": "  Sports   Hall ", "has_blocks": True}, headers=auth_headers(admin))
        assert response.status_code == 201
        body = response.json()
        assert (body["name"], body["has_blocks"], body["is_active"], body["sort_order"]) == ("Sports Hall", True, True, 7)
        entry = db_session.scalars(select(AuditLog).where(AuditLog.action == "CREATE_PICKUP_AREA")).one()
        assert entry.actor_id == admin.id and entry.target_id == str(body["id"])
        assert "Sports Hall" in [a["name"] for a in client.get(AREAS).json()]

    def test_duplicate_name_is_a_conflict_ignoring_case(self, client, admin):
        """TC-API-PKA-013 | AC-12.4 | T12 | negative | 'ecc' collides with 'ECC' on create and on rename"""
        headers = auth_headers(admin)
        assert client.post(ADMIN_AREAS, json={"name": "ecc"}, headers=headers).status_code == 409
        assert client.patch(f"{ADMIN_AREAS}/{GEC1}", json={"name": "Ecc"}, headers=headers).status_code == 409

    def test_blank_name_and_unknown_fields_are_rejected(self, client, admin):
        """TC-API-PKA-014 | AC-12.4 | T12 | negative | whitespace-only names and unknown fields are 422"""
        headers = auth_headers(admin)
        assert client.post(ADMIN_AREAS, json={"name": "   "}, headers=headers).status_code == 422
        assert client.post(ADMIN_AREAS, json={"name": "Gym", "sort_order": 1}, headers=headers).status_code == 422
        assert client.patch(f"{ADMIN_AREAS}/{GEC1}", json={"id": 99}, headers=headers).status_code == 422

    def test_rename_updates_the_text_on_existing_listings(self, client, db_session, admin):
        """TC-API-PKA-015 | AC-12.4 | T12 | business | renaming ECC changes 'ECC - 87' to 'Engineering Center - 87' on its listings"""
        add_listing(db_session, make_user(db_session), pickup_area_id=ECC, block_no=87, location="ECC - 87")
        response = client.patch(f"{ADMIN_AREAS}/{ECC}", json={"name": "Engineering Center"}, headers=auth_headers(admin))
        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.scalars(select(Listing)).one().location == "Engineering Center - 87"

    def test_deactivating_keeps_existing_listings_but_hides_the_area(self, client, db_session, admin):
        """TC-API-PKA-016 | AC-12.4 | T12 | business | an inactive area leaves the public list; listings in it are unchanged"""
        add_listing(db_session, make_user(db_session), pickup_area_id=GEC1, location="GEC 1")
        client.patch(f"{ADMIN_AREAS}/{GEC1}", json={"is_active": False}, headers=auth_headers(admin))
        assert "GEC 1" not in [a["name"] for a in client.get(AREAS).json()]
        assert "GEC 1" in [a["name"] for a in client.get(ADMIN_AREAS, headers=auth_headers(admin)).json()]
        assert client.get(LISTINGS).json()[0]["pickup_area"] == "GEC 1"

    def test_unknown_area_is_404(self, client, admin):
        """TC-API-PKA-017 | AC-12.4 | T12 | negative | patching an id that does not exist is 404"""
        assert client.patch(f"{ADMIN_AREAS}/999", json={"is_active": False}, headers=auth_headers(admin)).status_code == 404
