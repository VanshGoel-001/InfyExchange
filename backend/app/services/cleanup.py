import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.models.failed_email import FailedEmail
from app.models.idempotency_key import IdempotencyKey
from app.models.listing import Listing
from app.models.need import Need
from app.models.notification import Notification
from app.models.removal import Removal
from app.services.cloudinary import delete_image
from app.services.removals import record_listing_removal, record_need_removal
from app.utils.enums import ListingStatus, RemovalReason

logger = logging.getLogger(__name__)

# Failed emails hold a recipient address and message body; drop the ones nobody acted on.
FAILED_EMAIL_RETENTION_DAYS = 30


def cleanup_expired_data():

    db = SessionLocal()

    try:
        now = datetime.utcnow()

        expired_listings = db.scalars(
            select(Listing).where(
                Listing.expires_at <= now,
                # An item that is out on loan is not abandoned; it is swept
                # (or renewed) once it comes back.
                Listing.status != ListingStatus.RENTED,
            )
        ).all()

        for listing in expired_listings:

            for image in listing.images:
                try:
                    delete_image(
                        image.cloudinary_public_id
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to delete expired image %s from Cloudinary: %s",
                        image.cloudinary_public_id,
                        exc,
                    )

            record_listing_removal(db, listing, RemovalReason.EXPIRED)
            db.delete(listing)

        expired_needs = db.scalars(
            select(Need).where(
                Need.expires_at <= now
            )
        ).all()

        for need in expired_needs:
            record_need_removal(db, need, RemovalReason.EXPIRED)
            db.delete(need)

        stale_emails = db.scalars(
            select(FailedEmail).where(
                FailedEmail.created_at
                <= now - timedelta(days=FAILED_EMAIL_RETENTION_DAYS)
            )
        ).all()

        for failed_email in stale_emails:
            db.delete(failed_email)

        # Expired notifications are already hidden from every query; this just frees the rows.
        expired_notifications = db.execute(
            delete(Notification).where(Notification.expires_at <= now)
        ).rowcount

        # Old removal records and remembered retries have done their job.
        db.execute(
            delete(Removal).where(
                Removal.created_at <= now - timedelta(days=settings.removal_retention_days)
            )
        )
        db.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.created_at <= now - timedelta(hours=settings.idempotency_key_hours)
            )
        )

        db.commit()

        logger.info(
            "Cleanup deleted %d listing(s), %d need(s) and %d notification(s).",
            len(expired_listings),
            len(expired_needs),
            expired_notifications,
        )

    finally:
        db.close()


async def cleanup_loop():

    while True:

        try:
            # Off the event loop: it runs database queries and Cloudinary deletes,
            # and while it ran on the loop every request in the server stalled.
            await asyncio.to_thread(cleanup_expired_data)

        except Exception:
            logger.exception("Cleanup loop iteration failed.")

        # Run once every 24 hours.
        await asyncio.sleep(60 * 60 * 24)