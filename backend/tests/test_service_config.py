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


class TestRuntimeValidation:
    """Missing configuration stops a production start; it is never papered over with a default."""

    def test_complete_settings_have_no_problems(self):
        """TC-SVC-CFG-040 | AC-20.1 | T01 | positive | a fully configured deployment reports nothing missing"""
        from app.config import validate_runtime_settings

        assert validate_runtime_settings(_settings(cors_origins="https://site.example")) == []

    def test_there_is_no_built_in_cors_origin(self, monkeypatch):
        """TC-SVC-CFG-041 | AC-20.1 | T01 | negative | with CORS_ORIGINS unset the list is empty and validation names the setting"""
        from app.config import validate_runtime_settings

        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        s = _settings()
        assert s.cors_origin_list == []
        assert any("CORS_ORIGINS" in problem for problem in validate_runtime_settings(s))

    def test_problems_name_the_setting_but_never_its_value(self):
        """TC-SVC-CFG-042 | AC-20.1 | T01 | boundary | empty secrets are reported by variable name only; brevo needs its credentials"""
        from app.config import validate_runtime_settings

        s = _settings(secret_key=" ", cors_origins="https://x.example", email_provider="brevo", cloudinary_api_secret="top-secret-value")
        problems = " | ".join(validate_runtime_settings(s))
        assert "SECRET_KEY" in problems and "EMAIL_API_KEY" in problems
        assert "top-secret-value" not in problems

    def test_production_refuses_to_start_without_cors(self, monkeypatch):
        """TC-SVC-CFG-043 | AC-20.1 | T01 | negative | the app's startup raises in production when a required setting is missing"""
        import asyncio

        from app import main

        monkeypatch.setattr(main.settings, "environment", "production")
        monkeypatch.setattr(main.settings, "cors_origins", "")
        monkeypatch.setattr(main, "apply_migrations", lambda: None)

        async def start():
            async with main.lifespan(main.app):
                pass

        with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
            asyncio.run(start())

    def test_development_only_warns(self, monkeypatch, caplog):
        """TC-SVC-CFG-044 | AC-20.1 | T01 | boundary | outside production a missing setting is logged, and startup continues"""
        import asyncio

        from app import main

        monkeypatch.setattr(main.settings, "environment", "development")
        monkeypatch.setattr(main.settings, "cors_origins", "")
        monkeypatch.setattr(main, "apply_migrations", lambda: None)
        monkeypatch.setattr(main, "cleanup_loop", lambda: asyncio.sleep(0))
        monkeypatch.setattr(main, "maintenance_loop", lambda: asyncio.sleep(0))

        async def start():
            async with main.lifespan(main.app):
                pass

        with caplog.at_level("ERROR"):
            asyncio.run(start())
        assert any("CORS_ORIGINS" in record.getMessage() for record in caplog.records)


class TestServerErrorBody:
    def test_a_crash_answers_with_a_reference_and_no_detail(self):
        """TC-SVC-CFG-045 | AC-18.1 | T16 | business | an unhandled error is a generic 500 that carries the request id as ref; the exception text never leaves the server"""
        from fastapi.testclient import TestClient

        from app import main

        @main.app.get("/api/__boom")
        def boom():
            raise RuntimeError("secret internal detail")

        try:
            response = TestClient(main.app, raise_server_exceptions=False).get("/api/__boom", headers={"X-Request-ID": "abc123"})
        finally:
            main.app.router.routes = [r for r in main.app.router.routes if getattr(r, "path", "") != "/api/__boom"]

        body = response.json()
        assert response.status_code == 500
        assert "secret internal detail" not in response.text
        assert body["ref"] == "abc123" and response.headers["X-Request-ID"] == "abc123"
