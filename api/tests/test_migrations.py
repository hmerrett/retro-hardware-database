"""Migration smoke test against a real MariaDB.

The app and test suite run on MariaDB, whose DDL auto-commits and is not
transactional, so a migration that fails partway leaves half its work applied.
The normal test schema reaches head once per session; these tests additionally
exercise isolated empty databases, migration round trips, and preservation of
pre-feature asset rows -- the documented ``docker compose up`` path.

Skipped unless ``MIGRATION_TEST_DATABASE_URL`` names a MariaDB *server* (URL with
no database, or one whose database is ignored) under an account allowed to create
and drop a scratch database. CI provides one; see the MariaDB CI job.
"""
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

API_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.getenv("MIGRATION_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="set MIGRATION_TEST_DATABASE_URL to a MariaDB server to run migration tests",
)


@pytest.fixture
def scratch_db_url():
    """A freshly created, empty MariaDB database, dropped afterwards."""
    name = f"rhdb_migtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(text(f"CREATE DATABASE `{name}`"))
    try:
        # render_as_string(hide_password=False): str(url) masks the password as
        # "***", which the alembic subprocess would then try to authenticate with.
        yield make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
        admin.dispose()


def test_upgrade_head_on_empty_database(scratch_db_url):
    """A fresh database migrates cleanly to head.

    Regresses the data-in-migrations bug: migrations that INSERT/UPDATE specific
    collection assets used to fail the foreign-key check on an empty database and
    leave a half-applied, non-restartable schema behind.
    """
    env = {**os.environ, "DATABASE_URL": scratch_db_url}
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=API_DIR, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "alembic upgrade head failed on an empty database:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def _alembic(database_url, *args):
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        ["alembic", *args], cwd=API_DIR, env=env,
        capture_output=True, text=True,
    )


def _assert_alembic(result, operation):
    assert result.returncode == 0, (
        f"alembic {operation} failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_bom_migrations_downgrade_and_reupgrade(scratch_db_url):
    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "upgrade head")
    _assert_alembic(
        _alembic(scratch_db_url, "downgrade", "0033_work_project_names"),
        "downgrade 0033_work_project_names",
    )
    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "re-upgrade head")


def test_existing_assets_survive_bom_and_inventory_migrations(scratch_db_url):
    _assert_alembic(
        _alembic(scratch_db_url, "upgrade", "0033_work_project_names"),
        "upgrade 0033_work_project_names",
    )
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO computers (asset_id, name, manufacturer, model) "
            "VALUES ('TEST-COMP', 'Existing computer', 'Example', 'System')"
        ))
        conn.execute(text(
            "INSERT INTO parts (asset_id, computer_id, parent_id, type, "
            "manufacturer, model, name) "
            "VALUES ('TEST-PART', 'TEST-COMP', NULL, 'motherboard', "
            "'Example', 'Board', 'Existing board')"
        ))

    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "upgrade head")

    with engine.connect() as conn:
        computer = conn.execute(text(
            "SELECT name, manufacturer, model FROM computers "
            "WHERE asset_id = 'TEST-COMP'"
        )).one()
        part = conn.execute(text(
            "SELECT computer_id, type, manufacturer, model, name FROM parts "
            "WHERE asset_id = 'TEST-PART'"
        )).one()
        assert tuple(computer) == ("Existing computer", "Example", "System")
        assert tuple(part) == (
            "TEST-COMP", "motherboard", "Example", "Board", "Existing board")
        assert conn.execute(text("SELECT COUNT(*) FROM part_bom")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM inventory_lot")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM storage_location")).scalar_one() == 0
    engine.dispose()
