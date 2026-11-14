from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
)


class ListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    category: ListingCategory
    listing_type: ListingType
    price: int
    price_unit: str | None
    condition: ItemCondition
    location: str
    description: str
    status: ListingStatus
    created_at: datetime
    expires_at: datetime

    owner_name: str | None = None
    owner_role: str | None = None
    image_url: str | None = None


class ListingImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_url: str


class ListingDetailResponse(ListingResponse):
    images: list[ListingImageResponse]
    owner_name: str


class ListingUpdate(BaseModel):
    """The only thing an owner can change after posting is the price.

    Everything else is locked so people who already enquired are not misled;
    unknown fields are a 422 rather than silently ignored.
    """

    model_config = ConfigDict(extra="forbid")

    # Whole rupees; the upper bound mirrors the SPA (src/utils/validate.js) and the 32-bit column.
    price: int = Field(ge=1, le=10_000_000)