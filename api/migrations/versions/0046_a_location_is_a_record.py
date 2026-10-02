"""a location is a record: where things are kept, as things in the register

ADR-0034. `location` was a line of text on a machine or a part, which could be
read and nothing else: thirty things in one crate were thirty strings, the crate
had no label to scan and no page to stand on, and carrying it to the workshop was
thirty edits. So a location becomes a row with a tag from the register's own pool,
a kind, the location it is inside, notes and a photograph, and a thing points at
the one it is kept in. The path -- Workshop, Rack 3, Box 14 -- is read up the
parents when it is shown and never written down, so moving the box is one write.

Three tables come with it. `moves` is each change of where something is kept,
with who made it and how, because a line of history text cannot be asked where a
thing was before. `stock_checks` and `stock_check_scans` are a storage-mode round
and every scan in it, kept on the server so a phone that locks in the loft has not
lost the half-done shelf.

The text converts once, and that is a general, data-driven backfill rather than a
correction to named rows (database-standards): every distinct spelling becomes a
top-level location of kind `other`, named as it was typed, and so does every place
the remembered list (0043) was still holding. Spellings that differ only in case
or in the spaces round them are one location -- the remembered list's primary key
already folded case, so the register has always treated them as one crate -- under
the spelling most things were filed with. Nothing is nested, because nothing here
could know that `loft crate3` is inside `Loft`; that is the owner's to say.

The tags are drawn the way ids.py draws them, from the same alphabet and against
every tag already taken in all four tables. Written out here rather than imported:
a migration that imports the app runs whatever the app is on the day it runs, and
this one has to mean the same thing on every install for as long as it is in the
history.

MariaDB auto-commits DDL, so each step is written to be run again: a table or a
column is made only if it is missing, the conversion makes only the locations it
cannot find and fills only the links still empty, and the text goes last, once
nothing still reads it. A failure partway leaves a register that can be upgraded
again rather than one that has to be mended by hand.

Revision ID: 0046_a_location_is_a_record
Revises: 0045_accounts
Create Date: 2026-10-01
"""

import secrets
import string
from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "0046_a_location_is_a_record"
down_revision = "0045_accounts"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")

