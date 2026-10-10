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


# --- 0046: a location is a record (ADR-0034) ----------------------------------

BEFORE_LOCATION_RECORDS = "0045_accounts"
# Upgraded to 0046 and no further: 0047 folds these columns into the register.
LOCATION_RECORDS = "0046_a_location_is_a_record"


def _typed_locations(url):
    """A register at 0045 that keeps its locations as text, the way every
    installation before the change does: two machines in the loft spelt two ways,
    a part in a crate, a part with nothing written down, and a crate nothing is in
    any more that the register was remembering by name."""
    up = _alembic(url, "upgrade", BEFORE_LOCATION_RECORDS)
    assert up.returncode == 0, f"upgrade to 0045 failed:\n{up.stderr}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for aid, where in (("RH-0001", "Loft"), ("RH-0002", "loft"), ("RH-0003", "Loft ")):
            conn.execute(
                text("INSERT INTO computers (asset_id, location) VALUES (:a, :w)"),
                {"a": aid, "w": where},
            )
        conn.execute(
            text(
                "INSERT INTO parts (asset_id, parent_id, location) VALUES "
                "('RH-0004', NULL, 'Garage shelf B'), ('RH-0005', NULL, '')"
            )
        )
        conn.execute(
            text("INSERT INTO location (name, used_at) VALUES ('Old shed', NULL), ('Loft', NULL)")
        )
    return engine


def _places(conn):
    """{name: (kind, parent)} for every location the register now holds."""
    return {
        name: (kind, parent)
        for name, kind, parent in conn.execute(
            text("SELECT name, kind, parent_id FROM locations")
        ).all()
    }


def test_0046_makes_a_location_of_every_spelling_typed(scratch_db_url):
    """Each one named as it was typed, of kind other, at the top level: the upgrade
    cannot know that one crate is inside another, so it does not guess."""
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    with engine.begin() as conn:
        places = _places(conn)
    assert set(places) == {"Loft", "Garage shelf B", "Old shed"}
    assert set(places.values()) == {("other", None)}
    engine.dispose()


def test_0046_folds_spellings_that_differ_only_in_capitals(scratch_db_url):
    """`Loft`, `loft` and `Loft ` were one crate to the old suggestion list, which
    folded case and trimmed, so they are one location here -- under the spelling
    most things were filed with."""
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    with engine.begin() as conn:
        lofts = conn.execute(
            text("SELECT asset_id, name FROM locations WHERE LOWER(name) = 'loft'")
        ).all()
    assert [name for _, name in lofts] == ["Loft"]
    engine.dispose()


def test_0046_puts_each_thing_in_the_location_it_named(scratch_db_url):
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    with engine.begin() as conn:
        tag = dict(conn.execute(text("SELECT name, asset_id FROM locations")).all())
        where = dict(
            conn.execute(
                text(
                    "SELECT asset_id, location_id FROM computers UNION ALL "
                    "SELECT asset_id, location_id FROM parts"
                )
            ).all()
        )
    assert where == {
        "RH-0001": tag["Loft"],
        "RH-0002": tag["Loft"],
        "RH-0003": tag["Loft"],
        "RH-0004": tag["Garage shelf B"],
        "RH-0005": None,
    }
    engine.dispose()


def test_0046_draws_the_new_tags_from_the_registers_pool(scratch_db_url):
    """A location is in the register, so its tag is one nothing else holds, in the
    form every other new tag takes (ADR-0007, ADR-0034)."""
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    with engine.begin() as conn:
        tags = [t for (t,) in conn.execute(text("SELECT asset_id FROM locations")).all()]
        items = {
            t
            for (t,) in conn.execute(
                text(
                    "SELECT asset_id FROM computers UNION SELECT asset_id FROM parts "
                    "UNION SELECT asset_id FROM projects"
                )
            ).all()
        }
    import re

    assert all(re.fullmatch(r"RH-[0-9A-HJKMNP-Z]{4}", t) for t in tags), tags
    assert not set(tags) & items
    assert len(set(tags)) == len(tags)
    engine.dispose()


def test_0046_takes_the_text_and_the_remembered_list_away(scratch_db_url):
    """Nothing is kept twice: the text is now the location, and an emptied crate is
    a location that stays, so the list that remembered it has nothing left to do."""
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    with engine.begin() as conn:
        assert "location" not in _tables(conn)
        assert {"locations", "moves", "stock_checks", "stock_check_scans"} <= _tables(conn)
        for table in ("computers", "parts"):
            columns = {
                c
                for (c,) in conn.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE "
                        "TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                    ),
                    {"t": table},
                ).all()
            }
            assert "location" not in columns and "location_id" in columns, table
    engine.dispose()


