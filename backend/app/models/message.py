from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    """One chat message between the two people on an enquiry."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    interest_id: Mapped[int] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"),
        nullable=False,
    )

    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Set when the other participant fetches the thread; powers the unread badges.
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    interest = relationship("Interest", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_interest_id_id", "interest_id", "id"),
    )
