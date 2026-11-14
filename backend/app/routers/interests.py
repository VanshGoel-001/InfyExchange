from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    Session,
    joinedload,
)

from app.database import get_db
from app.dependencies import get_complete_user, get_current_user
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.message import Message
from app.models.user import User
from app.schemas.interest import (
    ContactResponse,
    InterestCreate,
    InterestDecline,
    InterestResponse,
    ReceivedAnswer,
)
from app.services import email_service
from app.services.notify import (
    is_blocked_between,
    notify,
    short,
)
from app.services.rate_limit import (
    action_limiter,
    client_key,
    contact_limiter,
    create_limiter,
    user_key,
)
from app.utils.enums import InterestStatus, ListingStatus, ListingType


router = APIRouter(
    prefix="/api/interests",
    tags=["Interests"],
)


def _unread_counts(
    db: Session,
    user_id: int,
    interest_ids: list[int],
) -> dict[int, int]:
    """Messages from the other person that `user_id` has not opened, per enquiry."""

    if not interest_ids:
        return {}

    rows = db.execute(
        select(Message.interest_id, func.count(Message.id))
        .where(
            Message.interest_id.in_(interest_ids),
            Message.sender_id != user_id,
            Message.read_at.is_(None),
        )
        .group_by(Message.interest_id)
    ).all()

    return {interest_id: count for interest_id, count in rows}


def _serialize_interest(
    interest: Interest,
    interested_user: User,
    unread_count: int = 0,
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
        "listing_type": (
            listing.listing_type
            if listing is not None
            else None
        ),
        "listing_status": (
            listing.status
            if listing is not None
            else None
        ),
        "interested_user_name": interested_user.name,
        "interested_user_role": str(
            interested_user.role.value
        ),
        "decline_reply": interest.decline_reply,
        "deal_closed_at": interest.deal_closed_at,
        "returned_at": interest.returned_at,
        "received_confirmed": interest.received_confirmed,
        "unread_count": unread_count,
    }


def _load_interest(db: Session, interest_id: int) -> Interest:
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

    return interest


def _load_owned_interest(
    db: Session,
    interest_id: int,
    current_user: User,
    forbidden_detail: str,
) -> Interest:
    interest = _load_interest(db, interest_id)

    if interest.listing.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=forbidden_detail,
        )

    return interest


