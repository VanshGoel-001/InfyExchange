from datetime import date
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.enums import UserRole
from app.utils.phone import validate_indian_mobile


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)

    email: EmailStr

    # Accepts "+91 98765 43210" and friends; stored as the bare 10-digit number.
    phone: str = Field(max_length=25)

    password: str = Field(
        min_length=8,
        max_length=100,
    )

    role: UserRole

    joining_date: date

    @field_validator("phone")
    @classmethod
    def phone_is_indian_mobile(cls, value: str) -> str:
        return validate_indian_mobile(value)

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


class GoogleLoginRequest(BaseModel):
    # The ID token (a JWT) returned by Google Sign-In.
    credential: str = Field(min_length=1, max_length=4096)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"