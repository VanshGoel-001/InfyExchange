"""Time-based enquiry rules, run on a timer.

* A pending enquiry the owner never answered closes after
  PENDING_ENQUIRY_EXPIRY_DAYS (7) and the buyer is told.
* A chat with no activity for CHAT_INACTIVITY_REMINDER_HOURS (48) gets one
  reminder to the owner ("close the deal or say it is still available").
  Any new message, or the owner pressing "Still available", re-arms it.

It is idempotent, so running it often (or from several instances) is safe.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import SessionLocal
from app.models.interest import Interest
from app.models.listing import Listing
from app.services.notify import notify, short
from app.utils.enums import InterestStatus, ListingStatus

logger = logging.getLogger(__name__)

# Distinct from the migration lock in services/migration.py.
_ADVISORY_LOCK_ID = 74193820417


def _expire_pending(db: Session, now: datetime) -> int:
    cutoff = now - timedelta(days=settings.pending_enquiry_expiry_days)

    stale = db.scalars(
        select(Interest)
        .options(joinedload(Interest.listing))
        .where(
            Interest.status == InterestStatus.PENDING,
            Interest.created_at <= cutoff,
        )
    ).all()

    for interest in stale:
        interest.status = InterestStatus.CLOSED
        notify(
            db,
            interest.interested_user_id,
            "enquiry_expired",
            f"Your enquiry about \"{short(interest.listing.title)}\" "
            f"expired because the seller did not reply within "
            f"{settings.pending_enquiry_expiry_days} days.",
            interest.id,
        )

    return len(stale)


def _remind_inactive(db: Session, now: datetime) -> int:
    cutoff = now - timedelta(hours=settings.chat_inactivity_reminder_hours)

    quiet = db.scalars(
        select(Interest)
        .join(Listing)
        .options(
            joinedload(Interest.listing).joinedload(Listing.owner),
            joinedload(Interest.interested_user),
        )
        .where(
            Interest.status == InterestStatus.ACCEPTED,
            Interest.reminder_sent_at.is_(None),
            Listing.status == ListingStatus.ACTIVE,
            func.coalesce(
                Interest.last_activity_at, Interest.created_at
            )
            <= cutoff,
        )
    ).all()

    for interest in quiet:
        interest.reminder_sent_at = now

        notify(
            db,
            interest.listing.owner_id,
            "completion_reminder",
            f"Your chat with {short(interest.interested_user.name)} about "
            f"\"{short(interest.listing.title)}\" has been quiet. "
            "Close the deal, or tell them it is still available.",
            interest.id,
        )

    return len(quiet)


def run_maintenance(now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()

    db = SessionLocal()

    try:
        # With several Cloud Run instances only one should do the work, or
        # owners would get duplicate reminders. The lock ends with the transaction.
        if db.get_bind().dialect.name == "postgresql":
            got_lock = db.scalar(
                text("SELECT pg_try_advisory_xact_lock(:id)"),
                {"id": _ADVISORY_LOCK_ID},
            )

            if not got_lock:
                return {"skipped": True, "expired": 0, "reminded": 0}

        expired = _expire_pending(db, now)
        reminded = _remind_inactive(db, now)

        db.commit()
    finally:
        db.close()

    logger.info(
        "Maintenance expired %d pending enquiry(ies), sent %d reminder(s).",
        expired,
        reminded,
    )

    return {"skipped": False, "expired": expired, "reminded": reminded}


async def maintenance_loop():
    while True:
        try:
            # Off the event loop: it is blocking database work.
            await asyncio.to_thread(run_maintenance)
        except Exception:
            logger.exception("Maintenance loop iteration failed.")

        await asyncio.sleep(settings.maintenance_interval_seconds)
