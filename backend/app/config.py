#config.py
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InfyExchange"
    environment: str = "development"

    database_url: str
    database_url_unpooled: str | None = None

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080

    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str

    listing_expiry_days: int = 30
    max_images_per_listing: int = 5
    max_image_size_mb: int = 5

    duplicate_submission_window_seconds: int = 60

    # PostgreSQL Connection Pooling Config
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800  # Recycle connections every 30 mins (below PG idle timeout)

    cors_origins: str = "http://localhost:4200"
    allowed_email_domains: str = "gmail.com"

    # OAuth client ID (public, not a secret) of the Google Sign-In web client.
    # Empty disables "Sign in with Google": the endpoint answers 503.
    google_client_id: str = ""

    # --- Email ---
    # "console" prints emails to the log (local dev, or no account yet); "brevo" sends them
    # over HTTPS. An unknown value stops the app at startup instead of silently not sending.
    email_provider: Literal["console", "brevo"] = "console"
    email_api_key: str = ""
    # Must be a sender verified in Brevo.
    sender_email: str = ""
    # Receives an alert for every enquiry.
    admin_email: str = ""

    # --- Enquiry timing ---
    pending_enquiry_expiry_days: int = 7
    chat_inactivity_reminder_hours: int = 48
    maintenance_interval_seconds: int = 3600

    # --- Security headers ---
    referrer_policy: str = "strict-origin-when-cross-origin"
    permissions_policy: str = "camera=(), microphone=(), geolocation=(), payment=()"
    # Strict CSP for JSON API responses; documentation endpoints are exempt
    api_csp: str = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

    # HSTS is only sent after TLS coverage for the deployed host is confirmed (see runbook)
    hsts_enabled: bool = False
    hsts_max_age: int = 15552000  # 180 days
    hsts_include_subdomains: bool = False

    # Comma-separated hosts accepted in the Host header; empty disables the check
    allowed_hosts: str = ""

    # --- Rate limits (requests per window, keyed per client IP unless noted) ---
    rate_limit_window_seconds: int = 60
    rate_limit_login: int = 10
    rate_limit_register: int = 5
    rate_limit_create: int = 10
    rate_limit_read: int = 120
    rate_limit_contact: int = 20
    rate_limit_admin: int = 60
    # Per signed-in user (not per IP: many trainees share one campus address).
    rate_limit_chat: int = 30
    rate_limit_action: int = 30
    rate_limit_poll: int = 90

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [
            domain.strip().lower()
            for domain in self.allowed_email_domains.split(",")
            if domain.strip()
        ]


settings = Settings()