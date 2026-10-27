# logging_utils.py - Central logging configuration for application and security events
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Correlation ID assigned per request by app.middleware.RequestContextMiddleware
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestContextFilter(logging.Filter):
    """Injects the current request correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class UTCFormatter(logging.Formatter):
    """Formats timestamps as UTC ISO-8601 so logs align across hosts."""

    def formatTime(self, record, datefmt=None):
        stamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        )
        return stamp.strftime("%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z"


_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once with UTC timestamps and request IDs."""
    root = logging.getLogger()

    if getattr(root, "_infy_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(UTCFormatter(_LOG_FORMAT))
    handler.addFilter(RequestContextFilter())

    root.addHandler(handler)
    root.setLevel(level)
    root._infy_configured = True


def get_security_logger() -> logging.Logger:
    """Logger for security-relevant events (auth failures, rate limits, admin denials).

    Never log passwords, tokens, or raw personal data here.
    """
    return logging.getLogger("security")
