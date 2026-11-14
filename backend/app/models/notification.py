from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

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

    # Plain text shown to the person. Never put contact details in here.
    message: Mapped[str] = mapped_column(String(300), nullable=False)

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

    __table_args__ = (
        Index("ix_notifications_user_id_read_at", "user_id", "read_at"),
    )
