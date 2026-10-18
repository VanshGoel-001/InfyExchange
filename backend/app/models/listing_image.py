from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(primary_key=True)

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cloudinary_public_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    image_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    listing = relationship(
        "Listing",
        back_populates="images",
    )