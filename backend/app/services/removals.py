"""The record of removed listings and needs.

These only add the row to the caller's session; the caller deletes the item and commits, so the record
and the delete are saved together.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.interest import Interest

from app.models.listing import Listing
from app.models.need import Need
from app.models.removal import Removal
from app.utils.enums import InterestStatus, RemovalReason

OWNER_REASONS = frozenset(
    {
        RemovalReason.OWNER_SOLD,
        RemovalReason.OWNER_UNAVAILABLE,
        RemovalReason.OWNER_MISTAKE,
        RemovalReason.OWNER_DELETED,
    }
)


def open_enquirer_ids(db: Session, listing_id: int) -> list[int]:
    """People still waiting, chatting or holding the item: they lose the enquiry when the listing goes."""
    return list(
        db.scalars(
            select(Interest.interested_user_id).where(
                Interest.listing_id == listing_id,
                or_(
                    Interest.status.in_([InterestStatus.PENDING, InterestStatus.ACCEPTED]),
                    and_(Interest.deal_closed_at.is_not(None), Interest.returned_at.is_(None)),
                ),
            )
        )
    )


def _text(value: Enum | str | None) -> str | None:
    return value.value if isinstance(value, Enum) else value


def record_listing_removal(
    db: Session,
    listing: Listing,
    reason: RemovalReason,
    removed_by_id: int | None = None,
    note: str | None = None,
) -> None:
    db.add(
        Removal(
            kind="LISTING",
            item_id=listing.id,
            title=listing.title,
            category=_text(listing.category),
            item_type=_text(listing.listing_type),
            amount=listing.price,
            owner_id=listing.owner_id,
            removed_by_id=removed_by_id,
            reason=reason.value,
            note=note[:200] if note else None,
            created_at=datetime.utcnow(),
        )
    )


def record_need_removal(
    db: Session,
    need: Need,
    reason: RemovalReason,
    removed_by_id: int | None = None,
    note: str | None = None,
) -> None:
    db.add(
        Removal(
            kind="NEED",
            item_id=need.id,
            title=need.title,
            category=_text(need.category),
            item_type=_text(need.need_type),
            amount=need.budget,
            owner_id=need.user_id,
            removed_by_id=removed_by_id,
            reason=reason.value,
            note=note[:200] if note else None,
            created_at=datetime.utcnow(),
        )
    )
