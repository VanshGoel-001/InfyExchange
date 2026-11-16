from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PickupArea(Base):
    """A place on campus where a listing can be collected. Admin-editable."""

    __tablename__ = "pickup_areas"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        unique=True,
    )

    # Areas such as ECC have numbered blocks; the listing form then offers a block number.
    has_blocks: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Inactive areas stay on existing listings but cannot be picked for new ones.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
