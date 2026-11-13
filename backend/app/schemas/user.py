from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.enums import UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    # None until a Google-created account finishes the profile step.
    phone: str | None = None
    role: UserRole | None = None
    is_admin: bool = False
    is_active: bool = True
    joining_date: date | None = None
    created_at: datetime
    profile_complete: bool = True


def _not_in_future(value: date | None) -> date | None:
    if value is not None and value > date.today():
        raise ValueError("Joining date cannot be in the future")
    return value


class CompleteProfileRequest(BaseModel):
    """First-time details for an account created through Google sign-in."""

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(pattern=r"^\d{10,15}$")
    role: UserRole
    joining_date: date

    _check_date = field_validator("joining_date")(_not_in_future)


class ProfileUpdate(BaseModel):
    """What a user may change later. Name, email and phone are deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    joining_date: date | None = None

    _check_date = field_validator("joining_date")(_not_in_future)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.role is None and self.joining_date is None:
            raise ValueError("Provide a role or a joining date to update")
        return self


class UserActivitySummary(BaseModel):
    my_listings_count: int
    my_needs_count: int
    my_interests_count: int
    requests_received_count: int
    pending_requests_received_count: int
