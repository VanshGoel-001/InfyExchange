"""Shared fixtures for the security test suite.

The environment is configured BEFORE any application module is imported so that
pydantic-settings picks up the test values, and the SQLAlchemy engine is swapped
for an isolated SQLite database (no PostgreSQL server required).
"""

import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

# Configure the environment before any app import
_DB_FILE = os.path.join(tempfile.gettempdir(), "infyexchange_security_tests.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use"
os.environ["CLOUDINARY_CLOUD_NAME"] = "test-cloud"
os.environ["CLOUDINARY_API_KEY"] = "test-key"
os.environ["CLOUDINARY_API_SECRET"] = "test-secret"
os.environ["ENVIRONMENT"] = "test"
os.environ["CORS_ORIGINS"] = "http://allowed.example"
os.environ["ALLOWED_EMAIL_DOMAINS"] = "gmail.com"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import database  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401 - import registers all tables
    Interest,
    Listing,
    ListingImage,
    Need,
    User,
)

test_engine = create_engine(
    f"sqlite:///{_DB_FILE}",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Route all sessions created by get_db() to the isolated test database
database.engine = test_engine
database.SessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def _no_lifespan(app):
    """Skip migrations and the cleanup background task during tests."""
    yield


from app.main import app  # noqa: E402 - must import after engine override
from app.services.auth import create_access_token, hash_password  # noqa: E402
from app.utils.enums import (  # noqa: E402
    InterestStatus,
    ItemCondition,
    ListingCategory,
    ListingStatus,
    ListingType,
    UserRole,
)

app.router.lifespan_context = _no_lifespan


@pytest.fixture(autouse=True)
def fresh_database():
    """Recreate all tables and reset rate limiter state before each test."""
    from app.services import rate_limit

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    for limiter in (
        rate_limit.login_limiter,
        rate_limit.account_login_limiter,
        rate_limit.register_limiter,
        rate_limit.create_limiter,
        rate_limit.read_limiter,
        rate_limit.contact_limiter,
        rate_limit.admin_limiter,
    ):
        limiter._requests.clear()

    yield


@pytest.fixture()
def db_session():
    session = database.SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


# --- Factories -------------------------------------------------------------


def make_user(
    db,
    email: str | None = None,
    password: str = "Passw0rd1",
    is_admin: bool = False,
    is_active: bool = True,
):
    user = User(
        name="Test User",
        email=email or f"user-{uuid.uuid4().hex[:12]}@gmail.com",
        phone=str(uuid.uuid4().int)[:10],
        password_hash=hash_password(password),
        role=UserRole.SE,
        is_admin=is_admin,
        is_active=is_active,
        joining_date=date.today(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def auth_headers(user) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_listing(db, owner, title: str = "Security test listing"):
    now = datetime.utcnow()

    listing = Listing(
        owner_id=owner.id,
        title=title,
        category=ListingCategory.OTHER,
        listing_type=ListingType.SELL,
        price=100,
        price_unit=None,
        condition=ItemCondition.GOOD,
        location="Test City",
        description="Listing created by the security test suite",
        status=ListingStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=7),
    )

    db.add(listing)
    db.commit()
    db.refresh(listing)

    return listing


def make_interest(db, listing, interested_user, status: InterestStatus):
    interest = Interest(
        listing_id=listing.id,
        interested_user_id=interested_user.id,
        message="Security test interest",
        status=status,
    )

    db.add(interest)
    db.commit()
    db.refresh(interest)

    return interest


def register_payload(email: str, password: str = "Passw0rd1") -> dict:
    return {
        "name": "New User",
        "email": email,
        "phone": str(uuid.uuid4().int)[:10],
        "password": password,
        "role": "SE",
        "joining_date": "2026-01-01",
    }
