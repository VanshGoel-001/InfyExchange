from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationList
from app.services.notify import short
from app.services.rate_limit import action_limiter, poll_limiter, user_key
from app.utils.names import clean_name


router = APIRouter(
    prefix="/api/notifications",
    tags=["Notifications"],
)

# Rows written before the structured columns existed have no actor. Who it was follows from what happened.
_BY_BUYER = {"enquiry_received", "received_answer", "completion_reminder"}
_BY_OWNER = {"enquiry_accepted", "enquiry_declined", "deal_closed", "price_changed", "item_returned"}

# Only these are system notices with nobody behind them. Every other kind needs a named sender.
_NO_SENDER = {"enquiry_expired", "enquiry_closed"}

# Most that is ever read for one person: 30 days of notifications is far fewer than this.
_SCAN_LIMIT = 500


def _actor(row: Notification):
    if row.actor is not None:
        return row.actor
    interest = row.interest
    if interest is None:
        return None
    owner = interest.listing.owner
    if row.kind in _BY_BUYER:
        return interest.interested_user
    if row.kind in _BY_OWNER:
        return owner
    if row.kind == "new_message":
        return interest.interested_user if row.user_id == owner.id else owner
    return None


def _present(row: Notification) -> dict | None:
    """Structured fields only; the SPA words the notification from them.

    None means the notification is hidden: it needs a sender and none can be named (the account is gone).
    """
    actor = _actor(row)
    name = short(clean_name(actor.name), 40) if actor is not None else ""

    if row.kind not in _NO_SENDER and not name:
        return None

    listing = row.interest.listing if row.interest is not None else None
    title = row.listing_title or (listing.title if listing is not None else None)

    return {
        "id": row.id,
        "kind": row.kind,
        "actor_name": name or None,
        "listing_id": listing.id if listing is not None else None,
        "listing_title": short(title, 150) if title else None,
        "detail": row.detail,
        "interest_id": row.interest_id,
        "created_at": row.created_at,
        "read": row.read_at is not None,
    }


def _live(user: User):
    """This member's notifications that have not expired."""
    return (Notification.user_id == user.id, Notification.expires_at > datetime.utcnow())


def _unread_count(db: Session, user: User) -> int:
    """Counted over exactly what the list can show, so the badge matches it."""
    rows = db.scalars(
        select(Notification)
        .options(
            joinedload(Notification.actor),
            selectinload(Notification.interest).options(
                joinedload(Interest.listing).joinedload(Listing.owner),
                joinedload(Interest.interested_user),
            ),
        )
        .where(*_live(user), Notification.read_at.is_(None))
        .limit(_SCAN_LIMIT)
    ).all()
    return sum(1 for row in rows if _present(row) is not None)


@router.get(
    "",
    response_model=NotificationList,
)
def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The latest notifications that have not expired, newest first, plus the unread total for the bell badge."""

    poll_limiter.enforce(
        user_key(current_user.id, "notifications"),
        "Too many requests. Please slow down.",
    )

    rows = db.scalars(
        select(Notification)
        .options(
            joinedload(Notification.actor),
            selectinload(Notification.interest).options(
                joinedload(Interest.listing).joinedload(Listing.owner),
                joinedload(Interest.interested_user),
            ),
        )
        .where(*_live(current_user))
        .order_by(Notification.id.desc())
        .limit(_SCAN_LIMIT)
    ).all()

    visible = [item for item in (_present(row) for row in rows) if item is not None]

    return {
        "unread_count": sum(1 for item in visible if not item["read"]),
        "items": visible[:limit],
    }


@router.post("/read-all")
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action_limiter.enforce(
        user_key(current_user.id, "notifications-read"),
        "Too many requests. Please try again later.",
    )

    db.execute(
        update(Notification)
        .where(*_live(current_user), Notification.read_at.is_(None))
        .values(read_at=datetime.utcnow())
    )
    db.commit()

    return {"unread_count": 0}


def _own_notification(db: Session, notification_id: int, user: User) -> Notification:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, *_live(user))
    )

    # Someone else's id, an expired one and one that never existed are all the same 404, so ids cannot be probed.
    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    return notification


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action_limiter.enforce(
        user_key(current_user.id, "notifications-read"),
        "Too many requests. Please try again later.",
    )

    notification = _own_notification(db, notification_id, current_user)

    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        db.commit()

    return {"unread_count": _unread_count(db, current_user)}


@router.delete("")
def clear_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete every notification of the logged-in member (the SPA asks "Clear all? Yes / No" first)."""

    action_limiter.enforce(
        user_key(current_user.id, "notifications-delete"),
        "Too many requests. Please try again later.",
    )

    db.execute(delete(Notification).where(Notification.user_id == current_user.id))
    db.commit()

    return {"unread_count": 0}


@router.delete("/{notification_id}")
def delete_one(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action_limiter.enforce(
        user_key(current_user.id, "notifications-delete"),
        "Too many requests. Please try again later.",
    )

    _own_notification(db, notification_id, current_user)

    db.execute(
        delete(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    db.commit()

    return {"unread_count": _unread_count(db, current_user)}
