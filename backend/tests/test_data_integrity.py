"""Data-integrity tests: constraints, defaults, cascades and consistency (tasks T02, T05, T08, T10, T12).

Runs on SQLite. SQLite does not enforce foreign keys by default, so database-level
ON DELETE CASCADE / SET NULL behaviour and PostgreSQL enum types are verified manually
(see TC-MAN-DB-001..003 in test.md). Everything below relies on unique indexes (which SQLite
does enforce) and on SQLAlchemy ORM cascades.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, Interest, Listing, ListingImage, Need, User
from app.utils.enums import (
    InterestStatus,
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
    NeedStatus,
    NeedType,
    UserRole,
)
from tests.conftest import auth_headers, make_user, register_payload
from tests.support import (
    add_image,
    add_interest,
    add_listing,
    add_need,
    install_fake_cloudinary,
    listing_form,
)


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _new_user(**overrides) -> User:
    fields = dict(
        name="Dup Test", email="dup@gmail.com", phone="9000000001", password_hash="x",
        role=UserRole.SE, joining_date=date(2026, 1, 1),
    )
    fields.update(overrides)
    return User(**fields)


class TestUniquenessConstraints:
    def test_duplicate_email_is_rejected_by_the_database(self, db_session):
        """TC-DI-UNQ-001 | AC-19.1 | T02 | negative | two users cannot share an email at the storage level"""
        db_session.add(_new_user())
        db_session.commit()
        db_session.add(_new_user(phone="9000000002"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
        assert _count(db_session, User) == 1

    def test_duplicate_phone_is_rejected_by_the_database(self, db_session):
        """TC-DI-UNQ-002 | AC-19.1 | T02 | negative | two users cannot share a phone number at the storage level"""
        db_session.add(_new_user())
        db_session.commit()
        db_session.add(_new_user(email="other@gmail.com"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
        assert _count(db_session, User) == 1

    def test_one_interest_per_user_per_listing_at_storage_level(self, db_session):
        """TC-DI-UNQ-003 | AC-19.1 | T02, T10 | negative | the (listing, user) unique constraint blocks a second interest row"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        add_interest(db_session, listing, buyer)
        db_session.add(Interest(listing_id=listing.id, interested_user_id=buyer.id))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
        assert _count(db_session, Interest) == 1

    def test_same_user_may_have_interests_in_different_listings(self, db_session):
        """TC-DI-UNQ-004 | AC-19.1 | T02 | boundary | the constraint is composite: other listings are unaffected"""
        owner, buyer = make_user(db_session), make_user(db_session)
        add_interest(db_session, add_listing(db_session, owner), buyer)
        add_interest(db_session, add_listing(db_session, owner), buyer)
        assert _count(db_session, Interest) == 2

    def test_api_registration_duplicates_leave_single_row(self, client, db_session):
        """TC-DI-UNQ-005 | AC-01.3, AC-19.1 | T05 | business | repeated API registration with the same email yields exactly one stored user"""
        payload = register_payload("only-one@gmail.com")
        client.post("/api/auth/register", json=payload)
        client.post("/api/auth/register", json={**payload, "phone": "9111111111"})
        assert db_session.scalar(select(func.count()).select_from(User).where(User.email == "only-one@gmail.com")) == 1


