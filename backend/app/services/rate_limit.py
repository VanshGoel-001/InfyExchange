import time
from collections import defaultdict


class InMemoryRateLimiter:
    """Simple sliding-window rate limiter using in-memory storage."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
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


# Login: 10 attempts per minute per IP
login_limiter = InMemoryRateLimiter(
    max_requests=10,
    window_seconds=60,
)

# Register: 5 attempts per minute per IP
register_limiter = InMemoryRateLimiter(
    max_requests=5,
    window_seconds=60,
)
