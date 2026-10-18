from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import (
    ListingCategory,
    NeedStatus,
    NeedType,
)


class Need(Base):
    __tablename__ = "needs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
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

    need_type: Mapped[NeedType] = mapped_column(
        Enum(NeedType),
        nullable=False,
    )

    duration: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    budget: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    location: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[NeedStatus] = mapped_column(
        Enum(NeedStatus),
        default=NeedStatus.ACTIVE,
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

    user = relationship(
        "User",
        back_populates="needs",
    )