from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    interest_id: int | None
    created_at: datetime
    read: bool


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationResponse]
