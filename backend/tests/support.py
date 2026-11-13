"""Shared builders for the spec-derived test suite.

Plain helpers only: no fixtures and no import-time side effects. Fixtures that
already exist live in ``tests/conftest.py`` (``client``, ``db_session``,
``make_user``, ``auth_headers``, ``make_listing``, ``make_interest``,
``register_payload``) and are reused as-is.

Docstring convention used by every new test (parsed to build test.md tables)::

    TC-<LAYER>-<AREA>-<NNN> | AC-xx.y[, AC-..] | Tnn[, Tnn] | <kind> | <description>

where <kind> is one of: positive, negative, boundary, business.
"""

import itertools
from datetime import datetime, timedelta

from app.models import Interest, Listing, ListingImage, Need
from app.utils.enums import (
    InterestStatus,
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
    NeedStatus,
    NeedType,
)

# Smallest byte strings that pass the magic-byte checks in services/cloudinary.py
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16

_counter = itertools.count(1)


def image_part(name: str = "photo.png", content: bytes = PNG_BYTES, content_type: str = "image/png"):
    """One ``images`` multipart part for ``client.post(..., files=[...])``."""
    return ("images", (name, content, content_type))


def listing_form(**overrides) -> dict:
    """Valid multipart form fields for POST /api/listings.

    Pass ``field=None`` to omit a field entirely.
    """
    form = {
        "title": "Yonex racket",
        "category": "BADMINTON",
        "listing_type": "SELL",
        "price": "500",
        "condition": "GOOD",
        "location": "ECC",
        "description": "Lightly used racket",
    }
    for key, value in overrides.items():
        if value is None:
            form.pop(key, None)
        else:
            form[key] = str(value)
    return form


def need_payload(**overrides) -> dict:
    """Valid JSON body for POST /api/needs."""
    body = {
        "title": "Need a squash racket",
        "category": "SQUASH",
        "need_type": "BORROW",
        "duration": "1 week",
        "budget": 0,
        "location": "ECC",
        "description": "Looking to borrow a racket for a week",
    }
    body.update(overrides)
    return body


def add_listing(db, owner, **overrides) -> Listing:
    now = datetime.utcnow()
    fields = dict(
        owner_id=owner.id,
        title=f"Listing {next(_counter)}",
        category=ListingCategory.BADMINTON,
        listing_type=ListingType.SELL,
        price=100,
        price_unit=None,
        condition=ItemCondition.GOOD,
        location="ECC",
        description="Test description",
        status=ListingStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    fields.update(overrides)
    listing = Listing(**fields)
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def add_image(db, listing, public_id: str | None = None, url: str | None = None) -> ListingImage:
    n = next(_counter)
    image = ListingImage(
        listing_id=listing.id,
        cloudinary_public_id=public_id or f"test/img-{n}",
        image_url=url or f"https://res.cloudinary.com/test/img-{n}.png",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def add_need(db, user, **overrides) -> Need:
    now = datetime.utcnow()
    fields = dict(
        user_id=user.id,
        title=f"Need {next(_counter)}",
        category=ListingCategory.SQUASH,
        need_type=NeedType.BORROW,
        duration=None,
        budget=0,
        location="ECC",
        description="Test need description",
        status=NeedStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    fields.update(overrides)
    need = Need(**fields)
    db.add(need)
    db.commit()
    db.refresh(need)
    return need


def add_interest(db, listing, user, status: InterestStatus = InterestStatus.PENDING, message: str | None = "hi") -> Interest:
    interest = Interest(
        listing_id=listing.id,
        interested_user_id=user.id,
        message=message,
        status=status,
    )
    db.add(interest)
    db.commit()
    db.refresh(interest)
    return interest


class FakeCloudinary:
    """Records calls instead of talking to Cloudinary.

    ``fail_on`` holds 1-based upload call numbers that should raise ValueError.
    """

    def __init__(self, fail_on=()):
        self.fail_on = set(fail_on)
        self.upload_calls = 0
        self.deleted: list[str] = []

    async def upload(self, file, listing_id):
        self.upload_calls += 1
        n = self.upload_calls
        if n in self.fail_on:
            raise ValueError("simulated upload failure")
        return {
            "public_id": f"test/{listing_id}/{n}",
            "url": f"https://res.cloudinary.com/test/{listing_id}/{n}.png",
        }

    def delete(self, public_id):
        self.deleted.append(public_id)


def install_fake_cloudinary(monkeypatch, fail_on=()) -> FakeCloudinary:
    """Patch the Cloudinary functions as imported by the listings router."""
    fake = FakeCloudinary(fail_on)
    monkeypatch.setattr("app.routers.listings.upload_image", fake.upload)
    monkeypatch.setattr("app.routers.listings.delete_image", fake.delete)
    return fake
