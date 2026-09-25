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
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
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
        ["alembic", *args],
        cwd=API_DIR,
        capture_output=True,
        text=True,
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
        conn.execute(text("INSERT INTO computers (asset_id, serial) VALUES ('RH-OLD2', 'SN-KEPT')"))
        conn.execute(text("INSERT INTO parts (asset_id, parent_id) VALUES ('RH-OLD3', NULL)"))

    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"

    with engine.begin() as conn:
        rows = dict(
            conn.execute(
                text(
                    "SELECT asset_id, serial FROM computers UNION ALL "
                    "SELECT asset_id, serial FROM parts"
                )
            ).all()
        )
        assert rows == {"RH-OLD1": "", "RH-OLD2": "SN-KEPT", "RH-OLD3": ""}

        # And the column can no longer hold the state that caused the bug.
        for table in ("computers", "parts"):
            nullable = conn.execute(
                text(
                    "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE "
                    "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND "
                    "COLUMN_NAME = 'serial'"
                ),
                {"t": table},
            ).scalar_one()
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
            nullable = conn.execute(
                text(
                    "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE "
                    "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND "
                    "COLUMN_NAME = 'serial'"
                ),
                {"t": table},
            ).scalar_one()
            assert nullable == "YES", f"{table}.serial did not go back to nullable"
    engine.dispose()


# The revision 0035 builds on, by its `revision` string rather than its file name.
BEFORE_PUBLIC_FILES = "0034_serial_not_null"


def test_files_already_on_file_stay_public_across_0035(scratch_db_url):
    """0035 keeps what is already there published, and starts everything after it
    private.

    Uploads were public from 0020 until this migration, and the collection's
    drivers and manuals are linked from item pages and from printed QR labels. A
    column defaulting to 0 with no backfill would have taken every one of them off
    the site on the deployment that ran it -- so the rows that predate the flag are
    published, and only new uploads inherit the default. Both halves are asserted
    here because either alone is the wrong feature.
    """
    up = _alembic(scratch_db_url, "upgrade", BEFORE_PUBLIC_FILES)
    assert up.returncode == 0, f"upgrade to 0034 failed:\n{up.stderr}"

    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO files (stored, filename, size) VALUES ('abc123.zip', 'tvga.zip', 12)")
        )

    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"

    with engine.begin() as conn:
        assert (
            conn.execute(text("SELECT public FROM files WHERE filename = 'tvga.zip'")).scalar_one()
            == 1
        )
        # And the column an upload written after the migration lands in.
        conn.execute(
            text(
                "INSERT INTO files (stored, filename, size) VALUES "
                "('def456.pdf', 'receipt.pdf', 34)"
            )
        )
        assert (
            conn.execute(
                text("SELECT public FROM files WHERE filename = 'receipt.pdf'")
            ).scalar_one()
            == 0
        )
    engine.dispose()


def test_the_public_flag_can_be_downgraded(scratch_db_url):
    """Going back drops the column, which is the state where every file is public
    again -- honest rather than safe, and the reason the migration says so."""
    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    down = _alembic(scratch_db_url, "downgrade", BEFORE_PUBLIC_FILES)
    assert down.returncode == 0, f"downgrade from 0035 failed:\n{down.stderr}"

    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE "
                    "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'files' AND "
                    "COLUMN_NAME = 'public'"
                )
            ).scalar_one()
            == 0
        )
    engine.dispose()


BEFORE_FILE_LINKS = "0038_items_may_be_for_sale"
# Where 0039 left things. The two tests below read the tables it made, which
# 0044 retired, so they stop here rather than at head.
FILE_LINKS = "0039_a_file_says_what_it_is_for"


