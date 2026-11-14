from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationList
from app.services.rate_limit import action_limiter, poll_limiter, user_key


router = APIRouter(
    prefix="/api/notifications",
    tags=["Notifications"],
)


@router.get(
    "",
    response_model=NotificationList,
)
def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first, plus the unread total the bell badge shows."""

    poll_limiter.enforce(
        user_key(current_user.id, "notifications"),
        "Too many requests. Please slow down.",
    )

    unread_count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )

    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.id.desc())
        .limit(limit)
    ).all()

    return {
        "unread_count": unread_count or 0,
        "items": [
            {
                "id": row.id,
                "kind": row.kind,
                "message": row.message,
                "interest_id": row.interest_id,
                "created_at": row.created_at,
                "read": row.read_at is not None,
            }
            for row in rows
        ],
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
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.utcnow())
    )
    db.commit()

    return {"unread_count": 0}


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

    notification = db.get(Notification, notification_id)

    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        db.commit()

    return {"read": True}
