from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.utils.enums import UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str
    role: UserRole
    joining_date: date
    created_at: datetime


class UserActivitySummary(BaseModel):
    my_listings_count: int
    my_needs_count: int
    my_interests_count: int
    requests_received_count: int
    pending_requests_received_count: int