import asyncio
import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.config import settings
from app.database import get_db
from app.dependencies import get_complete_user, get_current_user
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.listing_image import ListingImage
from app.models.pickup_area import PickupArea
from app.models.user import User
from app.schemas.listing import (
    ListingDetailResponse,
    ListingResponse,
    ListingUpdate,
)
from app.schemas.removal import OwnerRemoval
from app.services import idempotency
from app.services.cloudinary import (
    delete_image,
    upload_image,
)
from app.services.notify import notify, short
from app.services.removals import record_listing_removal
from app.utils.money import format_rupees
from app.services.rate_limit import (
    action_limiter,
    client_key,
    create_limiter,
    read_limiter,
    user_key,
)
from app.utils.enums import (
    InterestStatus,
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
    RemovalReason,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/listings",
    tags=["Listings"],
)


def _serialize_listing(listing: Listing) -> dict:
    owner = listing.owner

    image_url = None

    if listing.images:
        first_image = min(
            listing.images,
            key=lambda image: image.id,
        )
        image_url = first_image.image_url

    return {
        "id": listing.id,
        "owner_id": listing.owner_id,
        "title": listing.title,
        "category": listing.category,
        "listing_type": listing.listing_type,
        "price": listing.price,
        "price_unit": listing.price_unit,
        "condition": listing.condition,
        "location": listing.location,
        "pickup_area_id": listing.pickup_area_id,
        "pickup_area": (
            listing.pickup_area.name
            if listing.pickup_area is not None
            else None
        ),
        "block_no": listing.block_no,
        "description": listing.description,
        "status": listing.status,
        "created_at": listing.created_at,
        "expires_at": listing.expires_at,
        "owner_name": (
            owner.name
            if owner is not None
            else None
        ),
        "owner_role": (
            str(owner.role.value)
            if owner is not None
            else None
        ),
        "image_url": image_url,
    }


def _serialize_listing_detail(
    listing: Listing,
) -> dict:
    return {
        **_serialize_listing(listing),
        "images": listing.images,
    }


@router.post(
    "",
    response_model=ListingDetailResponse,
    status_code=201,
)
async def create_listing(
    request: Request,
    title: str = Form(..., min_length=2, max_length=150),
    category: ListingCategory = Form(...),
    listing_type: ListingType = Form(...),
    # Upper bound mirrors the SPA and keeps the value inside PostgreSQL's 32-bit integer.
    price: int = Form(0, ge=0, le=10_000_000),
    price_unit: str | None = Form(None, max_length=30),
    condition: ItemCondition = Form(...),
    pickup_area_id: int = Form(...),
    block_no: int | None = Form(None, ge=1, le=100),
    description: str = Form(..., min_length=2, max_length=2000),
    images: Annotated[
        list[UploadFile],
        File(
            description="Upload upto 5 images"
        )
    ] = [],
    current_user: User = Depends(get_complete_user),
    db: Session = Depends(get_db),
):

    idem = idempotency.begin(db, request, current_user, "listing.create")

    if idem.replay_id is not None:
        if db.get(Listing, idem.replay_id) is None:
            raise idempotency.already_done()

        return get_listing_detail(idem.replay_id, db)

    create_limiter.enforce(
        client_key(request, "create-listing"),
        "Too many listings created. Please try again later.",
    )

    # The length limits above count spaces, so "   " would pass and be saved as nothing.
    title, description = (
        title.strip(),
        description.strip(),
    )

    for field, value in (
        ("title", title),
        ("description", description),
    ):
        if len(value) < 2:
            raise HTTPException(
                status_code=422,
                detail=f"{field}: needs at least 2 characters, not counting spaces",
            )

    area = db.get(PickupArea, pickup_area_id)

    if area is None or not area.is_active:
        raise HTTPException(
            status_code=422,
            detail="Choose a pickup area from the list",
        )

    if block_no is not None and not area.has_blocks:
        raise HTTPException(
            status_code=422,
            detail=f"{area.name} has no block numbers",
        )

    location = f"{area.name} - {block_no}" if block_no else area.name

    if len(images) > settings.max_images_per_listing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Maximum "
                f"{settings.max_images_per_listing} images allowed"
            ),
        )

    if listing_type in {
        ListingType.LEND,
        ListingType.GIVEAWAY,
    }:
        price = 0
        price_unit = None

    if listing_type == ListingType.RENT and price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Rent listings must have a price",
        )

    if listing_type == ListingType.RENT and not price_unit:
        price_unit = "day"

    if listing_type == ListingType.SELL and price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Sell listings must have a price",
        )

    duplicate = db.scalar(
        select(Listing)
        .where(
            Listing.owner_id == current_user.id,
            Listing.title == title.strip(),
            Listing.listing_type == listing_type,
            Listing.price == price,
            Listing.pickup_area_id == area.id,
            Listing.block_no == block_no,
            Listing.description == description.strip(),
            Listing.created_at
            > datetime.utcnow()
            - timedelta(
                seconds=settings.duplicate_submission_window_seconds
            ),
        )
        .order_by(Listing.created_at.desc())
        .limit(1)
    )

    if duplicate is not None:
        return get_listing_detail(duplicate.id, db)

    now = datetime.utcnow()

    listing = Listing(
        owner_id=current_user.id,
        title=title.strip(),
        category=category,
        listing_type=listing_type,
        price=price,
        price_unit=price_unit,
        condition=condition,
        location=location,
        pickup_area_id=area.id,
        block_no=block_no,
        description=description.strip(),
        status=ListingStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(
            days=settings.listing_expiry_days
        ),
    )

    db.add(listing)
    db.commit()
    db.refresh(listing)

    uploaded_images = []

    try:
        for image in images:
            result = await upload_image(
                image,
                listing.id,
            )

            listing_image = ListingImage(
                listing_id=listing.id,
                cloudinary_public_id=result["public_id"],
                image_url=result["url"],
            )

            db.add(listing_image)
            uploaded_images.append(result["public_id"])

        # The key is claimed by the first commit and only gets its result here, so a retry that arrives
        # while the photos are still uploading is told to wait instead of being shown a listing without them.
        idem.finish(listing.id)
        db.commit()

    except Exception as exc:
        logger.error(
            "Image upload failed for listing %s: %s",
            listing.id,
            exc,
        )

        for public_id in uploaded_images:
            try:
                # Off the event loop: a Cloudinary call can take seconds.
                await asyncio.to_thread(delete_image, public_id)
            except Exception:
                # Keep going so the half-created listing is still removed below.
                logger.exception("Could not delete uploaded image %s", public_id)

        # The listing is undone, so the key must be too, or a retry would be answered with a listing that is gone.
        idem.release()
        db.delete(listing)
        db.commit()

        raise HTTPException(
            status_code=400,
            # ValueError messages come from our own checks (type, size, dimensions) and are user-safe.
            detail=(
                str(exc)
                if isinstance(exc, ValueError)
                else "Failed to upload images. Please try again."
            ),
        )

    db.refresh(listing)

    return get_listing_detail(
        listing.id,
        db,
    )


