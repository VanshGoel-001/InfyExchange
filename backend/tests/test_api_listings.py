"""API tests: listings (tasks T08, T09 via mocks, T13).

Cloudinary is replaced by ``tests.support.FakeCloudinary`` wherever a request would upload
or delete an image. Real image validation is covered in test_service_cloudinary.py.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Interest, Listing, ListingImage
from app.services import rate_limit
from app.utils.enums import InterestStatus, ItemCondition, ListingCategory, ListingStatus, ListingType
from tests.conftest import auth_headers, make_user
from tests.support import (
    add_image,
    add_interest,
    add_listing,
    image_part,
    install_fake_cloudinary,
    listing_form,
)

LISTINGS = "/api/listings"


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _create(client, user, files=None, **form):
    return client.post(LISTINGS, data=listing_form(**form), files=files or None, headers=auth_headers(user))


class TestCreateListing:
    def test_valid_listing_is_created_active_and_owned(self, client, db_session, monkeypatch):
        """TC-API-LST-001 | AC-04.1 | T08 | positive | 201; caller is owner; status ACTIVE; fields echoed"""
        install_fake_cloudinary(monkeypatch)
        owner = make_user(db_session)
        response = _create(client, owner, title="Yonex racket")
        assert response.status_code == 201
        body = response.json()
        assert body["owner_id"] == owner.id
        assert body["status"] == "ACTIVE"
        assert body["title"] == "Yonex racket"
        assert body["category"] == "BADMINTON"
        assert body["listing_type"] == "SELL"
        assert body["price"] == 500
        assert body["owner_name"] == owner.name
        assert body["images"] == []

    def test_expiry_is_listing_expiry_days_after_creation(self, client, db_session, monkeypatch):
        """TC-API-LST-002 | AC-04.1 | T08 | business | expires_at is created_at + LISTING_EXPIRY_DAYS (30)"""
        install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session)).json()
        created = datetime.fromisoformat(body["created_at"])
        expires = datetime.fromisoformat(body["expires_at"])
        assert expires - created == timedelta(days=settings.listing_expiry_days)

    def test_title_and_text_fields_are_trimmed(self, client, db_session, monkeypatch):
        """TC-API-LST-003 | AC-04.3 | T08 | business | surrounding whitespace is stripped before saving"""
        install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session), title="  Racket  ", location="  ECC  ", description="  Good  ").json()
        assert (body["title"], body["location"], body["description"]) == ("Racket", "ECC", "Good")

    def test_unauthenticated_create_is_rejected(self, client):
        """TC-API-LST-004 | AC-04.6 | T08 | negative | no token: 401/403 and nothing is created"""
        response = client.post(LISTINGS, data=listing_form())
        assert response.status_code in (401, 403)

    @pytest.mark.parametrize(
        "listing_type, price, expected_detail",
        [
            ("SELL", 0, "Sell listings must have a price"),
            ("SELL", None, "Sell listings must have a price"),
            ("RENT", 0, "Rent listings must have a price"),
        ],
        ids=["sell-zero", "sell-omitted", "rent-zero"],
    )
    def test_paid_types_require_positive_price(self, client, db_session, monkeypatch, listing_type, price, expected_detail):
        """TC-API-LST-005 | AC-04.2 | T08 | negative | SELL and RENT without a price > 0 get 400"""
        install_fake_cloudinary(monkeypatch)
        response = _create(client, make_user(db_session), listing_type=listing_type, price=price)
        assert response.status_code == 400
        assert response.json()["detail"] == expected_detail

    def test_price_of_one_is_the_minimum_valid_sell_price(self, client, db_session, monkeypatch):
        """TC-API-LST-006 | AC-04.2 | T08 | boundary | price 1 is accepted for SELL"""
        install_fake_cloudinary(monkeypatch)
        assert _create(client, make_user(db_session), price=1).status_code == 201

    @pytest.mark.parametrize("listing_type", ["LEND", "GIVEAWAY"])
    def test_free_types_force_zero_price_and_no_unit(self, client, db_session, monkeypatch, listing_type):
        """TC-API-LST-007 | AC-04.2 | T08 | business | LEND/GIVEAWAY ignore a submitted price and unit"""
        install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session), listing_type=listing_type, price=999, price_unit="day").json()
        assert body["price"] == 0
        assert body["price_unit"] is None

    def test_rent_defaults_unit_to_day(self, client, db_session, monkeypatch):
        """TC-API-LST-008 | AC-04.2 | T08 | business | RENT without price_unit is stored per 'day'"""
        install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session), listing_type="RENT", price=50).json()
        assert body["price_unit"] == "day"

    def test_rent_keeps_explicit_unit(self, client, db_session, monkeypatch):
        """TC-API-LST-009 | AC-04.2 | T08 | positive | RENT with price_unit 'week' keeps it"""
        install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session), listing_type="RENT", price=50, price_unit="week").json()
        assert body["price_unit"] == "week"

    @pytest.mark.parametrize(
        "field, length, expected",
        [
            ("title", 1, 422), ("title", 2, 201), ("title", 150, 201), ("title", 151, 422),
            ("location", 1, 422), ("location", 2, 201), ("location", 100, 201), ("location", 101, 422),
            ("description", 1, 422), ("description", 2, 201), ("description", 2000, 201), ("description", 2001, 422),
        ],
    )
    def test_text_field_length_boundaries(self, client, db_session, monkeypatch, field, length, expected):
        """TC-API-LST-010 | AC-04.3 | T08 | boundary | title 2-150, location 2-100, description 2-2000 characters"""
        install_fake_cloudinary(monkeypatch)
        response = _create(client, make_user(db_session), **{field: "x" * length})
        assert response.status_code == expected

    @pytest.mark.parametrize(
        "overrides",
        [
            {"price": -1},
            {"price": "abc"},
            {"category": "GOLF"},
            {"listing_type": "TRADE"},
            {"condition": "BROKEN"},
            {"title": None},
            {"description": None},
        ],
        ids=["negative-price", "non-numeric-price", "bad-category", "bad-type", "bad-condition", "no-title", "no-description"],
    )
    def test_invalid_or_missing_fields_are_422(self, client, db_session, monkeypatch, overrides):
        """TC-API-LST-011 | AC-04.3 | T08 | negative | out-of-range, unknown-enum and missing required fields are rejected"""
        install_fake_cloudinary(monkeypatch)
        assert _create(client, make_user(db_session), **overrides).status_code == 422

    def test_identical_resubmission_returns_existing_listing(self, client, db_session, monkeypatch):
        """TC-API-LST-012 | AC-04.4 | T08 | business | the same form within the window returns the first listing; only one row exists"""
        install_fake_cloudinary(monkeypatch)
        owner = make_user(db_session)
        first = _create(client, owner)
        second = _create(client, owner)
        assert first.json()["id"] == second.json()["id"]
        assert _count(db_session, Listing) == 1

    def test_changed_content_is_not_treated_as_duplicate(self, client, db_session, monkeypatch):
        """TC-API-LST-013 | AC-04.4 | T08 | business | a different description creates a second listing"""
        install_fake_cloudinary(monkeypatch)
        owner = make_user(db_session)
        _create(client, owner, description="first version")
        _create(client, owner, description="second version")
        assert _count(db_session, Listing) == 2

    def test_other_users_identical_listing_is_not_a_duplicate(self, client, db_session, monkeypatch):
        """TC-API-LST-014 | AC-04.4 | T08 | business | duplicate detection is per owner"""
        install_fake_cloudinary(monkeypatch)
        _create(client, make_user(db_session))
        _create(client, make_user(db_session))
        assert _count(db_session, Listing) == 2

    def test_zero_second_window_disables_duplicate_detection(self, client, db_session, monkeypatch):
        """TC-API-LST-015 | AC-04.4 | T08 | boundary | with DUPLICATE_SUBMISSION_WINDOW_SECONDS=0 identical submissions both create rows"""
        install_fake_cloudinary(monkeypatch)
        monkeypatch.setattr(settings, "duplicate_submission_window_seconds", 0)
        owner = make_user(db_session)
        _create(client, owner)
        _create(client, owner)
        assert _count(db_session, Listing) == 2

    def test_listing_with_images_stores_each_and_exposes_first(self, client, db_session, monkeypatch):
        """TC-API-LST-016 | AC-04.5 | T08, T09 | positive | three uploaded images are stored and the first upload becomes the card image"""
        fake = install_fake_cloudinary(monkeypatch)
        body = _create(client, make_user(db_session), files=[image_part(f"{i}.png") for i in range(3)]).json()
        assert len(body["images"]) == 3
        assert body["image_url"] == f"https://res.cloudinary.com/test/{body['id']}/1.png"
        assert fake.upload_calls == 3
        assert _count(db_session, ListingImage) == 3

    def test_five_images_is_the_maximum_allowed(self, client, db_session, monkeypatch):
        """TC-API-LST-017 | AC-04.5 | T08 | boundary | exactly MAX_IMAGES_PER_LISTING (5) is accepted"""
        install_fake_cloudinary(monkeypatch)
        response = _create(client, make_user(db_session), files=[image_part(f"{i}.png") for i in range(5)])
        assert response.status_code == 201
        assert len(response.json()["images"]) == 5

    def test_six_images_are_rejected_without_side_effects(self, client, db_session, monkeypatch):
        """TC-API-LST-018 | AC-04.5 | T08 | boundary | a sixth image gives 400, creates no listing and uploads nothing"""
        fake = install_fake_cloudinary(monkeypatch)
        response = _create(client, make_user(db_session), files=[image_part(f"{i}.png") for i in range(6)])
        assert response.status_code == 400
        assert response.json()["detail"] == f"Maximum {settings.max_images_per_listing} images allowed"
        assert _count(db_session, Listing) == 0
        assert fake.upload_calls == 0

    def test_failed_upload_rolls_back_listing_and_prior_images(self, client, db_session, monkeypatch):
        """TC-API-LST-019 | AC-04.5, AC-19.3 | T08, T09 | negative | if image 2 fails: 400, no listing row, image 1 is deleted from Cloudinary"""
        fake = install_fake_cloudinary(monkeypatch, fail_on={2})
        response = _create(client, make_user(db_session), files=[image_part("1.png"), image_part("2.png")])
        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to upload images. Please try again."
        assert _count(db_session, Listing) == 0
        # ListingImage rows are removed by the database's ON DELETE CASCADE; SQLite (used here)
        # does not enforce foreign keys, so that part is verified manually on PostgreSQL (TC-MAN-DB-002).
        assert len(fake.deleted) == 1

    def test_creation_is_throttled_after_limit(self, client, db_session, monkeypatch):
        """TC-API-LST-020 | AC-04.6 | T08, T13 | boundary | with the create limit at 2, the third creation is 429 with Retry-After"""
        install_fake_cloudinary(monkeypatch)
        monkeypatch.setattr(rate_limit.create_limiter, "max_requests", 2)
        owner = make_user(db_session)
        assert _create(client, owner, title="one").status_code == 201
        assert _create(client, owner, title="two").status_code == 201
        response = _create(client, owner, title="three")
        assert response.status_code == 429
        assert "Retry-After" in response.headers


class TestBrowseListings:
    def test_public_access_returns_only_active_unexpired(self, client, db_session):
        """TC-API-LST-030 | AC-05.1 | T08 | business | anonymous callers see ACTIVE, unexpired listings only"""
        owner = make_user(db_session)
        add_listing(db_session, owner, title="visible")
        add_listing(db_session, owner, title="sold", status=ListingStatus.SOLD)
        add_listing(db_session, owner, title="rented", status=ListingStatus.RENTED)
        add_listing(db_session, owner, title="unavailable", status=ListingStatus.UNAVAILABLE)
        add_listing(db_session, owner, title="expired", expires_at=datetime.utcnow() - timedelta(seconds=1))
        response = client.get(LISTINGS)
        assert response.status_code == 200
        assert [item["title"] for item in response.json()] == ["visible"]

    def test_empty_marketplace_returns_empty_list(self, client):
        """TC-API-LST-031 | AC-05.1 | T08 | boundary | no listings: 200 with []"""
        response = client.get(LISTINGS)
        assert response.status_code == 200
        assert response.json() == []

    def test_search_matches_title_case_insensitively(self, client, db_session):
        """TC-API-LST-032 | AC-05.2 | T08 | positive | search is a case-insensitive title substring"""
        owner = make_user(db_session)
        add_listing(db_session, owner, title="Yonex Racket")
        add_listing(db_session, owner, title="Football")
        assert [i["title"] for i in client.get(LISTINGS, params={"search": "RACKET"}).json()] == ["Yonex Racket"]
        assert client.get(LISTINGS, params={"search": "zzz"}).json() == []

    def test_category_type_condition_and_location_filters(self, client, db_session):
        """TC-API-LST-033 | AC-05.2 | T08 | positive | enum filters match exactly; location is a case-insensitive substring"""
        owner = make_user(db_session)
        add_listing(db_session, owner, title="target", category=ListingCategory.CRICKET, listing_type=ListingType.RENT,
                    condition=ItemCondition.NEW, location="Main Gate")
        add_listing(db_session, owner, title="other")
        for params in ({"category": "CRICKET"}, {"listing_type": "RENT"}, {"condition": "NEW"}, {"location": "gate"}):
            titles = [i["title"] for i in client.get(LISTINGS, params=params).json()]
            assert titles == ["target"], params

    def test_price_bounds_are_inclusive(self, client, db_session):
        """TC-API-LST-034 | AC-05.2 | T08 | boundary | min_price and max_price include listings priced exactly at the bound"""
        owner = make_user(db_session)
        for price in (10, 20, 30):
            add_listing(db_session, owner, title=f"p{price}", price=price)

        def prices(**params):
            return sorted(i["price"] for i in client.get(LISTINGS, params=params).json())

        assert prices(min_price=20) == [20, 30]
        assert prices(max_price=20) == [10, 20]
        assert prices(min_price=20, max_price=20) == [20]
        assert prices(min_price=31) == []
        assert prices(min_price=30, max_price=10) == []

    def test_results_are_newest_first(self, client, db_session):
        """TC-API-LST-035 | AC-05.3 | T08 | business | listings are ordered by created_at descending"""
        owner = make_user(db_session)
        now = datetime.utcnow()
        for age, title in ((3, "oldest"), (2, "middle"), (1, "newest")):
            add_listing(db_session, owner, title=title, created_at=now - timedelta(minutes=age))
        assert [i["title"] for i in client.get(LISTINGS).json()] == ["newest", "middle", "oldest"]

    def test_pagination_skip_and_limit(self, client, db_session):
        """TC-API-LST-036 | AC-05.3 | T08 | boundary | limit caps page size; skip offsets; skipping past the end gives []"""
        owner = make_user(db_session)
        for _ in range(5):
            add_listing(db_session, owner)
        assert len(client.get(LISTINGS, params={"limit": 2}).json()) == 2
        assert len(client.get(LISTINGS, params={"limit": 2, "skip": 4}).json()) == 1
        assert client.get(LISTINGS, params={"skip": 10}).json() == []

    def test_default_page_size_is_20(self, client, db_session):
        """TC-API-LST-037 | AC-05.3 | T08 | boundary | with 21 listings and no limit, 20 are returned"""
        owner = make_user(db_session)
        for _ in range(21):
            add_listing(db_session, owner)
        assert len(client.get(LISTINGS).json()) == 20

    @pytest.mark.parametrize(
        "params, expected",
        [({"limit": 0}, 422), ({"limit": 1}, 200), ({"limit": 100}, 200), ({"limit": 101}, 422),
         ({"skip": -1}, 422), ({"min_price": -1}, 422), ({"max_price": -1}, 422), ({"category": "GOLF"}, 422)],
    )
    def test_query_parameter_boundaries(self, client, params, expected):
        """TC-API-LST-038 | AC-05.3 | T08 | boundary | limit 1-100, skip >= 0, prices >= 0, enum values validated"""
        assert client.get(LISTINGS, params=params).status_code == expected

    def test_payload_has_owner_summary_and_no_contact_details(self, client, db_session):
        """TC-API-LST-039 | AC-05.4, AC-10.4 | T08 | business | cards carry owner name/role and image but never email, phone or hashes"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing, url="https://res.cloudinary.com/test/first.png")
        add_image(db_session, listing, url="https://res.cloudinary.com/test/second.png")
        item = client.get(LISTINGS).json()[0]
        assert item["owner_name"] == owner.name
        assert item["owner_role"] == "SE"
        assert item["image_url"] == "https://res.cloudinary.com/test/first.png"
        for secret in ("email", "phone", "password_hash", "owner_email", "owner_phone"):
            assert secret not in item

    def test_read_throttle_returns_429_after_limit(self, client, monkeypatch):
        """TC-API-LST-040 | AC-05.5 | T08, T13 | boundary | with the read limit at 3 the fourth browse request is 429"""
        monkeypatch.setattr(rate_limit.read_limiter, "max_requests", 3)
        assert [client.get(LISTINGS).status_code for _ in range(3)] == [200, 200, 200]
        assert client.get(LISTINGS).status_code == 429


