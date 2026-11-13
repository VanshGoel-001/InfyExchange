from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.need import Need
from app.models.user import User
from app.schemas.user import (
    CompleteProfileRequest,
    ProfileUpdate,
    UserActivitySummary,
    UserResponse,
)
from app.utils.enums import InterestStatus


router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post(
    "/me/complete-profile",
    response_model=UserResponse,
)
def complete_profile(
    data: CompleteProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-time step for accounts created through Google sign-in."""

    if current_user.profile_complete:
        raise HTTPException(
            status_code=409,
            detail="Your profile is already complete",
        )

    phone_owner = db.scalar(select(User).where(User.phone == data.phone))
    if phone_owner is not None and phone_owner.id != current_user.id:
        raise HTTPException(
            status_code=409,
            detail="Phone number already registered",
        )

    current_user.phone = data.phone
    current_user.role = data.role
    current_user.joining_date = data.joining_date

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number already registered",
        )

    db.refresh(current_user)
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
)
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.profile_complete:
        raise HTTPException(
            status_code=409,
            detail="Please complete your profile first",
        )

    if data.role is not None:
        current_user.role = data.role
    if data.joining_date is not None:
        current_user.joining_date = data.joining_date

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get(
    "/me/summary",
    response_model=UserActivitySummary,
)
def get_activity_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_listings_count = db.scalar(
        select(func.count(Listing.id))
        .where(Listing.owner_id == current_user.id)
    )

    my_needs_count = db.scalar(
        select(func.count(Need.id))
        .where(Need.user_id == current_user.id)
    )

    my_interests_count = db.scalar(
        select(func.count(Interest.id))
        .where(Interest.interested_user_id == current_user.id)
    )

    requests_received_count = db.scalar(
        select(func.count(Interest.id))
        .join(Listing)
        .where(Listing.owner_id == current_user.id)
    )

    pending_requests_received_count = db.scalar(
        select(func.count(Interest.id))
        .join(Listing)
        .where(
            Listing.owner_id == current_user.id,
            Interest.status == InterestStatus.PENDING
        )
    )

    return {
        "my_listings_count": my_listings_count or 0,
        "my_needs_count": my_needs_count or 0,
        "my_interests_count": my_interests_count or 0,
        "requests_received_count": requests_received_count or 0,
        "pending_requests_received_count": pending_requests_received_count or 0,
    }