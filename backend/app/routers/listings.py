import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.listing import Listing
from app.models.listing_image import ListingImage
from app.models.user import User
from app.schemas.listing import (
    ListingDetailResponse,
    ListingResponse,
    ListingUpdate,
)
from app.services.cloudinary import (
    delete_image,
    upload_image,
)
from app.utils.enums import (
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
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
    title: str = Form(..., min_length=2, max_length=150),
    category: ListingCategory = Form(...),
    listing_type: ListingType = Form(...),
    price: int = Form(0, ge=0),
    price_unit: str | None = Form(None, max_length=30),
    condition: ItemCondition = Form(...),
    location: str = Form(..., min_length=2, max_length=100),
    description: str = Form(..., min_length=2, max_length=2000),
    images: Annotated[
        list[UploadFile],
        File(
            description="Upload upto 5 images"
        )
    ] = [],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

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

    now = datetime.utcnow()

    listing = Listing(
        owner_id=current_user.id,
        title=title.strip(),
        category=category,
        listing_type=listing_type,
        price=price,
        price_unit=price_unit,
        condition=condition,
        location=location.strip(),
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

        db.commit()

    except Exception as exc:
        logger.error(
            "Image upload failed for listing %s: %s",
            listing.id,
            exc,
        )

        for public_id in uploaded_images:
            delete_image(public_id)

        db.delete(listing)
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Failed to upload images. Please try again.",
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
    search: str | None = Query(None),
    category: ListingCategory | None = Query(None),
    listing_type: ListingType | None = Query(None),
    location: str | None = Query(None),
    condition: ItemCondition | None = Query(None),
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):

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

    updates = data.model_dump(
        exclude_unset=True
    )

    for key, value in updates.items():
        setattr(listing, key, value)

    db.commit()
    db.refresh(listing)

    return _serialize_listing(listing)


@router.delete(
    "/{listing_id}",
)
def delete_listing(
    listing_id: int,
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

    for image in listing.images:
        delete_image(
            image.cloudinary_public_id
        )

    db.delete(listing)
    db.commit()

    return {
        "message": "Listing deleted successfully"
    }