@router.get(
    "",
    response_model=list[ListingResponse],
)
def get_listings(
    request: Request,
    search: str | None = Query(None),
    category: ListingCategory | None = Query(None),
    listing_type: ListingType | None = Query(None),
    location: str | None = Query(None),
    pickup_area_id: int | None = Query(None),
    block_no: int | None = Query(None, ge=1, le=100),
    condition: ItemCondition | None = Query(None),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):

    read_limiter.enforce(
        client_key(request, "read-listings"),
        "Too many requests. Please slow down.",
    )

    query = select(Listing).options(
        joinedload(Listing.owner),
        selectinload(Listing.images),
    ).where(
        Listing.status == ListingStatus.ACTIVE,
        Listing.expires_at > datetime.utcnow(),
    )

    if search:
        query = query.where(
            Listing.title.ilike(f"%{search}%")
        )

    if category:
        query = query.where(
            Listing.category == category
        )

    if listing_type:
        query = query.where(
            Listing.listing_type == listing_type
        )

    if location:
        query = query.where(
            Listing.location.ilike(f"%{location}%")
        )

    if pickup_area_id is not None:
        query = query.where(
            Listing.pickup_area_id == pickup_area_id
        )

    if block_no is not None:
        query = query.where(
            Listing.block_no == block_no
        )

    if condition:
        query = query.where(
            Listing.condition == condition
        )

    if min_price is not None:
        query = query.where(Listing.price >= min_price)

    if max_price is not None:
        query = query.where(Listing.price <= max_price)

    query = (
        query
        .order_by(Listing.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    listings = db.scalars(query).all()

    return [
        _serialize_listing(listing)
        for listing in listings
    ]


@router.get(
    "/me",
    response_model=list[ListingResponse],
)
def get_my_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        select(Listing)
        .options(
            joinedload(Listing.owner),
            selectinload(Listing.images),
        )
        .where(Listing.owner_id == current_user.id)
        .order_by(Listing.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    listings = db.scalars(query).all()

    return [
        _serialize_listing(listing)
        for listing in listings
    ]


@router.get(
    "/{listing_id}",
    response_model=ListingDetailResponse,
)
def get_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
):

    listing = db.scalar(
        select(Listing)
        .options(
            joinedload(Listing.images),
            joinedload(Listing.owner),
        )
        .where(Listing.id == listing_id)
    )

    if not listing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    if (
        listing.status == ListingStatus.ACTIVE
        and listing.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(
            status_code=404,
            detail="Listing has expired",
        )

    return _serialize_listing_detail(listing)


@router.put(
    "/{listing_id}",
    response_model=ListingResponse,
)
def update_listing(
    listing_id: int,
    data: ListingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action_limiter.enforce(
        user_key(current_user.id, "edit-listing"),
        "Too many requests. Please try again later.",
    )

    listing = db.get(Listing, listing_id)

    if not listing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    if listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own listing",
        )

    if listing.status != ListingStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="Only available items can be edited",
        )

    if listing.listing_type not in {
        ListingType.SELL,
        ListingType.RENT,
    }:
        raise HTTPException(
            status_code=400,
            detail="Free items have no price to change",
        )

    old_price = listing.price

    if data.price != old_price:
        listing.price = data.price

        unit = f" / {listing.price_unit}" if listing.price_unit else ""

        # Only people already chatting need to hear about it; pending
        # enquirers see the current price on the item page.
        chatting = db.scalars(
            select(Interest).where(
                Interest.listing_id == listing.id,
                Interest.status == InterestStatus.ACCEPTED,
            )
        ).all()

        for interest in chatting:
            notify(
                db,
                interest.interested_user_id,
                "price_changed",
                f"The price of \"{short(listing.title)}\" changed from "
                f"{format_rupees(old_price)}{unit} to {format_rupees(data.price)}{unit}.",
                interest.id,
                actor_id=current_user.id,
                listing_title=listing.title,
                detail=f"{format_rupees(old_price)}{unit} to {format_rupees(data.price)}{unit}",
            )

        db.commit()
        db.refresh(listing)

    return _serialize_listing(listing)


@router.post(
    "/{listing_id}/mark-returned",
    response_model=ListingResponse,
)
def mark_returned(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """A rented or lent item is back: make it Available again."""

    action_limiter.enforce(
        user_key(current_user.id, "mark-returned"),
        "Too many requests. Please try again later.",
    )

    listing = db.get(Listing, listing_id)

    if not listing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    if listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only update your own listing",
        )

    if listing.status != ListingStatus.RENTED:
        raise HTTPException(
            status_code=400,
            detail="This item is not out on loan",
        )

    now = datetime.utcnow()

    borrower_deal = db.scalar(
        select(Interest)
        .where(
            Interest.listing_id == listing.id,
            Interest.deal_closed_at.is_not(None),
            Interest.returned_at.is_(None),
        )
        .order_by(Interest.deal_closed_at.desc())
        .limit(1)
    )

    if borrower_deal is not None:
        borrower_deal.returned_at = now
        notify(
            db,
            borrower_deal.interested_user_id,
            "item_returned",
            f"\"{short(listing.title)}\" was marked as returned. Thank you!",
            borrower_deal.id,
            actor_id=current_user.id,
            listing_title=listing.title,
        )

    listing.status = ListingStatus.ACTIVE

    # A long loan can outlive the listing's 30 days; without this the
    # "Available" item would vanish from search and be swept by cleanup.
    if listing.expires_at <= now:
        listing.expires_at = now + timedelta(
            days=settings.listing_expiry_days
        )

    db.commit()
    db.refresh(listing)

    return _serialize_listing(listing)


@router.delete(
    "/{listing_id}",
)
def delete_listing(
    listing_id: int,
    data: OwnerRemoval | None = Body(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    listing = db.get(Listing, listing_id)

    if not listing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    if listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own listing",
        )

    # Closing the enquiries is deleting them with the listing; tell the
    # people who were still waiting or chatting (or borrowing it) first.
    affected = db.scalars(
        select(Interest).where(
            Interest.listing_id == listing.id,
            or_(
                Interest.status.in_(
                    [InterestStatus.PENDING, InterestStatus.ACCEPTED]
                ),
                and_(
                    Interest.deal_closed_at.is_not(None),
                    Interest.returned_at.is_(None),
                ),
            ),
        )
    ).all()

    for interest in affected:
        # No interest_id: the enquiry is deleted along with the listing.
        notify(
            db,
            interest.interested_user_id,
            "listing_removed",
            f"\"{short(listing.title)}\" was removed by the seller.",
            actor_id=current_user.id,
            listing_title=listing.title,
        )

    for image in listing.images:
        try:
            delete_image(
                image.cloudinary_public_id
            )
        except Exception:
            # A Cloudinary outage must not keep the listing alive; the orphaned image is logged for clean-up.
            logger.exception("Could not delete image %s", image.cloudinary_public_id)

    record_listing_removal(
        db,
        listing,
        RemovalReason(data.reason) if data else RemovalReason.OWNER_DELETED,
        removed_by_id=current_user.id,
    )

    db.delete(listing)
    db.commit()

    return {
        "message": "Listing deleted successfully"
    }