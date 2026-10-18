#config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InfyExchange"
    environment: str = "development"

    database_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080

    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str

    listing_expiry_days: int = 30
    max_images_per_listing: int = 5
    max_image_size_mb: int = 5

    cors_origins: str = "http://localhost:4200"
    allowed_email_domains: str = "gmail.com"

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