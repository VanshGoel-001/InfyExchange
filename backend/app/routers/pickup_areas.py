from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.pickup_area import PickupArea
from app.schemas.pickup_area import PickupAreaResponse
from app.services.rate_limit import client_key, read_limiter

router = APIRouter(
    prefix="/api/pickup-areas",
    tags=["Pickup areas"],
)


@router.get("", response_model=list[PickupAreaResponse])
def get_pickup_areas(
    request: Request,
    db: Session = Depends(get_db),
):
    """The areas a new listing can be collected from. Public: the item filter needs them too."""
    read_limiter.enforce(
        client_key(request, "read-pickup-areas"),
        "Too many requests. Please slow down.",
    )
    return db.scalars(
        select(PickupArea)
        .where(PickupArea.is_active.is_(True))
        .order_by(PickupArea.sort_order, PickupArea.name)
    ).all()
