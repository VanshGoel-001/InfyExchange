from pydantic import BaseModel, ConfigDict, Field


class PickupAreaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    has_blocks: bool


class PickupAreaAdminResponse(PickupAreaResponse):
    is_active: bool
    sort_order: int


class PickupAreaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=60)
    has_blocks: bool = False


class PickupAreaUpdate(BaseModel):
    """Only the fields that are sent change; unknown fields are a 422."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=2, max_length=60)
    has_blocks: bool | None = None
    is_active: bool | None = None