def test_0046_on_a_register_with_no_locations_makes_none(scratch_db_url):
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM locations")).scalar_one() == 0
    engine.dispose()


def test_0046_can_be_downgraded_and_upgraded_again(scratch_db_url):
    """Down, each thing gets back the words of where it is -- the path, which for a
    location the upgrade made is the name it was typed as -- and the remembered
    list gets every location's name. Up again, the same locations come back."""
    engine = _typed_locations(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS).returncode == 0
    down = _alembic(scratch_db_url, "downgrade", BEFORE_LOCATION_RECORDS)
    assert down.returncode == 0, f"downgrade from 0046 failed:\n{down.stderr}"
    with engine.begin() as conn:
        where = dict(
            conn.execute(
                text(
                    "SELECT asset_id, location FROM computers UNION ALL "
                    "SELECT asset_id, location FROM parts"
                )
            ).all()
        )
        remembered = {n for (n,) in conn.execute(text("SELECT name FROM location")).all()}
        assert "locations" not in _tables(conn)
    assert where == {
        "RH-0001": "Loft",
        "RH-0002": "Loft",
        "RH-0003": "Loft",
        "RH-0004": "Garage shelf B",
        "RH-0005": "",
    }
    assert remembered == {"Loft", "Garage shelf B", "Old shed"}
    again = _alembic(scratch_db_url, "upgrade", LOCATION_RECORDS)
    assert again.returncode == 0, f"upgrade after downgrade failed:\n{again.stderr}"
    with engine.begin() as conn:
        assert set(_places(conn)) == {"Loft", "Garage shelf B", "Old shed"}
    engine.dispose()


# --- 0047: where a thing is, is one tree (ADR-0036) ----------------------------

BEFORE_ONE_TREE = "0046_a_location_is_a_record"


def _two_answers(url, shown="0"):
    """A register at 0046 holding everything 0047 has to settle: a box on a shelf, a
    machine in the box, a card fitted in it with a drive mounted on the card, a card
    fitted in that machine that was also given a shelf of its own, a part still in
    the collection inside a machine that has been disposed of, a scan that took a
    part out of the machine and put it on the shelf, and a project."""
    up = _alembic(url, "upgrade", BEFORE_ONE_TREE)
    assert up.returncode == 0, f"upgrade to 0046 failed:\n{up.stderr}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO locations (asset_id, name, kind, parent_id, notes, image) VALUES "
                "('RH-SHLF', 'Shelf 2', 'shelf', NULL, '', ''), "
                "('RH-BOXX', 'Box 14', 'box', 'RH-SHLF', '', '')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO computers (asset_id, location_id, disposed, disposed_at, disposed_note) "
                "VALUES ('RH-0001', 'RH-BOXX', 0, NULL, ''), "
                "('RH-0002', NULL, 1, '2025-01-02', 'scrapped')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO parts (asset_id, computer_id, parent_id, location_id, disposed) VALUES "
                "('RH-0003', 'RH-0001', NULL, NULL, 0), "
                "('RH-0004', NULL, 'RH-0003', NULL, 0), "
                "('RH-0005', 'RH-0001', NULL, 'RH-SHLF', 0), "
                "('RH-0006', 'RH-0002', NULL, NULL, 0), "
                "('RH-0007', NULL, NULL, 'RH-SHLF', 0)"
            )
        )
        conn.execute(text("INSERT INTO projects (asset_id, name) VALUES ('RH-0008', 'A plan')"))
        conn.execute(
            text(
                "INSERT INTO users (id, username, password_hash, active, created_at) "
                "VALUES (1, 'owner', 'x', 1, '2026-10-01 10:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO stock_checks (id, user_id, started_at) "
                "VALUES (1, 1, '2026-10-01 10:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO moves (id, asset_id, from_id, from_path, to_id, to_path, moved_at, "
                "who, how) VALUES (1, 'RH-0007', NULL, '', 'RH-SHLF', 'Shelf 2', "
                "'2026-10-01 10:01:00', 'owner', 'scan')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO stock_check_scans (check_id, scanned_at, code, asset_id, at_id, "
                "result, said, move_id, was_computer, was_parent, undone) VALUES "
                "(1, '2026-10-01 10:01:00', 'RH-0007', 'RH-0007', 'RH-SHLF', 'moved', '', 1, "
                "'RH-0001', NULL, 0)"
            )
        )
        conn.execute(
            text("INSERT INTO setting (name, value) VALUES ('public_locations', :v)"), {"v": shown}
        )
    return engine


