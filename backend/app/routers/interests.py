from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
)

from app.database import get_db
from app.dependencies import get_current_user
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.user import User
from app.schemas.interest import (
    ContactResponse,
    InterestCreate,
    InterestResponse,
)
from app.services.rate_limit import (
    client_key,
    contact_limiter,
    create_limiter,
)
from app.utils.enums import InterestStatus, ListingStatus


router = APIRouter(
    prefix="/api/interests",
    tags=["Interests"],
)


def _serialize_interest(
    interest: Interest,
    interested_user: User,
) -> dict:

    listing = interest.listing

    image_url = None

    if listing is not None and listing.images:
        first_image = min(
            listing.images,
            key=lambda image: image.id,
        )
        image_url = first_image.image_url

    return {
        "id": interest.id,
        "listing_id": interest.listing_id,
        "interested_user_id": (
            interest.interested_user_id
        ),
        "message": interest.message,
        "status": interest.status,
        "created_at": interest.created_at,
        "listing_title": (
            listing.title
            if listing is not None
            else None
        ),
        "listing_image_url": image_url,
        "interested_user_name": interested_user.name,
        "interested_user_role": str(
            interested_user.role.value
        ),
    }


@router.post(
    "/listing/{listing_id}",
    response_model=InterestResponse,
    status_code=201,
)
def create_interest(
    listing_id: int,
    data: InterestCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    create_limiter.enforce(
        client_key(request, "create-interest"),
        "Too many interests submitted. Please try again later.",
    )

    listing = db.get(Listing, listing_id)

    if not listing:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    if listing.owner_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot show interest in your own listing",
        )

    if listing.status != ListingStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="This listing is no longer active",
        )

    if listing.expires_at <= datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="This listing has expired",
        )

    existing = db.scalar(
        select(Interest).where(
            Interest.listing_id == listing_id,
            Interest.interested_user_id == current_user.id,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already showed interest",
        )

    interest = Interest(
        listing_id=listing_id,
        interested_user_id=current_user.id,
        message=data.message,
        status=InterestStatus.PENDING,
    )

    db.add(interest)
    db.commit()
    db.refresh(interest)

    return interest


@router.get(
    "/received",
    response_model=list[InterestResponse],
)
def get_received_interests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    query = (
        select(Interest)
        .join(Listing)
        .options(
            joinedload(Interest.listing).selectinload(
                Listing.images
            ),
            joinedload(Interest.interested_user),
        )
        .where(
            Listing.owner_id == current_user.id
        )
        .order_by(Interest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    interests = db.scalars(query).all()

    return [
        _serialize_interest(
            interest,
            interest.interested_user,
        )
        for interest in interests
    ]


@router.get(
    "/sent",
    response_model=list[InterestResponse],
)
def get_sent_interests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    query = (
        select(Interest)
        .options(
            joinedload(Interest.listing).selectinload(
                Listing.images
            ),
        )
        .where(
            Interest.interested_user_id
            == current_user.id
        )
        .order_by(Interest.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    interests = db.scalars(query).all()

    return [
        _serialize_interest(
            interest,
            current_user,
        )
        for interest in interests
    ]


@router.patch(
    "/{interest_id}/accept",
    response_model=InterestResponse,
)
def accept_interest(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    interest = db.scalar(
        select(Interest)
        .options(
            joinedload(Interest.listing)
        )
        .where(Interest.id == interest_id)
    )

    if not interest:
        raise HTTPException(
            status_code=404,
            detail="Interest not found",
        )

    if interest.listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the listing owner can accept",
        )

    if interest.status != InterestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending interests can be accepted",
        )

    interest.status = InterestStatus.ACCEPTED

    db.commit()
    db.refresh(interest)

    return interest


@router.patch(
    "/{interest_id}/reject",
    response_model=InterestResponse,
)
def reject_interest(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    interest = db.scalar(
        select(Interest)
        .options(
            joinedload(Interest.listing)
        )
        .where(Interest.id == interest_id)
    )

    if not interest:
        raise HTTPException(
            status_code=404,
            detail="Interest not found",
        )

    if interest.listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the listing owner can reject",
        )

    if interest.status != InterestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending interests can be rejected",
        )

    interest.status = InterestStatus.REJECTED

    db.commit()
    db.refresh(interest)

    return interest


@router.get(
    "/{interest_id}/contact",
    response_model=ContactResponse,
)
def get_connection_contact(
    interest_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    contact_limiter.enforce(
        client_key(request, "contact"),
        "Too many requests. Please try again later.",
    )

    interest = db.scalar(
        select(Interest)
        .options(
            joinedload(Interest.listing),
            joinedload(Interest.interested_user),
        )
        .where(Interest.id == interest_id)
    )

    if not interest:
        raise HTTPException(
            status_code=404,
            detail="Interest not found",
        )

    if interest.status != InterestStatus.ACCEPTED:
        raise HTTPException(
            status_code=403,
            detail="Contact details are available only after acceptance",
        )

    owner_id = interest.listing.owner_id
    interested_user_id = interest.interested_user_id

    if current_user.id == owner_id:
        contact_user = interest.interested_user

    elif current_user.id == interested_user_id:
        contact_user = interest.listing.owner

    else:
        raise HTTPException(
            status_code=403,
            detail="You are not part of this connection",
        )

    return {
        "name": contact_user.name,
        "email": contact_user.email,
        "phone": contact_user.phone,
    }