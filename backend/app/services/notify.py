"""In-app notifications (the bell).

`notify` only adds the row to the caller's session; the caller commits.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.notification import Notification
from app.models.user_block import UserBlock


def short(text: str | None, limit: int = 60) -> str:
    """Trim a user-supplied name/title so a notification can never overflow its column."""
    text = " ".join((text or "").split())
    # The result, ellipsis included, never exceeds `limit`, so it always fits its column.
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def notify(
    db: Session,
    user_id: int,
    kind: str,
    message: str,
    interest_id: int | None = None,
    *,
    actor_id: int | None = None,
    listing_title: str | None = None,
    detail: str | None = None,
) -> None:
    # Nobody is told about something they did themselves.
    if actor_id is not None and actor_id == user_id:
        return

    now = datetime.utcnow()

    db.add(
        Notification(
            user_id=user_id,
            kind=kind,
            message=message[:300],
            interest_id=interest_id,
            actor_id=actor_id,
            listing_title=short(listing_title, 150) if listing_title else None,
            detail=short(detail, 120) if detail else None,
            created_at=now,
            # After this the notification no longer shows and the daily cleanup deletes it.
            expires_at=now + timedelta(days=settings.notification_expiry_days),
        )
    )


def is_blocked_between(db: Session, user_a: int, user_b: int) -> bool:
    """True when either person has blocked the other."""
    return (
        db.scalar(
            select(UserBlock.id).where(
                (
                    (UserBlock.blocker_id == user_a)
                    & (UserBlock.blocked_id == user_b)
                )
                | (
                    (UserBlock.blocker_id == user_b)
                    & (UserBlock.blocked_id == user_a)
                )
            )
        )
        is not None
    )