# ids.py's alphabet, as it stands: I, L and O are dropped because they cannot be
# told from 1 and 0 off a printed label.
_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "ILO")


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _make_tables():
    if not _has_table("locations"):
        op.create_table(
            "locations",
            sa.Column("asset_id", sa.String(length=16), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="other"),
            sa.Column("parent_id", sa.String(length=16), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("image", sa.String(length=255), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["parent_id"], ["locations.asset_id"], ondelete="SET NULL"),
        )
        op.create_index("ix_locations_parent_id", "locations", ["parent_id"])
    for table in TABLES:
        if "location_id" not in _columns(table):
            op.add_column(table, sa.Column("location_id", sa.String(length=16), nullable=True))
            # The index before the key, so MariaDB leans the key on this one rather
            # than making a second of its own.
            op.create_index(f"ix_{table}_location_id", table, ["location_id"])
            op.create_foreign_key(
                f"fk_{table}_location_id",
                table,
                "locations",
                ["location_id"],
                ["asset_id"],
                ondelete="SET NULL",
            )
    if not _has_table("moves"):
        op.create_table(
            "moves",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("asset_id", sa.String(length=16), nullable=False),
            sa.Column("from_id", sa.String(length=16), nullable=True),
            sa.Column("from_path", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("to_id", sa.String(length=16), nullable=True),
            sa.Column("to_path", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("moved_at", sa.DateTime(), nullable=False),
            sa.Column("who", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("how", sa.String(length=8), nullable=False),
            sa.Column("log_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["log_id"], ["log_entry.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_moves_asset_id", "moves", ["asset_id"])
        op.create_index("ix_moves_moved_at", "moves", ["moved_at"])
        op.create_index("ix_moves_log_id", "moves", ["log_id"])
    if not _has_table("stock_checks"):
        op.create_table(
            "stock_checks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_stock_checks_user_id", "stock_checks", ["user_id"])
    if not _has_table("stock_check_scans"):
        op.create_table(
            "stock_check_scans",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("check_id", sa.Integer(), nullable=False),
            sa.Column("scanned_at", sa.DateTime(), nullable=False),
            sa.Column("code", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("asset_id", sa.String(length=16), nullable=True),
            sa.Column("at_id", sa.String(length=16), nullable=True),
            sa.Column("result", sa.String(length=16), nullable=False),
            sa.Column("said", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("move_id", sa.Integer(), nullable=True),
            sa.Column("was_computer", sa.String(length=16), nullable=True),
            sa.Column("was_parent", sa.String(length=16), nullable=True),
            sa.Column("undone", sa.Boolean(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["check_id"], ["stock_checks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["move_id"], ["moves.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_stock_check_scans_check_id", "stock_check_scans", ["check_id"])
        op.create_index("ix_stock_check_scans_move_id", "stock_check_scans", ["move_id"])


def _convert():
    """Every spelling in use or remembered, as a location; every thing, in its.

    Read in Python rather than grouped in SQL, because the grouping is the point
    and it has to be exactly the one described above: trimmed, folded for case, and
    named after the commonest spelling, ties broken by the spelling itself so two
    installs holding the same text come out the same."""
    conn = op.get_bind()
    typed = []
    for table in TABLES:
        if "location" not in _columns(table):
            continue
        typed += [
            (table, aid, where.strip())
            for aid, where in conn.execute(sa.text(f"SELECT asset_id, location FROM {table}"))
            if where and where.strip()
        ]
    remembered = []
    if _has_table("location"):
        remembered = [
            name.strip()
            for (name,) in conn.execute(sa.text("SELECT name FROM location"))
            if name and name.strip()
        ]

    spellings: dict[str, Counter[str]] = {}
    for _table, _aid, where in typed:
        spellings.setdefault(where.casefold(), Counter())[where] += 1
    for name in remembered:
        spellings.setdefault(name.casefold(), Counter())
        spellings[name.casefold()][name] += 0

    found = {
        name.casefold(): aid
        for aid, name in conn.execute(sa.text("SELECT asset_id, name FROM locations"))
    }
    taken = set(found.values())
    for table in ("computers", "parts", "projects"):
        taken |= {aid for (aid,) in conn.execute(sa.text(f"SELECT asset_id FROM {table}"))}

    for key in sorted(spellings):
        if key in found:
            continue
        counts = spellings[key]
        name = sorted(counts, key=lambda s: (-counts[s], s))[0]
        while True:
            tag = "RH-" + "".join(secrets.choice(_ALPHABET) for _ in range(4))
            if tag not in taken:
                break
        taken.add(tag)
        conn.execute(
            sa.text(
                "INSERT INTO locations (asset_id, name, kind, parent_id, notes, image) "
                "VALUES (:tag, :name, 'other', NULL, '', '')"
            ),
            {"tag": tag, "name": name},
        )
        found[key] = tag

    for table, aid, where in typed:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET location_id = :tag "
                "WHERE asset_id = :aid AND location_id IS NULL"
            ),
            {"tag": found[where.casefold()], "aid": aid},
        )


def upgrade():
    _make_tables()
    _convert()
    for table in TABLES:
        if "location" in _columns(table):
            op.drop_column(table, "location")
    if _has_table("location"):
        op.drop_table("location")
    # The switch that kept the remembered list has nothing left to switch.
    op.get_bind().execute(sa.text("DELETE FROM setting WHERE name = 'remember_locations'"))


def _paths(conn):
    """{tag: path} for every location, the names root first, as the downgrade
    writes them back -- which for a location this migration made is the name it
    was typed as. Cut at the column's 255, and safe against a loop nothing in the
    app can build."""
    rows = {
        aid: (name, parent)
        for aid, name, parent in conn.execute(
            sa.text("SELECT asset_id, name, parent_id FROM locations")
        )
    }
    out = {}
    for aid in rows:
        names, at, seen = [], aid, set()
        while at in rows and at not in seen:
            seen.add(at)
            names.insert(0, rows[at][0])
            at = rows[at][1]
        out[aid] = " / ".join(names)[:255]
    return out, {name for name, _parent in rows.values()}


def downgrade():
    """Back to text. Each thing gets the words of where it is, and the remembered
    list every location's name, so a register taken down offers the same places it
    was keeping things in. What is lost is what text cannot hold: the nesting as a
    structure, the notes and photographs of a location, the moves and the rounds."""
    conn = op.get_bind()
    for table in TABLES:
        if "location" not in _columns(table):
            op.add_column(
                table,
                sa.Column("location", sa.String(255), nullable=False, server_default=""),
            )
    if not _has_table("location"):
        op.create_table(
            "location",
            sa.Column("name", sa.String(length=255), primary_key=True, nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
        )
    if _has_table("locations"):
        paths, names = _paths(conn)
        for table in TABLES:
            for aid, tag in conn.execute(
                sa.text(f"SELECT asset_id, location_id FROM {table} WHERE location_id IS NOT NULL")
            ):
                conn.execute(
                    sa.text(f"UPDATE {table} SET location = :where WHERE asset_id = :aid"),
                    {"where": paths.get(tag, ""), "aid": aid},
                )
        # One row a spelling, folded as the table's own key folds them.
        kept = {}
        for name in sorted(names):
            if name.strip():
                kept.setdefault(name.strip().casefold(), name.strip()[:255])
        for name in kept.values():
            conn.execute(
                sa.text("INSERT IGNORE INTO location (name, used_at) VALUES (:n, NULL)"),
                {"n": name},
            )
    # The tables and not their indexes first, as 0045's downgrade does: MariaDB will
    # not drop an index a foreign key still leans on.
    for table in ("stock_check_scans", "stock_checks", "moves"):
        if _has_table(table):
            op.drop_table(table)
    for table in TABLES:
        if "location_id" in _columns(table):
            op.drop_constraint(f"fk_{table}_location_id", table, type_="foreignkey")
            op.drop_index(f"ix_{table}_location_id", table_name=table)
            op.drop_column(table, "location_id")
    if _has_table("locations"):
        op.drop_table("locations")
