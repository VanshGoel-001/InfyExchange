from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import (
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
)


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    category: Mapped[ListingCategory] = mapped_column(
        Enum(ListingCategory),
        nullable=False,
        index=True,
    )

    listing_type: Mapped[ListingType] = mapped_column(
        Enum(ListingType),
        nullable=False,
        index=True,
    )

    price: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    price_unit: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    condition: Mapped[ItemCondition] = mapped_column(
        Enum(ItemCondition),
        nullable=False,
    )

    # Display text such as "ECC - 87", kept in step with pickup_area_id/block_no. Rows written by
    # the previous release only have this column, so the two new ones stay nullable.
    location: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    pickup_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_areas.id"),
        nullable=True,
        index=True,
    )

    block_no: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus),
        default=ListingStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    owner = relationship(
        "User",
        back_populates="listings",
    )

    # Joined on every load: it is a handful of rows and every listing payload shows the area name.
    pickup_area = relationship(
        "PickupArea",
        lazy="joined",
    )

    # Upload order, so the first photo is always the one shown on cards and the detail page.
    images = relationship(
        "ListingImage",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="ListingImage.id",
    )

    interests = relationship(
        "Interest",
        back_populates="listing",
        cascade="all, delete-orphan",
    )