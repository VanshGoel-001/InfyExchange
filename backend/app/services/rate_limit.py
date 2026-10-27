# rate_limit.py - In-memory sliding-window rate limiting for abuse protection
import hashlib
import logging
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

# Hard cap so attacker-rotated keys cannot grow process memory without bound
MAX_TRACKED_KEYS = 10_000


class InMemoryRateLimiter:
    """Simple sliding-window rate limiter using in-memory storage.

    Limits are enforced per worker process: they reset on restart and are
    not shared across workers or containers (documented limitation).
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        name: str = "limiter",
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_prune = time.time()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds

        for key in list(self._requests.keys()):
            live = [t for t in self._requests[key] if t > cutoff]

            if live:
                self._requests[key] = live
            else:
                del self._requests[key]

        # Evict oldest keys when a caller rotates across many identities
        while len(self._requests) > MAX_TRACKED_KEYS:
            oldest = next(iter(self._requests))
            del self._requests[oldest]

    def is_allowed(self, key: str) -> bool:
        now = time.time()

        if now - self._last_prune >= self.window_seconds:
            self._prune(now)
            self._last_prune = now

        cutoff = now - self.window_seconds

        # Remove expired timestamps
        self._requests[key] = [
            t for t in self._requests[key]
            if t > cutoff
        ]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def enforce(self, key: str, detail: str) -> None:
        """Raise 429 with Retry-After guidance when the limit is exceeded."""
        if not self.is_allowed(key):
            logger.warning(
                "rate_limit_exceeded limiter=%s window=%ss max=%s",
                self.name,
                self.window_seconds,
                self.max_requests,
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(self.window_seconds)},
            )


def client_key(request: Request, scope: str) -> str:
    """Rate limit key from the client IP as resolved by the trusted proxy."""
    client_ip = request.client.host if request.client else "unknown"
    return f"{scope}:{client_ip}"


def account_key(email: str) -> str:
    """Hashed per-account key so raw emails never enter limiter state or logs."""
    digest = hashlib.sha256(email.lower().encode()).hexdigest()[:32]
    return f"acct:{digest}"


def rate_limit_dependency(
    limiter: "InMemoryRateLimiter",
    scope: str,
    detail: str = "Too many requests. Please try again later.",
):
    """Build a FastAPI dependency that enforces the given limiter."""

    def dependency(request: Request) -> None:
        limiter.enforce(client_key(request, scope), detail)

    return dependency


_window = settings.rate_limit_window_seconds

# Login: per-IP and per-account limits to blunt distributed brute force
login_limiter = InMemoryRateLimiter(
    settings.rate_limit_login,
    _window,
    name="login",
)

account_login_limiter = InMemoryRateLimiter(
    settings.rate_limit_login,
    _window,
    name="login-account",
)

# Register: 5 attempts per minute per IP
register_limiter = InMemoryRateLimiter(
    settings.rate_limit_register,
    _window,
    name="register",
)

# Resource creation (listings, needs, interests)
create_limiter = InMemoryRateLimiter(
    settings.rate_limit_create,
    _window,
    name="create",
)

# Public read/search endpoints
read_limiter = InMemoryRateLimiter(
    settings.rate_limit_read,
    _window,
    name="read",
)

# Contact-detail reveal after accepted interest
contact_limiter = InMemoryRateLimiter(
    settings.rate_limit_contact,
    _window,
    name="contact",
)

# Admin endpoints
admin_limiter = InMemoryRateLimiter(
    settings.rate_limit_admin,
    _window,
    name="admin",
)
