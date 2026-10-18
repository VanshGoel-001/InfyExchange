from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import (
    ListingCategory,
    NeedStatus,
    NeedType,
)


class NeedCreate(BaseModel):
    title: str = Field(
        min_length=2,
        max_length=150,
    )

    category: ListingCategory

    need_type: NeedType

    duration: str | None = Field(
        default=None,
        max_length=100,
    )

    budget: int = Field(
        default=0,
        ge=0,
    )

    location: str = Field(
        min_length=2,
        max_length=100,
    )

    description: str = Field(
        min_length=2,
        max_length=2000,
    )


class NeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    category: ListingCategory
    need_type: NeedType
    duration: str | None
    budget: int
    location: str
    description: str
    status: NeedStatus
    created_at: datetime
    expires_at: datetime

    user_name: str | None = None