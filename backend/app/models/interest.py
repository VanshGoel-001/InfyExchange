from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import InterestStatus


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(primary_key=True)

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    interested_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[InterestStatus] = mapped_column(
        Enum(InterestStatus),
        default=InterestStatus.PENDING,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    listing = relationship(
        "Listing",
        back_populates="interests",
    )

    interested_user = relationship(
        "User",
        back_populates="interests",
    )

    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "interested_user_id",
            name="unique_listing_interest",
        ),
    )