@router.post(
    "/listing/{listing_id}",
    response_model=InterestResponse,
    status_code=201,
)
def create_interest(
    listing_id: int,
    data: InterestCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_complete_user),
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

    # Deliberately vague: it must not tell the sender they were blocked.
    if is_blocked_between(db, listing.owner_id, current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You cannot send an enquiry for this item.",
        )

    existing = db.scalar(
        select(Interest).where(
            Interest.listing_id == listing_id,
            Interest.interested_user_id == current_user.id,
        )
    )

    # Pending, chatting and declined enquiries stay final. A CLOSED one (the
    # deal went to someone else, it expired, or the item came back) must not
    # lock the person out of an item that is Available again, so it is reopened.
    if existing and existing.status != InterestStatus.CLOSED:
        raise HTTPException(
            status_code=409,
            detail="You already showed interest",
        )

    now = datetime.utcnow()

    if existing:
        interest = existing
        interest.status = InterestStatus.PENDING
        interest.message = data.message
        interest.created_at = now  # the 7-day expiry starts again
        interest.last_activity_at = now
        interest.reminder_sent_at = None
        interest.deal_closed_at = None
        interest.returned_at = None
        interest.received_confirmed = None
        interest.decline_reply = None
    else:
        interest = Interest(
            listing_id=listing_id,
            interested_user_id=current_user.id,
            message=data.message,
            status=InterestStatus.PENDING,
            last_activity_at=now,
        )
        db.add(interest)

    owner = listing.owner

    try:
        db.flush()

        notify(
            db,
            listing.owner_id,
            "enquiry_received",
            f"{short(current_user.name)} asked about "
            f"\"{short(listing.title)}\".",
            interest.id,
        )

        db.commit()
    except IntegrityError:
        # Two simultaneous submissions both passed the check above; the unique
        # constraint stopped the second. That is a duplicate, not a server fault.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You already showed interest",
        )

    db.refresh(interest)

    background_tasks.add_task(
        email_service.send_enquiry_alert,
        listing_title=listing.title,
        owner_name=owner.name,
        sender_name=current_user.name,
        sender_email=current_user.email,
        message=interest.message,
    )

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

    unread = _unread_counts(
        db,
        current_user.id,
        [interest.id for interest in interests],
    )

    return [
        _serialize_interest(
            interest,
            interest.interested_user,
            unread.get(interest.id, 0),
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

    unread = _unread_counts(
        db,
        current_user.id,
        [interest.id for interest in interests],
    )

    return [
        _serialize_interest(
            interest,
            current_user,
            unread.get(interest.id, 0),
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

    interest = _load_owned_interest(
        db,
        interest_id,
        current_user,
        "Only the listing owner can accept",
    )

    if interest.status != InterestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending interests can be accepted",
        )

    if interest.listing.status != ListingStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="This item is no longer available",
        )

    # Accepting opens the chat. The listing stays Available and other
    # enquiries stay as they are: the owner may talk to several people.
    interest.status = InterestStatus.ACCEPTED
    interest.last_activity_at = datetime.utcnow()
    interest.reminder_sent_at = None

    buyer = interest.interested_user
    title = short(interest.listing.title)

    notify(
        db,
        buyer.id,
        "enquiry_accepted",
        f"{short(current_user.name)} accepted your enquiry about "
        f"\"{title}\". You can chat now.",
        interest.id,
    )

    db.commit()
    db.refresh(interest)

    return interest


@router.patch(
    "/{interest_id}/reject",
    response_model=InterestResponse,
)
def reject_interest(
    interest_id: int,
    data: InterestDecline | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    interest = _load_owned_interest(
        db,
        interest_id,
        current_user,
        "Only the listing owner can reject",
    )

    if interest.status != InterestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only pending interests can be rejected",
        )

    reply = (data.reply or "").strip() if data else ""

    interest.status = InterestStatus.REJECTED
    interest.decline_reply = reply or None

    message = (
        f"{short(current_user.name)} declined your enquiry about "
        f"\"{short(interest.listing.title)}\"."
    )

    if reply:
        message += f" They said: {short(reply, 120)}"

    notify(
        db,
        interest.interested_user_id,
        "enquiry_declined",
        message,
        interest.id,
    )

    db.commit()
    db.refresh(interest)

    return interest


@router.post(
    "/{interest_id}/close-deal",
    response_model=InterestResponse,
)
def close_deal(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sold / rented / lent / given to this person.

    Marks the listing as no longer available and closes every other open
    enquiry on it, telling those people the item has gone.
    """

    action_limiter.enforce(
        user_key(current_user.id, "close-deal"),
        "Too many requests. Please try again later.",
    )

    interest = _load_owned_interest(
        db,
        interest_id,
        current_user,
        "Only the listing owner can close the deal",
    )

    if interest.status != InterestStatus.ACCEPTED:
        raise HTTPException(
            status_code=400,
            detail="You can only close a deal with someone you are chatting with",
        )

    # Lock the listing row so two simultaneous closes cannot both succeed
    # (no-op on SQLite, a real row lock on PostgreSQL).
    # populate_existing: the listing is already loaded, so without it the
    # status checked below could be the stale pre-lock value.
    listing = db.scalar(
        select(Listing)
        .where(Listing.id == interest.listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )

    if listing.status != ListingStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="This item is no longer available",
        )

    now = datetime.utcnow()
    title = short(listing.title)

    listing.status = (
        ListingStatus.SOLD
        if listing.listing_type in {ListingType.SELL, ListingType.GIVEAWAY}
        else ListingStatus.RENTED
    )

    interest.status = InterestStatus.CLOSED
    interest.deal_closed_at = now
    interest.last_activity_at = now

    notify(
        db,
        interest.interested_user_id,
        "deal_closed",
        f"{short(current_user.name)} closed the deal for \"{title}\" with "
        "you. Did you get it? Let them know in the chat.",
        interest.id,
    )

    others = db.scalars(
        select(Interest).where(
            Interest.listing_id == listing.id,
            Interest.id != interest.id,
            Interest.status.in_(
                [InterestStatus.PENDING, InterestStatus.ACCEPTED]
            ),
        )
    ).all()

    for other in others:
        other.status = InterestStatus.CLOSED
        notify(
            db,
            other.interested_user_id,
            "enquiry_closed",
            f"\"{title}\" is no longer available.",
            other.id,
        )

    db.commit()
    db.refresh(interest)

    return interest


@router.post(
    "/{interest_id}/still-available",
    response_model=InterestResponse,
)
def still_available(
    interest_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The owner's answer to the 48-hour reminder: keep chatting, ask again later."""

    action_limiter.enforce(
        user_key(current_user.id, "still-available"),
        "Too many requests. Please try again later.",
    )

    interest = _load_owned_interest(
        db,
        interest_id,
        current_user,
        "Only the listing owner can do this",
    )

    if interest.status != InterestStatus.ACCEPTED:
        raise HTTPException(
            status_code=400,
            detail="This enquiry is not open",
        )

    interest.last_activity_at = datetime.utcnow()
    interest.reminder_sent_at = None

    db.commit()
    db.refresh(interest)

    return interest


@router.post(
    "/{interest_id}/received",
    response_model=InterestResponse,
)
def answer_received(
    interest_id: int,
    data: ReceivedAnswer,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The buyer's optional "Did you get it?" answer after the owner closed the deal."""

    action_limiter.enforce(
        user_key(current_user.id, "received"),
        "Too many requests. Please try again later.",
    )

    interest = _load_interest(db, interest_id)

    if interest.interested_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the person the deal was closed with can answer",
        )

    if interest.deal_closed_at is None:
        raise HTTPException(
            status_code=400,
            detail="The deal has not been closed yet",
        )

    interest.received_confirmed = data.received

    notify(
        db,
        interest.listing.owner_id,
        "received_answer",
        (
            f"{short(current_user.name)} confirmed they got "
            f"\"{short(interest.listing.title)}\"."
            if data.received
            else f"{short(current_user.name)} says they have not got "
            f"\"{short(interest.listing.title)}\" yet."
        ),
        interest.id,
    )

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

    interest = _load_interest(db, interest_id)

    # "Chatting" enquiries, and the one the deal was closed with so the two
    # people can still arrange the handover. Declined and closed-out ones stay private.
    revealable = (
        interest.status == InterestStatus.ACCEPTED
        or (
            interest.status == InterestStatus.CLOSED
            and interest.deal_closed_at is not None
        )
    )

    if not revealable:
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
