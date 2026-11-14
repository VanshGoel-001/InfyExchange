from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
        # Mirrors the SPA and keeps the value inside PostgreSQL's 32-bit integer.
        le=10_000_000,
    )

    location: str = Field(
        min_length=2,
        max_length=100,
    )

    description: str = Field(
        min_length=2,
        max_length=2000,
    )

    # Runs before the length rules, so "   " is rejected instead of saved as an empty string.
    @field_validator("title", "duration", "location", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


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