def _tree(conn):
    """{tag: (what, inside)} for every row of the register."""
    return {
        aid: (what, inside)
        for aid, what, inside in conn.execute(
            text("SELECT asset_id, what, inside_id FROM register")
        ).all()
    }


def test_0047_puts_every_thing_in_the_register(scratch_db_url):
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        what = {aid: w for aid, (w, _in) in _tree(conn).items()}
    assert what == {
        "RH-SHLF": "location",
        "RH-BOXX": "location",
        "RH-0001": "computer",
        "RH-0002": "computer",
        "RH-0003": "part",
        "RH-0004": "part",
        "RH-0005": "part",
        "RH-0006": "part",
        "RH-0007": "part",
        "RH-0008": "project",
    }
    engine.dispose()


def test_0047_gives_each_thing_the_one_link_it_had(scratch_db_url):
    """Mounted on before installed in before kept in: the order the old columns were
    read in. A card with a machine and a shelf keeps the machine."""
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        inside = {aid: i for aid, (_w, i) in _tree(conn).items()}
    assert inside == {
        "RH-SHLF": None,
        "RH-BOXX": "RH-SHLF",
        "RH-0001": "RH-BOXX",
        "RH-0002": None,
        "RH-0003": "RH-0001",
        "RH-0004": "RH-0003",
        "RH-0005": "RH-0001",
        "RH-0006": "RH-0002",
        "RH-0007": "RH-SHLF",
        "RH-0008": None,
    }
    engine.dispose()


def test_0047_says_which_location_a_fitted_part_no_longer_claims(scratch_db_url):
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        said = [
            m
            for (m,) in conn.execute(
                text("SELECT message FROM log_entry WHERE asset_id = 'RH-0005'")
            ).all()
        ]
    assert said == ["stays fitted in RH-0001, and no longer also says it is kept in Shelf 2"]
    engine.dispose()


def test_0047_disposes_of_what_was_left_inside_a_disposed_machine(scratch_db_url):
    """On the machine's date and for its reason, so restoring it brings both back."""
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT disposed, disposed_at, disposed_note FROM parts WHERE asset_id = 'RH-0006'"
            )
        ).one()
        said = conn.execute(
            text("SELECT message FROM log_entry WHERE asset_id = 'RH-0006'")
        ).scalar()
    assert (bool(row[0]), str(row[1]), row[2]) == (True, "2025-01-02", "scrapped")
    assert said == "marked disposed with RH-0002 (2025-01-02): scrapped"
    engine.dispose()


def test_0047_points_a_scans_move_at_the_machine_it_took_a_part_out_of(scratch_db_url):
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        assert conn.execute(text("SELECT from_id FROM moves WHERE id = 1")).scalar() == "RH-0001"
        columns = {row[0] for row in conn.execute(text("SHOW COLUMNS FROM stock_check_scans"))}
    assert not {"was_computer", "was_parent"} & columns
    engine.dispose()


@pytest.mark.parametrize("shown", ["0", "1"])
def test_0047_ticks_every_thing_as_the_switch_says_that_day(scratch_db_url, shown):
    engine = _two_answers(scratch_db_url, shown)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        ticks = {
            v
            for (v,) in conn.execute(
                text(
                    "SELECT location_public FROM computers UNION SELECT location_public FROM parts"
                )
            ).all()
        }
    assert ticks == {int(shown)}
    engine.dispose()


def test_0047_refuses_a_tag_held_twice_before_it_writes_anything(scratch_db_url):
    up = _alembic(scratch_db_url, "upgrade", BEFORE_ONE_TREE)
    assert up.returncode == 0, up.stderr
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO computers (asset_id) VALUES ('RH-0001')"))
        conn.execute(
            text(
                "INSERT INTO parts (asset_id, computer_id, parent_id, location_id) "
                "VALUES ('RH-0001', NULL, NULL, NULL)"
            )
        )
    refused = _alembic(scratch_db_url, "upgrade", "head")
    assert refused.returncode != 0
    assert "RH-0001 (computers, parts)" in refused.stderr
    with engine.begin() as conn:
        assert "register" not in _tables(conn)
    engine.dispose()


