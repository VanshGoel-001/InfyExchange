# middleware.py - Cross-cutting HTTP middleware for request correlation and security headers
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.utils.logging_utils import request_id_var

# Only accept client-supplied correlation IDs with safe characters and length
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Paths that can carry sensitive data must never be stored by browsers or proxies
NO_STORE_PREFIXES = (
    "/api/auth",
    "/api/users/me",
    "/api/interests",
    "/api/admin",
)

# Documentation endpoints load remote assets and inline scripts; they are
# disabled in production and exempt from the strict JSON API CSP
CSP_EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a correlation ID to every request and returns it to the client."""

    async def dispatch(self, request, call_next):
        candidate = request.headers.get("x-request-id", "")
        request_id = (
            candidate
            if _REQUEST_ID_PATTERN.fullmatch(candidate)
            else uuid.uuid4().hex
        )

        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies baseline security headers to every application response."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        headers = response.headers
        path = request.url.path

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", settings.referrer_policy)
        headers.setdefault("Permissions-Policy", settings.permissions_policy)

        if not path.startswith(CSP_EXEMPT_PREFIXES):
            headers.setdefault(
                "Content-Security-Policy",
                settings.api_csp,
            )

        if path.startswith(NO_STORE_PREFIXES):
            headers.setdefault("Cache-Control", "no-store")

        if settings.hsts_enabled:
            policy = f"max-age={settings.hsts_max_age}"

            if settings.hsts_include_subdomains:
                policy += "; includeSubDomains"

            headers.setdefault("Strict-Transport-Security", policy)

        return response
