import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.rate_limit import (
    account_key,
    account_login_limiter,
    client_key,
    login_limiter,
    register_limiter,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)

security_logger = logging.getLogger("security")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):

    client_ip = request.client.host if request.client else "unknown"

    register_limiter.enforce(
        client_key(request, "register"),
        "Too many registration attempts. Please try again later.",
    )

    email = data.email.lower()

    allowed_domains = (
        settings.allowed_email_domain_list
        or ["gmail.com"]
    )

    if not any(
        email.endswith(f"@{domain}")
        for domain in allowed_domains
    ):
        if allowed_domains == ["gmail.com"]:
            detail = "Only Gmail addresses are allowed"
        else:
            detail = (
                "Only email addresses from these "
                "domains are allowed: "
                + ", ".join(
                    f"@{domain}"
                    for domain in allowed_domains
                )
            )

        raise HTTPException(
            status_code=400,
            detail=detail,
        )

    existing_email = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    existing_phone = db.scalar(
        select(User).where(User.phone == data.phone)
    )

    if existing_phone:
        raise HTTPException(
            status_code=409,
            detail="Phone number already registered",
        )

    user = User(
        name=data.name.strip(),
        email=email,
        phone=data.phone.strip(),
        password_hash=hash_password(data.password),
        role=data.role,
        joining_date=data.joining_date,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):

    client_ip = request.client.host if request.client else "unknown"

    login_limiter.enforce(
        client_key(request, "login"),
        "Too many login attempts. Please try again later.",
    )

    # Per-account limit blunts distributed brute force from rotating IPs
    account_login_limiter.enforce(
        account_key(data.email),
        "Too many login attempts for this account. Please try again later.",
    )

    user = db.scalar(
        select(User).where(
            User.email == data.email.lower()
        )
    )

    if not user or not verify_password(
        data.password,
        user.password_hash,
    ):
        security_logger.warning("login_failed ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)

    # "bearer" is the OAuth token type literal, not a secret (B105 is a known
    # bandit false positive for this key name; suppressed inline below).
    return {
        "access_token": token,
        "token_type": "bearer",  # nosec B105
    }


@router.get(
    "/me",
    response_model=UserResponse,
)
def me(
    current_user: User = Depends(get_current_user),
):
    return current_user