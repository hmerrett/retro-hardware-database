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


def test_donor_migration_round_trip_preserves_foundation_data(scratch_db_url):
    _assert_alembic(
        _alembic(scratch_db_url, "upgrade", "0035_inventory_storage"),
        "upgrade 0035_inventory_storage",
    )
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO parts (asset_id, computer_id, parent_id, type, model) "
            "VALUES ('DONOR-BASE', NULL, NULL, 'motherboard', 'Existing board')"
        ))
        conn.execute(text(
            "INSERT INTO inventory_lot (quantity, `condition`) "
            "VALUES (1, 'pulled')"
        ))
        lot_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
        conn.execute(text(
            "INSERT INTO inventory_item (lot_id, item_code) "
            "VALUES (:lot_id, 'EXISTING-ITEM')"
        ), {"lot_id": lot_id})

    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "upgrade head")
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT board_role FROM parts WHERE asset_id = 'DONOR-BASE'"
        )).scalar_one() == "normal"
        assert conn.execute(text(
            "SELECT lifecycle_status FROM inventory_item "
            "WHERE item_code = 'EXISTING-ITEM'"
        )).scalar_one() == "inventory"
        assert conn.execute(text("SELECT COUNT(*) FROM component_event")).scalar_one() == 0

    _assert_alembic(
        _alembic(scratch_db_url, "downgrade", "0035_inventory_storage"),
        "downgrade 0035_inventory_storage",
    )
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT model FROM parts WHERE asset_id = 'DONOR-BASE'"
        )).scalar_one() == "Existing board"
        assert conn.execute(text(
            "SELECT COUNT(*) FROM inventory_item WHERE item_code = 'EXISTING-ITEM'"
        )).scalar_one() == 1

    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "re-upgrade head")
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT board_role FROM parts WHERE asset_id = 'DONOR-BASE'"
        )).scalar_one() == "normal"
        assert conn.execute(text(
            "SELECT lifecycle_status FROM inventory_item "
            "WHERE item_code = 'EXISTING-ITEM'"
        )).scalar_one() == "inventory"
        assert conn.execute(text("SELECT COUNT(*) FROM component_event")).scalar_one() == 0
    engine.dispose()


def test_compatibility_migration_round_trip_preserves_existing_data(scratch_db_url):
    _assert_alembic(
        _alembic(scratch_db_url, "upgrade", "0036_donor_workflow"),
        "upgrade 0036_donor_workflow",
    )
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO computers (asset_id, name) VALUES ('COMPAT-COMP', 'Existing')"
        ))
        conn.execute(text(
            "INSERT INTO parts (asset_id, computer_id, parent_id, type, board_role) "
            "VALUES ('COMPAT-PART', 'COMPAT-COMP', NULL, 'motherboard', 'repair')"
        ))
        conn.execute(text(
            "INSERT INTO bom_component (generic_name) VALUES ('Existing component')"
        ))
        component_id = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
        conn.execute(text(
            "INSERT INTO bom_part_number (component_id, manufacturer, part_number) "
            "VALUES (:component_id, 'Existing maker', 'EXISTING-PN')"
        ), {"component_id": component_id})

    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "upgrade head")
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT board_role FROM parts WHERE asset_id = 'COMPAT-PART'"
        )).scalar_one() == "repair"
        assert conn.execute(text(
            "SELECT part_number FROM bom_part_number WHERE part_number = 'EXISTING-PN'"
        )).scalar_one() == "EXISTING-PN"
        assert conn.execute(text(
            "SELECT COUNT(*) FROM component_compatibility"
        )).scalar_one() == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM component_production_use"
        )).scalar_one() == 0

    _assert_alembic(
        _alembic(scratch_db_url, "downgrade", "0036_donor_workflow"),
        "downgrade 0036_donor_workflow",
    )
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM parts WHERE asset_id = 'COMPAT-PART'"
        )).scalar_one() == 1
        assert conn.execute(text(
            "SELECT COUNT(*) FROM bom_part_number WHERE part_number = 'EXISTING-PN'"
        )).scalar_one() == 1

    _assert_alembic(_alembic(scratch_db_url, "upgrade", "head"), "re-upgrade head")
    with engine.connect() as conn:
        assert conn.execute(text(
            "SELECT COUNT(*) FROM component_compatibility"
        )).scalar_one() == 0
    engine.dispose()
