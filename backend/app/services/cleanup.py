import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models.failed_email import FailedEmail
from app.models.listing import Listing
from app.models.need import Need
from app.services.cloudinary import delete_image
from app.utils.enums import ListingStatus

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

            db.delete(listing)

        expired_needs = db.scalars(
            select(Need).where(
                Need.expires_at <= now
            )
        ).all()

        for need in expired_needs:
            db.delete(need)

        stale_emails = db.scalars(
            select(FailedEmail).where(
                FailedEmail.created_at
                <= now - timedelta(days=FAILED_EMAIL_RETENTION_DAYS)
            )
        ).all()

        for failed_email in stale_emails:
            db.delete(failed_email)

        db.commit()

        logger.info(
            "Cleanup deleted %d listing(s) and %d need(s).",
            len(expired_listings),
            len(expired_needs),
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