class TestListingDetail:
    def test_detail_includes_images_and_owner_name(self, client, db_session):
        """TC-API-LST-050 | AC-06.1 | T08 | positive | public detail returns the listing with all its images"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing, url="https://res.cloudinary.com/test/a.png")
        add_image(db_session, listing, url="https://res.cloudinary.com/test/b.png")
        response = client.get(f"{LISTINGS}/{listing.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == listing.id
        assert body["owner_name"] == owner.name
        assert {i["image_url"] for i in body["images"]} == {
            "https://res.cloudinary.com/test/a.png", "https://res.cloudinary.com/test/b.png"}
        assert "email" not in body and "phone" not in body

    def test_unknown_listing_is_404(self, client):
        """TC-API-LST-051 | AC-06.1 | T08 | negative | unknown id gives 404 'Listing not found'"""
        response = client.get(f"{LISTINGS}/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Listing not found"

    def test_expired_active_listing_is_404(self, client, db_session):
        """TC-API-LST-052 | AC-06.1 | T08 | boundary | an ACTIVE listing past expires_at gives 404 'Listing has expired'"""
        listing = add_listing(db_session, make_user(db_session), expires_at=datetime.utcnow() - timedelta(seconds=1))
        response = client.get(f"{LISTINGS}/{listing.id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Listing has expired"

    def test_non_numeric_id_is_422(self, client):
        """TC-API-LST-053 | AC-06.1 | T08 | negative | a non-integer id is a validation error"""
        assert client.get(f"{LISTINGS}/abc").status_code == 422


class TestMyListings:
    def test_returns_only_own_listings_of_every_status(self, client, db_session):
        """TC-API-LST-060 | AC-06.2 | T08 | business | /me includes the caller's SOLD and expired listings and excludes other users'"""
        me, other = make_user(db_session), make_user(db_session)
        add_listing(db_session, me, title="active")
        add_listing(db_session, me, title="sold", status=ListingStatus.SOLD)
        add_listing(db_session, me, title="expired", expires_at=datetime.utcnow() - timedelta(days=1))
        add_listing(db_session, other, title="not mine")
        response = client.get(f"{LISTINGS}/me", headers=auth_headers(me))
        assert response.status_code == 200
        assert sorted(i["title"] for i in response.json()) == ["active", "expired", "sold"]

    def test_requires_authentication(self, client):
        """TC-API-LST-061 | AC-06.2 | T08 | negative | /me without a token is 401/403"""
        assert client.get(f"{LISTINGS}/me").status_code in (401, 403)

    def test_pagination_applies(self, client, db_session):
        """TC-API-LST-062 | AC-06.2 | T08 | boundary | limit and skip are honoured and limit 101 is rejected"""
        me = make_user(db_session)
        for _ in range(3):
            add_listing(db_session, me)
        headers = auth_headers(me)
        assert len(client.get(f"{LISTINGS}/me", params={"limit": 2}, headers=headers).json()) == 2
        assert len(client.get(f"{LISTINGS}/me", params={"limit": 2, "skip": 2}, headers=headers).json()) == 1
        assert client.get(f"{LISTINGS}/me", params={"limit": 101}, headers=headers).status_code == 422


class TestUpdateListing:
    """Owners can change the price and nothing else (see ListingUpdate)."""

    def test_owner_can_change_the_price(self, client, db_session):
        """TC-API-LST-070 | AC-07.1 | T08 | positive | PUT {price} updates the price and leaves every other field unchanged"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, title="old", price=100, location="ECC")
        response = client.put(f"{LISTINGS}/{listing.id}", json={"price": 250}, headers=auth_headers(owner))
        assert response.status_code == 200
        body = response.json()
        assert (body["title"], body["price"], body["location"], body["status"]) == ("old", 250, "ECC", "ACTIVE")

    @pytest.mark.parametrize(
        "body",
        [{"title": "new"}, {"status": "SOLD"}, {"location": "elsewhere"}, {"description": "changed"},
         {"condition": "POOR"}, {"price_unit": "week"}, {"price": 200, "title": "new"}],
    )
    def test_every_other_field_is_locked(self, client, db_session, body):
        """TC-API-LST-071 | AC-07.1 | T08 | negative | any field besides price is rejected with 422 and nothing is saved"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, title="same", price=100)
        response = client.put(f"{LISTINGS}/{listing.id}", json=body, headers=auth_headers(owner))
        assert response.status_code == 422
        db_session.refresh(listing)
        assert (listing.title, listing.price, listing.status) == ("same", 100, ListingStatus.ACTIVE)

    def test_price_is_required(self, client, db_session):
        """TC-API-LST-072 | AC-07.1 | T08 | negative | PUT {} is rejected: there is nothing to change"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        assert client.put(f"{LISTINGS}/{listing.id}", json={}, headers=auth_headers(owner)).status_code == 422

    def test_unknown_listing_is_404_and_anonymous_is_rejected(self, client, db_session):
        """TC-API-LST-073 | AC-07.2 | T08 | negative | PUT on a missing id is 404; PUT without a token is 401/403"""
        owner = make_user(db_session)
        assert client.put(f"{LISTINGS}/999999", json={"price": 5}, headers=auth_headers(owner)).status_code == 404
        listing = add_listing(db_session, owner)
        assert client.put(f"{LISTINGS}/{listing.id}", json={"price": 5}).status_code in (401, 403)

    @pytest.mark.parametrize(
        "body, expected",
        [({"price": -1}, 422), ({"price": 0}, 422), ({"price": 1}, 200), ({"price": 10_000_000}, 200),
         ({"price": 10_000_001}, 422), ({"price": "abc"}, 422), ({"price": 1.5}, 422)],
    )
    def test_price_boundaries(self, client, db_session, body, expected):
        """TC-API-LST-074 | AC-07.3 | T08 | boundary | price must be a whole number from 1 to 10,000,000"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        assert client.put(f"{LISTINGS}/{listing.id}", json=body, headers=auth_headers(owner)).status_code == expected

    @pytest.mark.parametrize("status", [ListingStatus.SOLD, ListingStatus.RENTED, ListingStatus.UNAVAILABLE])
    def test_only_available_items_can_be_edited(self, client, db_session, status):
        """TC-API-LST-075 | AC-07.1 | T08 | negative | a sold, lent-out or unlisted item's price is frozen (400)"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, status=status)
        response = client.put(f"{LISTINGS}/{listing.id}", json={"price": 5}, headers=auth_headers(owner))
        assert response.status_code == 400

    @pytest.mark.parametrize("listing_type", [ListingType.LEND, ListingType.GIVEAWAY])
    def test_free_items_have_no_price_to_change(self, client, db_session, listing_type):
        """TC-API-LST-076 | AC-07.1 | T08 | negative | a lend or giveaway item cannot be given a price (400)"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, listing_type=listing_type, price=0)
        response = client.put(f"{LISTINGS}/{listing.id}", json={"price": 5}, headers=auth_headers(owner))
        assert response.status_code == 400
        db_session.refresh(listing)
        assert listing.price == 0

    def test_price_change_notifies_only_people_in_a_chat(self, client, db_session):
        """TC-API-LST-077 | AC-07.1 | T08 | business | chatting buyers get an in-app notice; pending, declined and unchanged-price cases do not"""
        from app.models import Notification

        owner = make_user(db_session)
        listing = add_listing(db_session, owner, price=100)
        chatting, pending, declined = (make_user(db_session) for _ in range(3))
        add_interest(db_session, listing, chatting, InterestStatus.ACCEPTED)
        add_interest(db_session, listing, pending, InterestStatus.PENDING)
        add_interest(db_session, listing, declined, InterestStatus.REJECTED)

        headers = auth_headers(owner)
        assert client.put(f"{LISTINGS}/{listing.id}", json={"price": 100}, headers=headers).status_code == 200
        assert db_session.scalar(select(func.count()).select_from(Notification)) == 0

        assert client.put(f"{LISTINGS}/{listing.id}", json={"price": 80}, headers=headers).status_code == 200
        rows = db_session.scalars(select(Notification)).all()
        assert [(n.user_id, n.kind) for n in rows] == [(chatting.id, "price_changed")]
        assert "100" in rows[0].message and "80" in rows[0].message


class TestDeleteListing:
    def test_owner_delete_removes_listing_images_and_interests(self, client, db_session, monkeypatch):
        """TC-API-LST-080 | AC-07.4, AC-19.3 | T08, T09 | positive | delete removes the row, its image rows, interests and the Cloudinary assets"""
        fake = install_fake_cloudinary(monkeypatch)
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing, public_id="pid-a")
        add_image(db_session, listing, public_id="pid-b")
        add_interest(db_session, listing, buyer, InterestStatus.PENDING)

        response = client.delete(f"{LISTINGS}/{listing.id}", headers=auth_headers(owner))

        assert response.status_code == 200
        assert response.json() == {"message": "Listing deleted successfully"}
        db_session.expire_all()
        assert _count(db_session, Listing) == 0
        assert _count(db_session, ListingImage) == 0
        assert _count(db_session, Interest) == 0
        assert sorted(fake.deleted) == ["pid-a", "pid-b"]

    def test_deleted_listing_is_gone_from_detail(self, client, db_session, monkeypatch):
        """TC-API-LST-081 | AC-07.4 | T08 | business | after delete, GET by id is 404"""
        install_fake_cloudinary(monkeypatch)
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        client.delete(f"{LISTINGS}/{listing.id}", headers=auth_headers(owner))
        assert client.get(f"{LISTINGS}/{listing.id}").status_code == 404

    def test_unknown_listing_and_anonymous_are_rejected(self, client, db_session):
        """TC-API-LST-082 | AC-07.2 | T08 | negative | DELETE on a missing id is 404; without a token is 401/403"""
        owner = make_user(db_session)
        assert client.delete(f"{LISTINGS}/999999", headers=auth_headers(owner)).status_code == 404
        listing = add_listing(db_session, owner)
        assert client.delete(f"{LISTINGS}/{listing.id}").status_code in (401, 403)
        assert _count(db_session, Listing) == 1

    def test_non_owner_cannot_delete_and_listing_survives(self, client, db_session, monkeypatch):
        """TC-API-LST-083 | AC-07.2 | T08 | negative | a stranger gets 403 and no images are removed"""
        fake = install_fake_cloudinary(monkeypatch)
        owner, stranger = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing, public_id="keep")
        response = client.delete(f"{LISTINGS}/{listing.id}", headers=auth_headers(stranger))
        assert response.status_code == 403
        assert _count(db_session, Listing) == 1
        assert fake.deleted == []
