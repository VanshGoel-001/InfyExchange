from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.enums import InterestStatus, ListingStatus, ListingType


def _not_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Message cannot be empty")
    return value


class MessageCreate(BaseModel):
    body: str = Field(max_length=1000)

    _strip = field_validator("body")(_not_blank)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    body: str
    created_at: datetime


class ReportCreate(BaseModel):
    reason: str = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_has_substance(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Please say a little more about what went wrong")
        return value


class ChatState(BaseModel):
    """Everything the chat screen needs, plus any messages newer than `after_id`."""

    interest_id: int
    listing_id: int
    listing_title: str
    listing_type: ListingType
    listing_status: ListingStatus
    price: int
    price_unit: str | None
    status: InterestStatus

    i_am_owner: bool
    other_name: str
    other_role: str | None
    # False for a declined/expired/closed-out chat, when either side blocked, or after a return.
    can_send: bool
    blocked_by_me: bool

    deal_closed_at: datetime | None
    returned_at: datetime | None
    received_confirmed: bool | None
    # Owner only: the 48-hour "close the deal?" reminder has fired and nothing has happened since.
    reminder_pending: bool

    messages: list[MessageResponse]
