"""Service tests: settings parsing and defaults (task T01)."""

import pytest
from pydantic import ValidationError

from app.config import Settings

REQUIRED = dict(
    database_url="sqlite:///unused.db",
    secret_key="unit-test-secret",
    cloudinary_cloud_name="c",
    cloudinary_api_key="k",
    cloudinary_api_secret="s",
)

# Env vars that, if present in the developer's shell, would hide a default we want to assert.
DEFAULTED_ENV_VARS = [
    "LISTING_EXPIRY_DAYS", "MAX_IMAGES_PER_LISTING", "MAX_IMAGE_SIZE_MB", "DUPLICATE_SUBMISSION_WINDOW_SECONDS",
    "ACCESS_TOKEN_EXPIRE_MINUTES", "ALGORITHM", "HSTS_ENABLED", "DB_POOL_SIZE", "DB_MAX_OVERFLOW",
    "RATE_LIMIT_WINDOW_SECONDS", "RATE_LIMIT_LOGIN", "RATE_LIMIT_REGISTER", "RATE_LIMIT_CREATE",
    "RATE_LIMIT_READ", "RATE_LIMIT_CONTACT", "RATE_LIMIT_ADMIN",
]


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


class TestSettingsDefaults:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for name in DEFAULTED_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

    def test_marketplace_policy_defaults(self):
        """TC-SVC-CFG-001 | AC-20.2, AC-04.1, AC-04.4, AC-04.5, AC-16.1 | T01 | positive | 30-day expiry, 5 images of 5 MB, 60 s duplicate window"""
        s = _settings()
        assert s.listing_expiry_days == 30
        assert s.max_images_per_listing == 5
        assert s.max_image_size_mb == 5
        assert s.duplicate_submission_window_seconds == 60

    def test_auth_defaults(self):
        """TC-SVC-CFG-002 | AC-20.2, AC-02.1 | T01 | positive | HS256 tokens valid for 10080 minutes (7 days)"""
        s = _settings()
        assert s.algorithm == "HS256"
        assert s.access_token_expire_minutes == 10080

    def test_rate_limit_defaults(self):
        """TC-SVC-CFG-003 | AC-20.2, AC-02.4, AC-05.5, AC-10.3, AC-12.7 | T01 | positive | 60 s window; login 10, register 5, create 10, read 120, contact 20, admin 60"""
        s = _settings()
        assert (s.rate_limit_window_seconds, s.rate_limit_login, s.rate_limit_register, s.rate_limit_create,
                s.rate_limit_read, s.rate_limit_contact, s.rate_limit_admin) == (60, 10, 5, 10, 120, 20, 60)

    def test_hsts_is_off_by_default(self):
        """TC-SVC-CFG-004 | AC-20.2, AC-17.1 | T01 | business | HSTS must be explicitly enabled"""
        assert _settings().hsts_enabled is False


class TestSettingsParsing:
    def test_cors_origins_are_split_and_trimmed(self):
        """TC-SVC-CFG-010 | AC-20.3, AC-17.3 | T01 | boundary | comma list is trimmed and empty entries are dropped"""
        s = _settings(cors_origins=" https://a.example , https://b.example ,, ")
        assert s.cors_origin_list == ["https://a.example", "https://b.example"]

    def test_empty_cors_setting_yields_no_origins(self):
        """TC-SVC-CFG-011 | AC-20.3, AC-17.3 | T01 | boundary | an empty CORS_ORIGINS allows no origin"""
        assert _settings(cors_origins="").cors_origin_list == []

    def test_allowed_email_domains_are_lowercased_and_trimmed(self):
        """TC-SVC-CFG-012 | AC-20.3, AC-01.2 | T01 | boundary | domains are normalised to lowercase without whitespace"""
        s = _settings(allowed_email_domains=" Gmail.COM , Company.org ")
        assert s.allowed_email_domain_list == ["gmail.com", "company.org"]

    def test_unknown_environment_variables_are_ignored(self, monkeypatch):
        """TC-SVC-CFG-013 | AC-20.1 | T01 | business | stray env vars do not break startup"""
        monkeypatch.setenv("SOMETHING_UNRELATED", "1")
        assert _settings().app_name == "InfyExchange"


class TestRequiredSettings:
    @pytest.mark.parametrize("missing", list(REQUIRED))
    def test_each_required_setting_is_mandatory(self, monkeypatch, missing):
        """TC-SVC-CFG-020 | AC-20.1 | T01 | negative | omitting any required setting stops the app from starting"""
        for name in REQUIRED:
            monkeypatch.delenv(name.upper(), raising=False)
        values = {k: v for k, v in REQUIRED.items() if k != missing}
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)
