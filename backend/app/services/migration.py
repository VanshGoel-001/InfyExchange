import logging
from alembic import command
from alembic.config import Config
from app.config import settings

logger = logging.getLogger(__name__)


def apply_migrations() -> None:
    """Apply any pending Alembic database migrations programmatically on startup."""
    try:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully.")
    except Exception as exc:
        # Serving an un-migrated schema would fail on every request, so refuse
        # to start in production. Development stays lenient to allow hacking
        # without a reachable database.
        logger.error(f"Failed to apply database migrations: {exc}")
        if settings.environment.lower() == "production":
            raise
