from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Removal(Base):
    """What was removed, by whom, when and why. Written in the same transaction as the delete.

    It keeps the facts needed to answer "what happened to that listing", and nothing that is
    personal beyond the owner's account id, which is cleared if the account is deleted.
    """

    __tablename__ = "removals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # LISTING or NEED.
    kind: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # The id the item had. It no longer exists, so this is not a foreign key.
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(150), nullable=False)

    category: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # The listing type (SELL, RENT, ...) or the need type (BUY, RENT, BORROW).
    item_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # The price of a listing or the budget of a need, in whole rupees.
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Empty when nobody did it: the item expired.
    removed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # The reason an admin typed.
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    owner = relationship("User", foreign_keys=[owner_id])
    removed_by = relationship("User", foreign_keys=[removed_by_id])
