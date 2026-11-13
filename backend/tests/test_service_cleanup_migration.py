"""Service tests: expiry cleanup (T15) and startup migrations (T03)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import Interest, Listing, ListingImage, Need
from app.services import migration
from app.services.cleanup import cleanup_expired_data
from app.utils.enums import InterestStatus, ListingStatus, NeedStatus
from tests.conftest import make_user
from tests.support import add_image, add_interest, add_listing, add_need

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture()
def deleted_assets(monkeypatch):
    """Capture Cloudinary deletions made by the cleanup service."""
    deleted: list[str] = []
    monkeypatch.setattr("app.services.cleanup.delete_image", deleted.append)
    return deleted


class TestCleanupService:
    def test_expired_listing_and_images_are_removed(self, db_session, deleted_assets):
        """TC-SVC-CLN-001 | AC-14.1 | T15 | positive | an expired listing, its image rows and its Cloudinary assets are deleted"""
        owner = make_user(db_session)
        expired = add_listing(db_session, owner, expires_at=datetime.utcnow() - timedelta(seconds=1))
        add_image(db_session, expired, public_id="pid-1")
        add_image(db_session, expired, public_id="pid-2")

        cleanup_expired_data()

        db_session.expire_all()
        assert _count(db_session, Listing) == 0
        assert _count(db_session, ListingImage) == 0
        assert sorted(deleted_assets) == ["pid-1", "pid-2"]

    def test_unexpired_listing_is_kept(self, db_session, deleted_assets):
        """TC-SVC-CLN-002 | AC-14.1 | T15 | boundary | a listing expiring one hour from now is untouched"""
        owner = make_user(db_session)
        keep = add_listing(db_session, owner, expires_at=datetime.utcnow() + timedelta(hours=1))
        add_image(db_session, keep, public_id="keep-me")

        cleanup_expired_data()

        db_session.expire_all()
        assert _count(db_session, Listing) == 1
        assert _count(db_session, ListingImage) == 1
        assert deleted_assets == []

    def test_expired_need_is_removed_and_active_need_kept(self, db_session, deleted_assets):
        """TC-SVC-CLN-003 | AC-14.1 | T15 | positive | expired needs are deleted, current needs are kept"""
        user = make_user(db_session)
        add_need(db_session, user, title="old", expires_at=datetime.utcnow() - timedelta(minutes=5))
        add_need(db_session, user, title="fresh", expires_at=datetime.utcnow() + timedelta(days=1))

        cleanup_expired_data()

        db_session.expire_all()
        titles = [n.title for n in db_session.scalars(select(Need)).all()]
        assert titles == ["fresh"]

    def test_expiry_is_independent_of_status(self, db_session, deleted_assets):
        """TC-SVC-CLN-004 | AC-14.1 | T15 | business | an expired SOLD listing and a CLOSED need are removed too"""
        user = make_user(db_session)
        past = datetime.utcnow() - timedelta(days=1)
        add_listing(db_session, user, status=ListingStatus.SOLD, expires_at=past)
        add_need(db_session, user, status=NeedStatus.CLOSED, expires_at=past)

        cleanup_expired_data()

        db_session.expire_all()
        assert _count(db_session, Listing) == 0
        assert _count(db_session, Need) == 0

    def test_cloudinary_failure_does_not_stop_cleanup(self, db_session, monkeypatch):
        """TC-SVC-CLN-005 | AC-14.2 | T15 | negative | a failing asset deletion is logged and the rows are still removed"""
        owner = make_user(db_session)
        expired = add_listing(db_session, owner, expires_at=datetime.utcnow() - timedelta(days=1))
        add_image(db_session, expired, public_id="bad")
        add_image(db_session, expired, public_id="good")
        attempted: list[str] = []

        def flaky_delete(public_id):
            attempted.append(public_id)
            if public_id == "bad":
                raise RuntimeError("cloudinary down")

        monkeypatch.setattr("app.services.cleanup.delete_image", flaky_delete)

        cleanup_expired_data()

        db_session.expire_all()
        assert sorted(attempted) == ["bad", "good"]
        assert _count(db_session, Listing) == 0

    def test_deleting_expired_listing_removes_its_interests(self, db_session, deleted_assets):
        """TC-SVC-CLN-006 | AC-14.1, AC-19.3 | T15 | business | interests on an expired listing disappear with it"""
        owner, buyer = make_user(db_session), make_user(db_session)
        expired = add_listing(db_session, owner, expires_at=datetime.utcnow() - timedelta(days=1))
        add_interest(db_session, expired, buyer, InterestStatus.ACCEPTED)

        cleanup_expired_data()

        db_session.expire_all()
        assert _count(db_session, Interest) == 0

    def test_cleanup_with_nothing_expired_is_a_noop(self, db_session, deleted_assets):
        """TC-SVC-CLN-007 | AC-14.1 | T15 | boundary | running on an empty/current database changes nothing"""
        owner = make_user(db_session)
        add_listing(db_session, owner)
        add_need(db_session, owner)

        cleanup_expired_data()

        db_session.expire_all()
        assert _count(db_session, Listing) == 1
        assert _count(db_session, Need) == 1


class TestMigrationService:
    @pytest.fixture()
    def migrate_in(self, monkeypatch, tmp_path):
        """Point the migration service at a fresh SQLite file and run from backend/."""
        monkeypatch.chdir(BACKEND_DIR)  # alembic.ini is resolved relative to cwd
        url = f"sqlite:///{tmp_path / 'migrated.db'}"
        monkeypatch.setattr(settings, "database_url_unpooled", url)
        return url

    def test_upgrade_builds_the_full_schema_at_head(self, migrate_in):
        """TC-SVC-MIG-001 | AC-19.4 | T03 | positive | apply_migrations on an empty DB creates all six tables at the head revision"""
        migration.apply_migrations()

        engine = create_engine(migrate_in, poolclass=NullPool)
        try:
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as connection:
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        finally:
            engine.dispose()

        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert {"users", "listings", "listing_images", "interests", "needs", "audit_logs"} <= tables
        assert version == head

    def test_upgrade_is_idempotent(self, migrate_in):
        """TC-SVC-MIG-002 | AC-19.4 | T03 | boundary | running migrations twice succeeds and leaves the same revision"""
        migration.apply_migrations()
        migration.apply_migrations()

        engine = create_engine(migrate_in, poolclass=NullPool)
        try:
            with engine.connect() as connection:
                rows = connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
        finally:
            engine.dispose()
        assert rows == 1

    def test_unpooled_url_is_preferred(self, monkeypatch, tmp_path):
        """TC-SVC-MIG-003 | AC-19.4 | T03 | business | migrations use DATABASE_URL_UNPOOLED when it is set"""
        seen = {}
        unpooled = f"sqlite:///{tmp_path / 'unpooled.db'}"

        def fake_upgrade(config, revision):
            seen["url"] = config.get_main_option("sqlalchemy.url")
            seen["revision"] = revision

        monkeypatch.setattr(migration.command, "upgrade", fake_upgrade)
        monkeypatch.setattr(settings, "database_url_unpooled", unpooled)

        migration.apply_migrations()

        assert seen == {"url": unpooled, "revision": "head"}

    def test_failure_is_fatal_in_production(self, monkeypatch):
        """TC-SVC-MIG-004 | AC-19.5 | T03 | negative | in production a failed migration re-raises so the instance does not start"""
        def boom(config, revision):
            raise RuntimeError("migration failed")

        monkeypatch.setattr(migration.command, "upgrade", boom)
        monkeypatch.setattr(settings, "environment", "production")

        with pytest.raises(RuntimeError, match="migration failed"):
            migration.apply_migrations()

    def test_failure_is_tolerated_outside_production(self, monkeypatch):
        """TC-SVC-MIG-005 | AC-19.5 | T03 | business | in development a failed migration is logged and startup continues"""
        def boom(config, revision):
            raise RuntimeError("migration failed")

        monkeypatch.setattr(migration.command, "upgrade", boom)
        monkeypatch.setattr(settings, "environment", "development")

        assert migration.apply_migrations() is None

    def test_production_check_is_case_insensitive(self, monkeypatch):
        """TC-SVC-MIG-006 | AC-19.5 | T03 | boundary | ENVIRONMENT='Production' is still treated as production"""
        def boom(config, revision):
            raise RuntimeError("migration failed")

        monkeypatch.setattr(migration.command, "upgrade", boom)
        monkeypatch.setattr(settings, "environment", "Production")

        with pytest.raises(RuntimeError):
            migration.apply_migrations()
