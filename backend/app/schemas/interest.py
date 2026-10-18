from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import InterestStatus


class InterestCreate(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=500,
    )


class InterestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    interested_user_id: int
    message: str | None
    status: InterestStatus
    created_at: datetime

    listing_title: str | None = None
    listing_image_url: str | None = None
    interested_user_name: str | None = None
    interested_user_role: str | None = None


class ContactResponse(BaseModel):
    name: str
    email: str
    phone: str