def test_what_the_matcher_found_survives_0039(scratch_db_url):
    """0039 stops a file being matched to an item by name and starts it being
    attached to one, and runs the old matcher once to write down what it found.

    The point of the backfill is that the day of the change is quiet: a register
    whose driver disks appear on the right cards on Monday has them on the right
    cards on Tuesday. So the four shapes it has to get right are asserted here --
    a tag covering two identical cards, a tag that is an asset id, a tag reaching
    something with no model to name, and a tag reaching nothing at all.

    It is faithful rather than clever on purpose (ADR-0006): what the matcher got
    wrong is preserved too, because a backfill that quietly corrected the mistakes
    would be one nobody could check afterwards.
    """
    up = _alembic(scratch_db_url, "upgrade", BEFORE_FILE_LINKS)
    assert up.returncode == 0, f"upgrade to 0038 failed:\n{up.stderr}"

    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        for aid, maker, model in (
            ("RH-0001", "Trident", "TVGA8900"),
            ("RH-0002", "Trident", "TVGA8900"),
            ("RH-0003", "Tseng", "ET4000"),
            ("RH-0004", "", ""),
        ):
            conn.execute(
                text(
                    "INSERT INTO parts (asset_id, type, manufacturer, model, name, "
                    "disposed_note, computer_id, parent_id) "
                    "VALUES (:a, 'video', :m, :d, '', '', NULL, NULL)"
                ),
                {"a": aid, "m": maker, "d": model},
            )
        for fid, (stored, name) in enumerate(
            (
                ("a.zip", "tvga.zip"),
                ("b.pdf", "receipt.pdf"),
                ("c.zip", "nothing.zip"),
                ("d.zip", "unnamed.zip"),
            ),
            start=1,
        ):
            conn.execute(
                text("INSERT INTO files (id, stored, filename, size) VALUES (:i, :s, :f, 10)"),
                {"i": fid, "s": stored, "f": name},
            )
        for fid, tag in (
            (1, "Trident TVGA8900"),
            (2, "RH-0001"),
            (3, "Nothing At All"),
            (4, "RH-0004"),
        ):
            conn.execute(
                text("INSERT INTO file_tag (file_id, tag, fold) VALUES (:i, :t, :f)"),
                {"i": fid, "t": tag, "f": "".join(tag.split()).lower()},
            )

    up = _alembic(scratch_db_url, "upgrade", FILE_LINKS)
    assert up.returncode == 0, f"upgrade to 0039 failed:\n{up.stderr}"

    with engine.begin() as conn:
        models = set(conn.execute(text("SELECT file_id, kind, model_key FROM file_model")).all())
        assets = set(conn.execute(text("SELECT file_id, asset_id FROM file_asset")).all())

    # One link, not two: the tag reached two identical cards and they are one model,
    # which is the whole reason a model link exists.
    assert models == {(1, "named", "trident|tvga8900")}
    # A tag that was an asset id meant that one unit, and still does. The card with
    # nothing to call it has no model to be one of, so its file is about the unit.
    assert assets == {(2, "RH-0001"), (4, "RH-0004")}
    engine.dispose()


def test_a_file_the_matcher_reached_nothing_with_is_left_unfiled(scratch_db_url):
    """Unfiled is a state and not a loss: the bytes are untouched and the files page
    says so. The alternative -- guessing at what a tag nobody can match was meant to
    cover -- is the sort of kindness that loses a file."""
    up = _alembic(scratch_db_url, "upgrade", BEFORE_FILE_LINKS)
    assert up.returncode == 0, f"upgrade to 0038 failed:\n{up.stderr}"
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO parts (asset_id, type, manufacturer, model, "
                "name, disposed_note, computer_id, parent_id) VALUES "
                "('RH-0009', 'video', 'Tseng', 'ET4000', '', '', NULL, NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO files (id, stored, filename, size) "
                "VALUES (7, 'x.zip', 'orphan.zip', 10)"
            )
        )
        conn.execute(
            text("INSERT INTO file_tag (file_id, tag, fold) VALUES (7, 'Whatever', 'whatever')")
        )

    up = _alembic(scratch_db_url, "upgrade", FILE_LINKS)
    assert up.returncode == 0, f"upgrade to 0039 failed:\n{up.stderr}"
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM file_model")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM file_asset")).scalar_one() == 0
        assert (
            conn.execute(text("SELECT filename FROM files WHERE id = 7")).scalar_one()
            == "orphan.zip"
        )
    engine.dispose()


