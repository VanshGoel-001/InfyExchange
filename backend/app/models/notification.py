from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base


class Notification(Base):
    """An in-app notification shown in the bell."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Short machine label (e.g. "enquiry_accepted"); the SPA only uses it to pick an icon.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)

    # Kept only so the previous release keeps working during a rollout. The SPA no longer shows it:
    # it builds the wording from kind, actor, listing and detail below.
    message: Mapped[str] = mapped_column(String(300), nullable=False)

    # Who did it. SET NULL so a deleted account leaves the notification (without a name).
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The listing's title at the time, so the line still reads right after the listing is deleted.
    listing_title: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # One short plain-text extra (a chat preview, a price change, or a code such as "received"). Never contact details.
    detail: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Where the click goes. SET NULL so a deleted enquiry leaves the text readable.
    interest_id: Mapped[int | None] = mapped_column(
        ForeignKey("interests.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # created_at + NOTIFICATION_EXPIRY_DAYS. Queries only return rows where this is still in the future,
    # and the daily cleanup deletes the rest.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=settings.notification_expiry_days),
        nullable=False,
        index=True,
    )

    actor = relationship("User", foreign_keys=[actor_id])
    interest = relationship("Interest", foreign_keys=[interest_id])

    __table_args__ = (
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
    )
