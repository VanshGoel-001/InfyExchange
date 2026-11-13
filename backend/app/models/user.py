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

    # phone, role and joining_date are NULL only for accounts created through
    # Google sign-in that have not finished the "complete your profile" step.
    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=True,
    )

    # NULL for Google-only accounts (they have no password to verify).
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Google's stable account id ("sub" claim); the email can change, this cannot.
    google_sub: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
    )

    role: Mapped[UserRole | None] = mapped_column(
        Enum(UserRole),
        nullable=True,
    )

    is_admin: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    joining_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    @property
    def profile_complete(self) -> bool:
        return (
            self.phone is not None
            and self.role is not None
            and self.joining_date is not None
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