BEFORE_ID_LINKS = "0043_where_a_thing_is_kept"


def _tables(conn):
    return {row[0] for row in conn.execute(text("SHOW TABLES")).all()}


def _before_id_links(scratch_db_url):
    """A database as 0043 left it: two Trident cards spelled two ways, one of them
    disposed of, a Tseng card, and two Spectrums the catalogue names."""
    up = _alembic(scratch_db_url, "upgrade", BEFORE_ID_LINKS)
    assert up.returncode == 0, f"upgrade to 0043 failed:\n{up.stderr}"
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        for aid, maker, model, gone in (
            ("RH-0001", "Trident", "TVGA8900", 0),
            ("RH-0002", "trident", "TVGA 8900", 1),
            ("RH-0003", "Tseng", "ET4000", 0),
        ):
            conn.execute(
                text(
                    "INSERT INTO parts (asset_id, type, manufacturer, model, name, disposed, "
                    "disposed_note, computer_id, parent_id) "
                    "VALUES (:a, 'video', :m, :d, '', :g, '', NULL, NULL)"
                ),
                {"a": aid, "m": maker, "d": model, "g": gone},
            )
        for aid, maker, model in (
            ("RH-0010", "Sinclair", "ZX Spectrum 48K"),
            ("RH-0011", "sinclair research", "Spectrum"),
        ):
            conn.execute(
                text("INSERT INTO computers (asset_id, manufacturer, model) VALUES (:a, :m, :d)"),
                {"a": aid, "m": maker, "d": model},
            )
            conn.execute(
                text(
                    "INSERT INTO asset_variant (asset_id, model_key, issue, style, region) "
                    "VALUES (:a, 'zx-spectrum-48k', '', '', '')"
                ),
                {"a": aid},
            )
    return engine


def _file(conn, fid, name, note=""):
    conn.execute(
        text("INSERT INTO files (id, stored, filename, size, note) VALUES (:i, :s, :f, 10, :n)"),
        {"i": fid, "s": f"{fid}.bin", "f": name, "n": note},
    )


def _tag(conn, fid, tag):
    conn.execute(
        text("INSERT INTO file_tag (file_id, tag, fold) VALUES (:i, :t, :f)"),
        {"i": fid, "t": tag, "f": "".join(tag.split()).lower()},
    )


def _model_link(conn, fid, kind, key, label):
    conn.execute(
        text("INSERT INTO file_model (file_id, kind, model_key, label) VALUES (:i, :k, :m, :l)"),
        {"i": fid, "k": kind, "m": key, "l": label},
    )


def test_0044_links_every_item_a_model_link_reached(scratch_db_url):
    """ADR-0028. A model link becomes a link to each item that answers to the model
    on the day -- by maker and model folded, or by catalogue key -- held or
    disposed, since a disposed item's page shows its files too. A unit link stays
    as it was, and the two tables that are retired are gone."""
    engine = _before_id_links(scratch_db_url)
    with engine.begin() as conn:
        _file(conn, 1, "tvga.zip")
        _file(conn, 2, "manual.pdf")
        _file(conn, 3, "receipt.pdf")
        _model_link(conn, 1, "named", "trident|tvga8900", "Trident TVGA8900")
        _model_link(conn, 2, "catalogue", "zx-spectrum-48k", "ZX Spectrum 48K")
        conn.execute(text("INSERT INTO file_asset (file_id, asset_id) VALUES (3, 'RH-0003')"))

    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    with engine.begin() as conn:
        links = set(conn.execute(text("SELECT file_id, asset_id FROM file_asset")).all())
        tables = _tables(conn)
    assert links == {
        (1, "RH-0001"),
        (1, "RH-0002"),
        (2, "RH-0010"),
        (2, "RH-0011"),
        (3, "RH-0003"),
    }
    assert "file_model" not in tables and "file_tag" not in tables
    engine.dispose()


