from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.enums import InterestStatus, ListingStatus, ListingType


class InterestCreate(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=500,
    )


class InterestDecline(BaseModel):
    """Optional one-line reply sent along with a decline."""

    reply: str | None = Field(
        default=None,
        max_length=200,
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
    listing_type: ListingType | None = None
    listing_status: ListingStatus | None = None
    interested_user_name: str | None = None
    interested_user_role: str | None = None

    decline_reply: str | None = None
    deal_closed_at: datetime | None = None
    returned_at: datetime | None = None
    received_confirmed: bool | None = None
    # Messages from the other person that this user has not opened yet.
    unread_count: int = 0


class ContactResponse(BaseModel):
    name: str
    email: str
    phone: str


class ReceivedAnswer(BaseModel):
    received: bool
