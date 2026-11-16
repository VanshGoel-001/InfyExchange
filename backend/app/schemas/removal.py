from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OwnerRemoval(BaseModel):
    """Optional body of an owner's delete. Older clients send none, which counts as OWNER_DELETED."""

    reason: Literal[
        "OWNER_SOLD",
        "OWNER_UNAVAILABLE",
        "OWNER_MISTAKE",
        "OWNER_DELETED",
    ] = "OWNER_DELETED"


class AdminRemoval(BaseModel):
    """An admin has to say why. The owner is shown this text."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=3, max_length=200)
