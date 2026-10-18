import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal
from app.models.listing import Listing
from app.models.need import Need
from app.services.cloudinary import delete_image
from app.utils.enums import ListingStatus, NeedStatus

logger = logging.getLogger(__name__)


def cleanup_expired_data():

    db = SessionLocal()

    try:
        now = datetime.utcnow()

        expired_listings = db.scalars(
            select(Listing).where(
                Listing.expires_at <= now
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

        db.commit()

        print(
            f"[CLEANUP] "
            f"Deleted {len(expired_listings)} listings "
            f"and {len(expired_needs)} needs."
        )

    finally:
        db.close()


async def cleanup_loop():

    while True:

        try:
            cleanup_expired_data()

        except Exception as exc:
            print(
                f"[CLEANUP ERROR] {exc}"
            )

        # Run once every 24 hours.
        await asyncio.sleep(60 * 60 * 24)