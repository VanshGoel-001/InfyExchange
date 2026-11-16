from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IdempotencyKey(Base):
    """Remembers the outcome of one write for a day, so a retried request cannot do it twice."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)

    # What the key was used for ("listing.create"); the same key on a different action is refused.
    scope: Mapped[str] = mapped_column(String(40), nullable=False)

    # The id of what the first attempt created. Empty only while that attempt is still running.
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
