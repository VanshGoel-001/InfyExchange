from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
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

    # Optional one-line reply the owner attached when declining.
    decline_reply: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # Last chat message or owner action; drives the 48-hour "close the deal?" reminder.
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Set on the one enquiry the owner closed the deal with (the others are closed without it).
    deal_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Rent/lend only: when the item came back and the listing went live again.
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # The buyer's optional answer to "Did you get it?"; NULL = not answered.
    received_confirmed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    listing = relationship(
        "Listing",
        back_populates="interests",
    )

    messages = relationship(
        "Message",
        back_populates="interest",
        cascade="all, delete-orphan",
        order_by="Message.id",
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