import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse
from app.services import email_service
from app.services.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.services.google import (
    GoogleNotConfigured,
    GoogleTokenError,
    GoogleUnavailable,
    verify_google_id_token,
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


def _require_allowed_domain(email: str) -> None:
    allowed_domains = (
        settings.allowed_email_domain_list
        or ["gmail.com"]
    )

    if any(
        email.endswith(f"@{domain}")
        for domain in allowed_domains
    ):
        return

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


def _google_display_name(claims: dict, email: str) -> str:
    name = str(claims.get("name") or "").strip()[:100]
    if len(name) >= 2:
        return name
    local_part = email.split("@", 1)[0][:100]
    return local_part if len(local_part) >= 2 else "Google user"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):

    register_limiter.enforce(
        client_key(request, "register"),
        "Too many registration attempts. Please try again later.",
    )

    email = data.email.lower()

    _require_allowed_domain(email)

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

    try:
        db.commit()
    except IntegrityError:
        # A simultaneous registration won the race past the checks above.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or phone number already registered",
        )

    db.refresh(user)

    background_tasks.add_task(
        email_service.send_welcome,
        name=user.name,
        email=user.email,
    )

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

    # Google-only accounts have no password hash and can never match here.
    if (
        not user
        or not user.password_hash
        or not verify_password(
            data.password,
            user.password_hash,
        )
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


@router.post(
    "/google",
    response_model=TokenResponse,
)
def google_login(
    data: GoogleLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Sign in, or sign up on first use, with a Google ID token."""

    client_ip = request.client.host if request.client else "unknown"

    login_limiter.enforce(
        client_key(request, "google"),
        "Too many login attempts. Please try again later.",
    )

    try:
        claims = verify_google_id_token(data.credential)
    except (GoogleNotConfigured, GoogleUnavailable):
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not available right now. Please use your email and password.",
        )
    except GoogleTokenError:
        security_logger.warning("google_login_failed ip=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google sign-in failed. Please try again.",
        )

    email = claims["email"].strip().lower()
    google_sub = str(claims["sub"])

    user = db.scalar(select(User).where(User.google_sub == google_sub))

    if user is None:
        _require_allowed_domain(email)

        # An existing account is never merged automatically: registration does
        # not prove mailbox ownership, so merging would let whoever registered
        # an address first keep access after its real owner signs in with Google.
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Please log in with your password.",
            )

        user = User(
            name=_google_display_name(claims, email),
            email=email,
            google_sub=google_sub,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Two first-time requests raced; the other one created the account.
            db.rollback()
            user = db.scalar(select(User).where(User.google_sub == google_sub))
            if user is None:
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists. Please log in with your password.",
                )
        else:
            db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact an administrator.",
        )

    return {
        "access_token": create_access_token(user.id),
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