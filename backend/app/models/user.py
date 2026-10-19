from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    phone: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        nullable=False,
    )

    is_admin: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    joining_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    listings = relationship(
        "Listing",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    needs = relationship(
        "Need",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    interests = relationship(
        "Interest",
        back_populates="interested_user",
        cascade="all, delete-orphan",
    )