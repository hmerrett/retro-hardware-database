"""Migration smoke test against a real MariaDB.

The app runs on MariaDB, whose DDL auto-commits and is not transactional, so a
migration that fails partway leaves half its work applied. The rest of the suite
builds the schema from the models on SQLite and never exercises the migration
path, so a migration that cannot run from empty to head slips through CI. This
test closes that gap: it runs ``alembic upgrade head`` against a throwaway
MariaDB database and asserts it reaches head -- the documented
``docker compose up`` path.

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


# The revision 0034 builds on. Alembic identifies a migration by its `revision`
# string, which is not the file name.
BEFORE_SERIAL_FIX = "0033_work_project_names"


def _alembic(url, *args):
    """Run the alembic CLI against `url` and return the completed process."""
    return subprocess.run(
        ["alembic", *args], cwd=API_DIR, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": url},
    )


def test_serials_left_null_before_0034_are_backfilled(scratch_db_url):
    """0034 settles an unrecorded serial on "" for rows that predate it.

    0028 added the column nullable and backfilled nothing, so every row already in
    a collection got NULL while every row written since got the model's "". The
    API promised a string and a NULL row 500'd the whole list. Upgrading has to
    bring the old rows into line, not just stop new ones happening.
    """
    up = _alembic(scratch_db_url, "upgrade", BEFORE_SERIAL_FIX)
    assert up.returncode == 0, f"upgrade to 0033 failed:\n{up.stderr}"

    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        # Bare rows, which is what a collection that ran 0028 was left holding:
        # every column defaulted and `serial` therefore NULL. parent_id is named
        # only because the column carries a stray DEFAULT '' that its own foreign
        # key then rejects -- unrelated to this migration, and not this test's
        # business to trip over.
        conn.execute(text("INSERT INTO computers (asset_id) VALUES ('RH-OLD1')"))
        conn.execute(text("INSERT INTO computers (asset_id, serial) VALUES "
                          "('RH-OLD2', 'SN-KEPT')"))
        conn.execute(text("INSERT INTO parts (asset_id, parent_id) VALUES "
                          "('RH-OLD3', NULL)"))

    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"

    with engine.begin() as conn:
        rows = dict(conn.execute(text(
            "SELECT asset_id, serial FROM computers UNION ALL "
            "SELECT asset_id, serial FROM parts")).all())
        assert rows == {"RH-OLD1": "", "RH-OLD2": "SN-KEPT", "RH-OLD3": ""}

        # And the column can no longer hold the state that caused the bug.
        for table in ("computers", "parts"):
            nullable = conn.execute(text(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE "
                "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND "
                "COLUMN_NAME = 'serial'"), {"t": table}).scalar_one()
            assert nullable == "NO", f"{table}.serial is still nullable"
    engine.dispose()


def test_the_serial_backfill_can_be_downgraded(scratch_db_url):
    """0034's downgrade puts the column back as 0028 left it. It cannot know which
    rows were NULL -- that is gone the moment they are written -- so it restores
    the nullability and leaves the values alone, which is the honest half."""
    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    down = _alembic(scratch_db_url, "downgrade", BEFORE_SERIAL_FIX)
    assert down.returncode == 0, f"downgrade from 0034 failed:\n{down.stderr}"

    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        for table in ("computers", "parts"):
            nullable = conn.execute(text(
                "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE "
                "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND "
                "COLUMN_NAME = 'serial'"), {"t": table}).scalar_one()
            assert nullable == "YES", f"{table}.serial did not go back to nullable"
    engine.dispose()
