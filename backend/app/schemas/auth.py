from datetime import date

from pydantic import BaseModel, EmailStr, Field

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


class LoginRequest(BaseModel):
    email: EmailStr

    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"