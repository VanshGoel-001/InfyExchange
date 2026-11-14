from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Report(Base):
    """A user's complaint about the other person in a chat, for admins to review."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    reported_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    interest_id: Mapped[int | None] = mapped_column(
        ForeignKey("interests.id", ondelete="SET NULL"),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
