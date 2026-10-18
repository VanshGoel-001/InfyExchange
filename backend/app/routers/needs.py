from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.need import Need
from app.models.user import User
from app.schemas.need import NeedCreate, NeedResponse
from app.utils.enums import (
    ListingCategory,
    NeedStatus,
    NeedType,
)


router = APIRouter(
    prefix="/api/needs",
    tags=["Needs"],
)


def _serialize_need(need: Need) -> dict:
    return {
        "id": need.id,
        "user_id": need.user_id,
        "title": need.title,
        "category": need.category,
        "need_type": need.need_type,
        "duration": need.duration,
        "budget": need.budget,
        "location": need.location,
        "description": need.description,
        "status": need.status,
        "created_at": need.created_at,
        "expires_at": need.expires_at,
        "user_name": (
            need.user.name
            if need.user is not None
            else None
        ),
    }


@router.post(
    "",
    response_model=NeedResponse,
    status_code=201,
)
def create_need(
    data: NeedCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    now = datetime.utcnow()

    duplicate = db.scalar(
        select(Need)
        .where(
            Need.user_id == current_user.id,
            Need.title == data.title.strip(),
            Need.need_type == data.need_type,
            Need.budget == data.budget,
            Need.location == data.location.strip(),
            Need.description == data.description.strip(),
            Need.created_at
            > now
            - timedelta(
                seconds=settings.duplicate_submission_window_seconds
            ),
        )
        .order_by(Need.created_at.desc())
        .limit(1)
    )

    if duplicate is not None:
        return duplicate

    need = Need(
        user_id=current_user.id,
        title=data.title.strip(),
        category=data.category,
        need_type=data.need_type,
        duration=data.duration,
        budget=data.budget,
        location=data.location.strip(),
        description=data.description.strip(),
        status=NeedStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(
            days=settings.listing_expiry_days
        ),
    )

    db.add(need)
    db.commit()
    db.refresh(need)

    return need


@router.get(
    "",
    response_model=list[NeedResponse],
)
def get_needs(
    search: str | None = Query(None),
    category: ListingCategory | None = Query(None),
    need_type: NeedType | None = Query(None),
    location: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):

    query = select(Need).options(
        joinedload(Need.user)
    ).where(
        Need.status == NeedStatus.ACTIVE,
        Need.expires_at > datetime.utcnow(),
    )

    if search:
        query = query.where(
            Need.title.ilike(f"%{search}%")
        )

    if category:
        query = query.where(
            Need.category == category
        )

    if need_type:
        query = query.where(
            Need.need_type == need_type
        )

    if location:
        query = query.where(
            Need.location.ilike(f"%{location}%")
        )

    query = (
        query
        .order_by(Need.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    needs = db.scalars(query).all()

    return [
        _serialize_need(need)
        for need in needs
    ]


@router.get(
    "/me",
    response_model=list[NeedResponse],
)
def get_my_needs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        select(Need)
        .options(joinedload(Need.user))
        .where(Need.user_id == current_user.id)
        .order_by(Need.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    needs = db.scalars(query).all()

    return [
        _serialize_need(need)
        for need in needs
    ]


@router.get(
    "/{need_id}",
    response_model=NeedResponse,
)
def get_need(
    need_id: int,
    db: Session = Depends(get_db),
):

    need = db.scalar(
        select(Need)
        .options(joinedload(Need.user))
        .where(Need.id == need_id)
    )

    if not need:
        raise HTTPException(
            status_code=404,
            detail="Need not found",
        )

    if (
        need.status == NeedStatus.ACTIVE
        and need.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(
            status_code=404,
            detail="Need has expired",
        )

    return _serialize_need(need)


@router.delete(
    "/{need_id}",
)
def delete_need(
    need_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    need = db.get(Need, need_id)

    if not need:
        raise HTTPException(
            status_code=404,
            detail="Need not found",
        )

    if need.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own need",
        )

    db.delete(need)
    db.commit()

    return {
        "message": "Need deleted successfully"
    }