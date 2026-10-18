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
    title: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )

    price: int | None = Field(
        default=None,
        ge=0,
    )

    price_unit: str | None = None

    condition: ItemCondition | None = None

    location: str | None = None

    description: str | None = None

    status: ListingStatus | None = None