def test_0047_can_be_downgraded_and_upgraded_again(scratch_db_url):
    """Down, each thing gets back the column that says what it is in, by what holds
    it; up again, the same tree."""
    engine = _two_answers(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    down = _alembic(scratch_db_url, "downgrade", BEFORE_ONE_TREE)
    assert down.returncode == 0, f"downgrade from 0047 failed:\n{down.stderr}"
    with engine.begin() as conn:
        assert "register" not in _tables(conn)
        parts = {
            aid: (computer, parent, where)
            for aid, computer, parent, where in conn.execute(
                text("SELECT asset_id, computer_id, parent_id, location_id FROM parts")
            ).all()
        }
        boxes = dict(conn.execute(text("SELECT asset_id, parent_id FROM locations")).all())
        machines = dict(conn.execute(text("SELECT asset_id, location_id FROM computers")).all())
    assert parts == {
        "RH-0003": ("RH-0001", None, None),
        "RH-0004": (None, "RH-0003", None),
        "RH-0005": ("RH-0001", None, None),
        "RH-0006": ("RH-0002", None, None),
        "RH-0007": (None, None, "RH-SHLF"),
    }
    assert boxes == {"RH-SHLF": None, "RH-BOXX": "RH-SHLF"}
    assert machines == {"RH-0001": "RH-BOXX", "RH-0002": None}
    again = _alembic(scratch_db_url, "upgrade", "head")
    assert again.returncode == 0, f"upgrade after downgrade failed:\n{again.stderr}"
    with engine.begin() as conn:
        assert _tree(conn)["RH-0004"] == ("part", "RH-0003")
    engine.dispose()


# The revision 0048 builds on.
BEFORE_EACH_LABEL = "0047_where_a_thing_is"


def _settings(conn):
    return dict(conn.execute(text("SELECT name, value FROM setting")).all())


def _choose(scratch_db_url, **chosen):
    """A register at 0047 with these label settings saved, as the old page saved them."""
    up = _alembic(scratch_db_url, "upgrade", BEFORE_EACH_LABEL)
    assert up.returncode == 0, up.stderr
    engine = create_engine(scratch_db_url, future=True)
    with engine.begin() as conn:
        for name, value in chosen.items():
            conn.execute(
                text("INSERT INTO setting (name, value, updated_at) VALUES (:n, :v, NOW())"),
                {"n": name, "v": value},
            )
    return engine


def test_0048_gives_each_label_what_the_two_shared_and_the_first_its_destination(
    scratch_db_url,
):
    engine = _choose(
        scratch_db_url,
        label_codes="code128",
        label_type="look",
        label_destination="agent:workshop-pi",
    )
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        kept = _settings(conn)
        columns = {row[0] for row in conn.execute(text("SHOW COLUMNS FROM print_job"))}
    assert kept == {
        "label_small_codes": "code128",
        "label_full_codes": "code128",
        "label_small_type": "look",
        "label_full_type": "look",
        "label_small_destination": "agent:workshop-pi",
    }
    assert "label" in columns
    engine.dispose()


def test_0048_writes_nothing_where_nothing_was_chosen(scratch_db_url):
    """A key never saved is the default, and the defaults are the labels as they
    always were, so there is nothing to copy."""
    engine = _choose(scratch_db_url)
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        assert _settings(conn) == {}
    engine.dispose()


def test_0048_makes_every_job_already_queued_the_first_labels(scratch_db_url):
    engine = _choose(scratch_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO print_job (agent, kind, asset_id, media, fmt, dpi, copies, state, "
                "created_at) VALUES ('bench', 'part', 'RH-0001', 'niimbot-50x30', 'png', 0, 1, "
                "'queued', NOW())"
            )
        )
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        assert conn.execute(text("SELECT label FROM print_job")).scalar() == "small"
    engine.dispose()


def test_0048_can_be_downgraded_and_upgraded_again(scratch_db_url):
    """Down, both labels share the first one's code and face again, and the first's
    destination is the destination; a code the older version never had goes back to
    its default. Up again, each label has them."""
    engine = _choose(scratch_db_url, label_codes="both", label_destination="bluetooth")
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO setting (name, value, updated_at) VALUES "
                "('label_small_type', 'look', NOW()), ('label_full_name', 'Shelf card', NOW())"
            )
        )
        conn.execute(text("UPDATE setting SET value = 'none' WHERE name = 'label_full_codes'"))
    down = _alembic(scratch_db_url, "downgrade", BEFORE_EACH_LABEL)
    assert down.returncode == 0, f"downgrade from 0048 failed:\n{down.stderr}"
    with engine.begin() as conn:
        assert _settings(conn) == {
            "label_codes": "both",
            "label_type": "look",
            "label_destination": "bluetooth",
        }
        columns = {row[0] for row in conn.execute(text("SHOW COLUMNS FROM print_job"))}
    assert "label" not in columns
    assert _alembic(scratch_db_url, "upgrade", "head").returncode == 0
    with engine.begin() as conn:
        assert _settings(conn) == {
            "label_small_codes": "both",
            "label_full_codes": "both",
            "label_small_type": "look",
            "label_full_type": "look",
            "label_small_destination": "bluetooth",
        }
    engine.dispose()
