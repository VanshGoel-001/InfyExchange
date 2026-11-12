import logging
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.config import settings

logger = logging.getLogger(__name__)


def apply_migrations() -> None:
    """Apply any pending Alembic database migrations programmatically on startup."""
    try:
        migration_database_url = (
            settings.database_url_unpooled or settings.database_url
        )
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", migration_database_url)
        alembic_cfg.attributes["configure_logger"] = False
        logger.info("Database migrations starting")
        engine = create_engine(migration_database_url, poolclass=NullPool)
        try:
            with engine.begin() as connection:
                if connection.dialect.name == "postgresql":
                    connection.execute(
                        text("SELECT pg_advisory_xact_lock(:lock_id)"),
                        {"lock_id": 74193820416},
                    )
                alembic_cfg.attributes["connection"] = connection
                command.upgrade(alembic_cfg, "head")
        finally:
            engine.dispose()
        logger.info("Database migrations applied")
    except Exception:
        # Serving an un-migrated schema would fail on every request, so refuse
        # to start in production. Development stays lenient to allow hacking
        # without a reachable database.
        logger.exception("Database migrations failed")
        if settings.environment.lower() == "production":
            raise
