"""Migration h4e2c9f63b17: every existing notification gets expires_at = created_at + 30 days."""

from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_upgrade_gives_existing_notifications_a_30_day_expiry(monkeypatch, tmp_path):
    """TC-SVC-NOT-001 | AC-19.4 | T03 | business | old rows get created_at + 30 days, so a 40-day-old one is already expired while a recent one lives on"""
    monkeypatch.chdir(BACKEND_DIR)
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    old, recent = datetime.utcnow() - timedelta(days=40), datetime.utcnow() - timedelta(days=5)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "f2c9a6b17d34")
            connection.execute(text(
                "INSERT INTO users (id, name, email, phone, password_hash, role, is_admin, is_active, created_at) "
                "VALUES (1, 'U', 'u@gmail.com', '9876543210', 'x', 'SE', 0, 1, '2026-01-01')"
            ))
            for row_id, created in ((1, old), (2, recent)):
                connection.execute(
                    text("INSERT INTO notifications (id, user_id, kind, message, created_at) VALUES (:id, 1, 'enquiry_received', 'm', :at)"),
                    {"id": row_id, "at": created.isoformat(sep=" ")},
                )
            command.upgrade(config, "h4e2c9f63b17")
            rows = connection.execute(text("SELECT id, created_at, expires_at FROM notifications ORDER BY id")).fetchall()

        def parse(value):
            return datetime.fromisoformat(str(value))

        assert [parse(r[2]) - parse(r[1]) for r in rows] == [timedelta(days=30), timedelta(days=30)]
        assert parse(rows[0][2]) < datetime.utcnow() < parse(rows[1][2])
    finally:
        engine.dispose()
