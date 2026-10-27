from datetime import date
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.enums import UserRole


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    email: EmailStr

    phone: str = Field(
        min_length=10,
        max_length=15,
    )

    password: str = Field(
        min_length=8,
        max_length=100,
    )

    role: UserRole

    joining_date: date

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        """Require at least one letter and one digit alongside the length rule."""
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError(
                "Password must contain at least one letter and one number"
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"