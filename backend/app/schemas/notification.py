from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    actor_name: str | None
    listing_id: int | None
    listing_title: str | None
    detail: str | None
    interest_id: int | None
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationResponse]
