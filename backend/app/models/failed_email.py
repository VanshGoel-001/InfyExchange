from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FailedEmail(Base):
    """An email the provider refused or could not be reached for.

    It stays here until an admin retries it (the row is deleted on success) or
    discards it. The message is stored already rendered, so a retry sends
    exactly what the first attempt would have.
    """

    __tablename__ = "failed_emails"

    id: Mapped[int] = mapped_column(primary_key=True)

    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Why it failed, without the recipient or message body.
    error: Mapped[str] = mapped_column(String(300), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
