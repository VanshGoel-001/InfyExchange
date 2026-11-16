"""Migration e7a3c1d94b52: pickup areas and the conversion of old free-text locations."""

import importlib.util
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "pickup_area_migration", BACKEND_DIR / "alembic" / "versions" / "e7a3c1d94b52_pickup_areas.py"
)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.mark.parametrize(
    "text_in, expected",
    [
        ("ECC87", ("ECC", 87)),
        ("ECC 92", ("ECC", 92)),
        ("ecc-87", ("ECC", 87)),
        ("ECC - 5", ("ECC", 5)),
        ("ECC Block 12", ("ECC", 12)),
        ("ECC", ("ECC", None)),
        ("ECC 150", ("ECC", None)),
        ("ECC 0", ("ECC", None)),
        ("GEC 1", ("GEC 1", None)),
        ("gec2", ("GEC 2", None)),
        ("GEC", ("Other", None)),
        ("Recreational Center, ECC 86, GEC 2", ("Recreational Center", None)),
        ("near Food Court", ("Food Court", None)),
        ("Main Gate", ("Other", None)),
        ("eccentric place", ("Other", None)),
        ("", ("Other", None)),
    ],
)
def test_old_free_text_is_converted(text_in, expected):
    """TC-SVC-PKA-001 | AC-04.3 | T03 | boundary | legacy location text maps to an area and block; unknown text becomes Other"""
    assert migration.parse_legacy_location(text_in) == expected


def test_display_text():
    """TC-SVC-PKA-002 | AC-04.3 | T03 | positive | 'ECC' + 87 displays as 'ECC - 87'; no block shows the area alone"""
    assert migration.display_location("ECC", 87) == "ECC - 87"
    assert migration.display_location("Other", None) == "Other"


def test_upgrade_converts_existing_listings(monkeypatch, tmp_path):
    """TC-SVC-PKA-003 | AC-04.3, AC-19.4 | T03 | business | upgrading a database that has old listings seeds the areas and converts each listing, keeping the text column in step"""
    monkeypatch.chdir(BACKEND_DIR)
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "d5b2e9a14c70")
            connection.execute(text(
                "INSERT INTO users (id, name, email, phone, password_hash, role, is_admin, is_active, created_at) "
                "VALUES (1, 'U', 'u@gmail.com', '9876543210', 'x', 'SE', 0, 1, '2026-01-01')"
            ))
            for position, location in enumerate(["ECC87", "ECC 92", "Main Gate", "GEC 2"], start=1):
                connection.execute(
                    text(
                        "INSERT INTO listings (id, owner_id, title, category, listing_type, price, condition, "
                        "location, description, status, created_at, expires_at) VALUES "
                        "(:id, 1, 't', 'OTHER', 'SELL', 1, 'GOOD', :loc, 'd', 'ACTIVE', '2026-01-01', '2027-01-01')"
                    ),
                    {"id": position, "loc": location},
                )
            command.upgrade(config, "e7a3c1d94b52")
            rows = connection.execute(text(
                "SELECT l.location, a.name, l.block_no FROM listings l "
                "JOIN pickup_areas a ON a.id = l.pickup_area_id ORDER BY l.id"
            )).fetchall()
            names = connection.execute(text("SELECT name FROM pickup_areas ORDER BY sort_order")).scalars().all()
        assert names == ["ECC", "GEC 1", "GEC 2", "Recreational Center", "Food Court", "Other"]
        assert [tuple(r) for r in rows] == [
            ("ECC - 87", "ECC", 87),
            ("ECC - 92", "ECC", 92),
            ("Other", "Other", None),
            ("GEC 2", "GEC 2", None),
        ]
    finally:
        engine.dispose()