class TestDefaultsAndConsistency:
    def test_new_user_defaults(self, db_session):
        """TC-DI-DEF-001 | AC-01.6, AC-19.2 | T02 | positive | a user created without flags is non-admin, active, with a creation time"""
        user = _new_user()
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        assert user.is_admin is False
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)

    def test_new_interest_defaults_to_pending(self, db_session):
        """TC-DI-DEF-002 | AC-09.1, AC-19.2 | T02 | positive | an Interest saved without a status is PENDING"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        interest = Interest(listing_id=listing.id, interested_user_id=buyer.id)
        db_session.add(interest)
        db_session.commit()
        db_session.refresh(interest)
        assert interest.status == InterestStatus.PENDING

    def test_new_listing_and_need_default_to_active_with_zero_price_or_budget(self, db_session):
        """TC-DI-DEF-003 | AC-19.2 | T02 | positive | ORM defaults: status ACTIVE and price/budget 0 when unspecified"""
        user = make_user(db_session)
        now = datetime.utcnow()
        listing = Listing(owner_id=user.id, title="t", category=ListingCategory.OTHER, listing_type=ListingType.GIVEAWAY,
                          condition=ItemCondition.GOOD,
                          location="ECC", description="d", expires_at=now + timedelta(days=1))
        need = Need(user_id=user.id, title="t", category=ListingCategory.OTHER, need_type=NeedType.BUY, location="ECC",
                    description="d", expires_at=now + timedelta(days=1))
        db_session.add_all([listing, need])
        db_session.commit()
        db_session.refresh(listing)
        db_session.refresh(need)
        assert (listing.status, listing.price) == (ListingStatus.ACTIVE, 0)
        assert (need.status, need.budget) == (NeedStatus.ACTIVE, 0)

    def test_api_created_listing_expires_after_it_was_created(self, client, db_session, monkeypatch):
        """TC-DI-DEF-004 | AC-04.1, AC-19.2 | T08 | business | persisted expires_at is strictly later than created_at for API-created listings"""
        install_fake_cloudinary(monkeypatch)
        user = make_user(db_session)
        client.post("/api/listings", data=listing_form(), headers=auth_headers(user))
        listing = db_session.scalar(select(Listing))
        assert listing.expires_at > listing.created_at

    def test_summary_counters_equal_actual_row_counts(self, client, db_session):
        """TC-DI-CON-001 | AC-11.1 | T07 | business | the summary endpoint agrees with rows counted directly in the database"""
        me, other = make_user(db_session), make_user(db_session)
        mine = add_listing(db_session, me)
        add_need(db_session, me)
        add_interest(db_session, add_listing(db_session, other), me)
        add_interest(db_session, mine, other)
        body = client.get("/api/users/me/summary", headers=auth_headers(me)).json()
        assert body["my_listings_count"] == db_session.scalar(select(func.count()).select_from(Listing).where(Listing.owner_id == me.id))
        assert body["my_needs_count"] == db_session.scalar(select(func.count()).select_from(Need).where(Need.user_id == me.id))
        assert body["my_interests_count"] == db_session.scalar(select(func.count()).select_from(Interest).where(Interest.interested_user_id == me.id))


class TestCascadeDeletes:
    def test_deleting_a_listing_removes_images_and_interests(self, db_session):
        """TC-DI-CAS-001 | AC-19.3 | T02 | positive | ORM delete of a listing cascades to its images and interests"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing)
        add_interest(db_session, listing, buyer)
        db_session.delete(listing)
        db_session.commit()
        assert (_count(db_session, Listing), _count(db_session, ListingImage), _count(db_session, Interest)) == (0, 0, 0)

    def test_deleting_a_user_removes_their_listings_needs_and_interests(self, db_session):
        """TC-DI-CAS-002 | AC-19.3 | T02 | positive | deleting a user removes everything they own, including interests others made on their listings"""
        user, other = make_user(db_session), make_user(db_session)
        own_listing = add_listing(db_session, user)
        add_image(db_session, own_listing)
        add_need(db_session, user)
        add_interest(db_session, own_listing, other)                       # received
        add_interest(db_session, add_listing(db_session, other), user)     # sent
        survivors_listing = _count(db_session, Listing)

        db_session.delete(user)
        db_session.commit()

        assert _count(db_session, User) == 1
        assert _count(db_session, Need) == 0
        assert _count(db_session, ListingImage) == 0
        assert _count(db_session, Interest) == 0
        assert _count(db_session, Listing) == survivors_listing - 1

    def test_deleting_a_user_does_not_touch_other_users_data(self, db_session):
        """TC-DI-CAS-003 | AC-19.3 | T02 | business | another user's listings and needs survive"""
        user, other = make_user(db_session), make_user(db_session)
        add_listing(db_session, other)
        add_need(db_session, other)
        db_session.delete(user)
        db_session.commit()
        assert (_count(db_session, Listing), _count(db_session, Need)) == (1, 1)

    def test_deleting_a_need_does_not_affect_listings(self, db_session):
        """TC-DI-CAS-004 | AC-19.3 | T02 | boundary | needs and listings are independent aggregates"""
        user = make_user(db_session)
        add_listing(db_session, user)
        need = add_need(db_session, user)
        db_session.delete(need)
        db_session.commit()
        assert _count(db_session, Listing) == 1

    def test_admin_actions_leave_audit_rows_after_target_is_deleted(self, client, db_session):
        """TC-DI-CAS-005 | AC-13.1, AC-19.3 | T12 | business | removing a listing through the admin API keeps the audit entry that records it"""
        admin = make_user(db_session, is_admin=True)
        listing = add_listing(db_session, make_user(db_session), title="Audited")
        client.delete(f"/api/admin/listings/{listing.id}", headers=auth_headers(admin))
        db_session.expire_all()
        assert _count(db_session, Listing) == 0
        entry = db_session.scalar(select(AuditLog))
        assert entry is not None and entry.action == "DELETE_LISTING"


class TestPersistedValues:
    def test_listing_images_keep_public_id_and_url(self, db_session):
        """TC-DI-VAL-001 | AC-04.5, AC-07.4 | T02 | positive | the Cloudinary public id (needed for deletion) and url are both stored"""
        image = add_image(db_session, add_listing(db_session, make_user(db_session)), public_id="folder/abc", url="https://res.cloudinary.com/x/abc.png")
        db_session.refresh(image)
        assert (image.cloudinary_public_id, image.image_url) == ("folder/abc", "https://res.cloudinary.com/x/abc.png")

    def test_enum_columns_round_trip(self, db_session):
        """TC-DI-VAL-002 | AC-19.2 | T02 | positive | status/type enums are stored and read back as enum members"""
        listing = add_listing(db_session, make_user(db_session), status=ListingStatus.RENTED)
        db_session.expire_all()
        assert db_session.get(Listing, listing.id).status is ListingStatus.RENTED

    def test_passwords_are_never_stored_in_plaintext(self, client, db_session):
        """TC-DI-VAL-003 | AC-01.4, AC-19.6 | T05 | business | no column of the stored user row contains the submitted password"""
        payload = register_payload("stored@gmail.com", password="Sup3rSecret!")
        client.post("/api/auth/register", json=payload)
        user = db_session.scalar(select(User).where(User.email == "stored@gmail.com"))
        stored_values = [str(getattr(user, column.name)) for column in User.__table__.columns]
        assert not any("Sup3rSecret!" in value for value in stored_values)
