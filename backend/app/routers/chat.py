import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.interest import Interest
from app.models.message import Message
from app.models.report import Report
from app.models.user import User
from app.models.user_block import UserBlock
from app.schemas.chat import (
    ChatState,
    MessageCreate,
    MessageResponse,
    ReportCreate,
)
from app.services.notify import (
    is_blocked_between,
    notify,
    short,
)
from app.services.rate_limit import (
    action_limiter,
    chat_limiter,
    poll_limiter,
    user_key,
)
from app.utils.enums import InterestStatus

security_logger = logging.getLogger("security")

# One page of a thread; the SPA asks for newer messages with after_id.
MAX_MESSAGES_PER_POLL = 200

router = APIRouter(
    prefix="/api/interests",
    tags=["Chat"],
)


def _participant_interest(
    db: Session,
    interest_id: int,
    current_user: User,
) -> tuple[Interest, User]:
    """Load an enquiry for one of its two people, returning it with the other person."""

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

    owner = interest.listing.owner

    if current_user.id == owner.id:
        return interest, interest.interested_user

    if current_user.id == interest.interested_user_id:
        return interest, owner

    raise HTTPException(
        status_code=403,
        detail="You are not part of this conversation",
    )


def _chat_is_open(interest: Interest) -> bool:
    """Chatting, or the enquiry the deal was closed with until the item is returned."""
    return interest.status == InterestStatus.ACCEPTED or (
        interest.status == InterestStatus.CLOSED
        and interest.deal_closed_at is not None
        and interest.returned_at is None
    )


def _blocked_by_me(db: Session, me: int, other: int) -> bool:
    return (
        db.scalar(
            select(UserBlock.id).where(
                UserBlock.blocker_id == me,
                UserBlock.blocked_id == other,
            )
        )
        is not None
    )


@router.get(
    "/{interest_id}/chat",
    response_model=ChatState,
)
def get_chat(
    interest_id: int,
    after_id: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The chat screen's one call: enquiry state plus messages newer than `after_id`.

    Fetching the thread marks the other person's messages as read.
    """

    poll_limiter.enforce(
        user_key(current_user.id, "chat-poll"),
        "Too many requests. Please slow down.",
    )

    interest, other = _participant_interest(db, interest_id, current_user)
    listing = interest.listing

    query = select(Message).where(
        Message.interest_id == interest.id,
        Message.id > after_id,
    )

    if after_id == 0:
        # First load: the most recent page, shown oldest first.
        messages = list(
            reversed(
                db.scalars(
                    query.order_by(Message.id.desc()).limit(
                        MAX_MESSAGES_PER_POLL
                    )
                ).all()
            )
        )
    else:
        messages = db.scalars(
            query.order_by(Message.id).limit(MAX_MESSAGES_PER_POLL)
        ).all()

    unread = db.execute(
        update(Message)
        .where(
            Message.interest_id == interest.id,
            Message.sender_id != current_user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.utcnow())
    )

    if unread.rowcount:
        db.commit()

    i_am_owner = current_user.id == listing.owner_id
    blocked = is_blocked_between(db, current_user.id, other.id)

    return {
        "interest_id": interest.id,
        "listing_id": listing.id,
        "listing_title": listing.title,
        "listing_type": listing.listing_type,
        "listing_status": listing.status,
        "price": listing.price,
        "price_unit": listing.price_unit,
        "status": interest.status,
        "i_am_owner": i_am_owner,
        "other_name": other.name,
        "other_role": other.role.value if other.role else None,
        "can_send": _chat_is_open(interest) and not blocked,
        "blocked_by_me": _blocked_by_me(db, current_user.id, other.id),
        "deal_closed_at": interest.deal_closed_at,
        "returned_at": interest.returned_at,
        "received_confirmed": interest.received_confirmed,
        "reminder_pending": (
            i_am_owner
            and interest.status == InterestStatus.ACCEPTED
            and interest.reminder_sent_at is not None
        ),
        "messages": messages,
    }


@router.post(
    "/{interest_id}/messages",
    response_model=MessageResponse,
    status_code=201,
)
def send_message(
    interest_id: int,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    chat_limiter.enforce(
        user_key(current_user.id, "chat-send"),
        "You are sending messages too quickly. Please wait a moment.",
    )

    interest, other = _participant_interest(db, interest_id, current_user)

    if is_blocked_between(db, current_user.id, other.id):
        # Same wording for both directions: never reveal who blocked whom.
        raise HTTPException(
            status_code=403,
            detail="You cannot message this person.",
        )

    if not _chat_is_open(interest):
        raise HTTPException(
            status_code=403,
            detail="This chat is closed.",
        )

    # If they already have unread messages from me they have been told once;
    # another bell entry per message would only be noise.
    already_notified = db.scalar(
        select(func.count(Message.id)).where(
            Message.interest_id == interest.id,
            Message.sender_id == current_user.id,
            Message.read_at.is_(None),
        )
    )

    now = datetime.utcnow()

    message = Message(
        interest_id=interest.id,
        sender_id=current_user.id,
        body=data.body,
        created_at=now,
    )

    db.add(message)

    interest.last_activity_at = now
    interest.reminder_sent_at = None

    title = short(interest.listing.title)

    if not already_notified:
        notify(
            db,
            other.id,
            "new_message",
            f"New message from {short(current_user.name)} about "
            f"\"{title}\".",
            interest.id,
        )

    db.commit()
    db.refresh(message)

    return message


@router.post(
    "/{interest_id}/report",
    status_code=201,
)
def report_user(
    interest_id: int,
    data: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Report the other person in this chat for admins to review."""

    action_limiter.enforce(
        user_key(current_user.id, "report"),
        "Too many requests. Please try again later.",
    )

    interest, other = _participant_interest(db, interest_id, current_user)

    db.add(
        Report(
            reporter_id=current_user.id,
            reported_user_id=other.id,
            interest_id=interest.id,
            reason=data.reason,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    security_logger.info(
        "chat_report reporter_id=%s reported_id=%s interest_id=%s",
        current_user.id,
        other.id,
        interest.id,
    )

    return {"message": "Thanks. An admin will look into it."}


@router.post("/{interest_id}/block")
def block_user(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stop all messages between you and the other person in this chat. Safe to repeat."""

    action_limiter.enforce(
        user_key(current_user.id, "block"),
        "Too many requests. Please try again later.",
    )

    _, other = _participant_interest(db, interest_id, current_user)

    if not _blocked_by_me(db, current_user.id, other.id):
        db.add(
            UserBlock(
                blocker_id=current_user.id,
                blocked_id=other.id,
                created_at=datetime.utcnow(),
            )
        )
        db.commit()

    return {"blocked": True}


@router.delete("/{interest_id}/block")
def unblock_user(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action_limiter.enforce(
        user_key(current_user.id, "block"),
        "Too many requests. Please try again later.",
    )

    _, other = _participant_interest(db, interest_id, current_user)

    block = db.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id,
            UserBlock.blocked_id == other.id,
        )
    )

    if block:
        db.delete(block)
        db.commit()

    return {"blocked": False}