def test_0044_keeps_in_the_note_a_tag_that_said_more_than_the_links(scratch_db_url):
    """A tag that only repeated what the file was linked to -- inside a model link's
    label, the way the name matcher read tags, or equal to a linked asset id -- is
    dropped. Any other tag is kept, after whatever the note already said, so a clue
    on a file linked to nothing survives."""
    engine = _before_id_links(scratch_db_url)
    with engine.begin() as conn:
        _file(conn, 1, "tvga.zip")
        _model_link(conn, 1, "named", "trident|tvga8900", "Trident TVGA8900")
        _tag(conn, 1, "Trident TVGA8900")
        _tag(conn, 1, "driver")
        _file(conn, 2, "sbbasic.img", note="the basic disk")
        _model_link(conn, 2, "named", "trident|tvga8900", "Trident TVGA8900 rev B")
        _tag(conn, 2, "Trident TVGA8900")
        _file(conn, 3, "ctcmbbs.img")
        _tag(conn, 3, "Creative Labs Sound Blaster PnP")
        _file(conn, 4, "receipt.pdf")
        conn.execute(text("INSERT INTO file_asset (file_id, asset_id) VALUES (4, 'RH-0003')"))
        _tag(conn, 4, "RH-0003")
        _file(conn, 5, "guide.pdf", note="user guide")
        _tag(conn, 5, "manual")

    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    with engine.begin() as conn:
        notes = dict(conn.execute(text("SELECT id, note FROM files")).all())
    assert notes == {
        1: "driver",
        2: "the basic disk",
        3: "Creative Labs Sound Blaster PnP",
        4: "",
        5: "user guide — manual",
    }
    engine.dispose()


def test_0044_moves_nothing_on_a_register_with_no_files(scratch_db_url):
    engine = _before_id_links(scratch_db_url)
    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM file_asset")).scalar_one() == 0
    engine.dispose()


def test_0044_can_be_downgraded(scratch_db_url):
    """The two tables come back empty, which is the shape 0043 expects, and the links
    stay: a downgraded register offers each file on the items it is linked to."""
    engine = _before_id_links(scratch_db_url)
    with engine.begin() as conn:
        _file(conn, 1, "tvga.zip")
        _model_link(conn, 1, "named", "trident|tvga8900", "Trident TVGA8900")
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    down = _alembic(scratch_db_url, "downgrade", BEFORE_ID_LINKS)
    assert down.returncode == 0, f"downgrade from 0044 failed:\n{down.stderr}"
    with engine.begin() as conn:
        tables = _tables(conn)
        links = set(conn.execute(text("SELECT file_id, asset_id FROM file_asset")).all())
    assert {"file_model", "file_tag"} <= tables
    assert links == {(1, "RH-0001"), (1, "RH-0002")}
    again = _alembic(scratch_db_url, "upgrade", "head")
    assert again.returncode == 0, f"upgrade after downgrade failed:\n{again.stderr}"
    engine.dispose()


BEFORE_ACCOUNTS = "0044_a_file_is_linked_by_id"


def test_0045_makes_the_account_tables_empty(scratch_db_url):
    """Nothing is seeded by the migration: the old single login is read by the app
    at startup, because a migration must not assume what the environment holds any
    more than what the data does (ADR-0002, ADR-0032)."""
    up = _alembic(scratch_db_url, "upgrade", "head")
    assert up.returncode == 0, f"upgrade to head failed:\n{up.stderr}"
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        assert {"users", "memberships", "sessions", "api_tokens"} <= _tables(conn)
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 0
    engine.dispose()


def test_0045_can_be_downgraded_and_upgraded_again(scratch_db_url):
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    down = _alembic(scratch_db_url, "downgrade", BEFORE_ACCOUNTS)
    assert down.returncode == 0, f"downgrade from 0045 failed:\n{down.stderr}"
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        assert not {"users", "memberships", "sessions", "api_tokens"} & _tables(conn)
    engine.dispose()
    again = _alembic(scratch_db_url, "upgrade", "head")
    assert again.returncode == 0, f"upgrade after downgrade failed:\n{again.stderr}"
