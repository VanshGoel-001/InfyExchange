"""In-app notifications (the bell).

`notify` only adds the row to the caller's session; the caller commits.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user_block import UserBlock


def short(text: str | None, limit: int = 60) -> str:
    """Trim a user-supplied name/title so a notification can never overflow its column."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def notify(
    db: Session,
    user_id: int,
    kind: str,
    message: str,
    interest_id: int | None = None,
) -> None:
    db.add(
        Notification(
            user_id=user_id,
            kind=kind,
            message=message[:300],
            interest_id=interest_id,
            created_at=datetime.utcnow(),
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
