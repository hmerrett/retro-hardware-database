"""where a thing is, is one tree: the register's pool as a table, holding what each
thing is inside

ADR-0036. Where a thing was had five answers in three tables: a location's
`parent_id`, `location_id` on a machine and on a part, and a part's `computer_id`
and `parent_id`. They all said what a thing is directly inside, and four separate
walks read them and disagreed at the edges. So the pool of tags becomes a table,
`register`, with the tag as its primary key -- the database now refuses a tag held
twice, where ids.py used to ask four tables in turn -- and one `inside_id` on it,
and each kind's own table hangs off it by `asset_id`. The five columns go, and so
do `was_computer` and `was_parent` on a scan, whose move now says what a part was
taken out of.

`location_public` comes onto machines and parts: whether a visitor is told where
this one is kept. Every existing thing is given what Show locations says today, so
the upgrade changes nothing a visitor sees.

What the old columns could say and the new one cannot is settled by general,
data-driven rules rather than by naming rows (database-standards):

- A link to what a part is mounted on wins over what it is installed in, and both
  over where it is kept -- the order locations.inherited read them in. A part that
  had a host and a location of its own stays with its host, and its history says
  which location it no longer claims.
- A thing still in the collection inside something disposed of is disposed of with
  it, on the same date and for the same reason, which is what disposal would have
  done had it reached it; restoring the outer thing then brings it back.
- A scan that took a part out of a machine had kept the machine in `was_computer`
  or `was_parent`. Its move is pointed at that machine instead, so its undo still
  puts the part back in it.

Before anything is written, the upgrade looks for one tag held by two tables. The
allocator has never handed one out twice, but an import could have, and the
register's primary key would refuse it halfway through: refusing before the first
statement leaves a register that can be put right and upgraded, rather than one
half made.

MariaDB auto-commits DDL, so each step can run again: the register is made if it is
missing and filled with the rows it lacks, the links are copied while the old
columns are there to copy from, and the old columns go last.

Revision ID: 0047_where_a_thing_is
Revises: 0046_a_location_is_a_record
Create Date: 2026-10-08
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0047_where_a_thing_is"
down_revision = "0046_a_location_is_a_record"
branch_labels = None
depends_on = None

# Each kind's table, and what its rows are called in the register.
KINDS = (("computers", "computer"), ("parts", "part"), ("locations", "location"), ("projects", "project"))

# settings.OFF, as it stands: the spellings of a switch that is off.
_OFF = ("0", "false", "no", "off")


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _fk_on(table, column):
    """The name of the foreign key on one column, whatever it was called: the old
    location tree's was made inline and named by the server."""
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk["constrained_columns"] == [column]:
            return fk["name"]
    return None


def _has_index(table, name):
    return any(ix["name"] == name for ix in sa.inspect(op.get_bind()).get_indexes(table))


def _refuse_shared_tags(conn):
    held = {}
    for table, _what in KINDS:
        for (aid,) in conn.execute(sa.text(f"SELECT asset_id FROM {table}")):
            held.setdefault(aid.upper(), []).append(table)
    shared = sorted((tag, tables) for tag, tables in held.items() if len(tables) > 1)
    if shared:
        listed = "; ".join(f"{tag} ({', '.join(tables)})" for tag, tables in shared)
        raise RuntimeError(
            "Some tags are held by more than one thing, and the register keeps one "
            f"thing to a tag: {listed}. Give one of each a new tag, then upgrade again."
        )


def _make_register(conn):
    if not _has_table("register"):
        op.create_table(
            "register",
            sa.Column("asset_id", sa.String(length=16), nullable=False),
            sa.Column("what", sa.String(length=16), nullable=False),
            sa.Column("inside_id", sa.String(length=16), nullable=True),
            sa.PrimaryKeyConstraint("asset_id"),
            sa.ForeignKeyConstraint(
                ["inside_id"],
                ["register.asset_id"],
                name="fk_register_inside_id",
                ondelete="SET NULL",
            ),
        )
        op.create_index("ix_register_inside_id", "register", ["inside_id"])
    for table, what in KINDS:
        conn.execute(
            sa.text(
                f"INSERT INTO register (asset_id, what) SELECT t.asset_id, '{what}' "
                f"FROM {table} t WHERE NOT EXISTS "
                "(SELECT 1 FROM register r WHERE r.asset_id = t.asset_id)"
            )
        )


def _copy_links(conn):
    """Each thing's one link, from whichever old column held it."""
    if "parent_id" in _columns("locations"):
        conn.execute(
            sa.text(
                "UPDATE register r JOIN locations l ON l.asset_id = r.asset_id "
                "SET r.inside_id = UPPER(l.parent_id) WHERE l.parent_id IS NOT NULL"
            )
        )
    if "location_id" in _columns("computers"):
        conn.execute(
            sa.text(
                "UPDATE register r JOIN computers c ON c.asset_id = r.asset_id "
                "SET r.inside_id = UPPER(c.location_id) WHERE c.location_id IS NOT NULL"
            )
        )
    if {"computer_id", "parent_id", "location_id"} <= _columns("parts"):
        conn.execute(
            sa.text(
                "UPDATE register r JOIN parts p ON p.asset_id = r.asset_id "
                "SET r.inside_id = UPPER(COALESCE(p.parent_id, p.computer_id, p.location_id)) "
                "WHERE COALESCE(p.parent_id, p.computer_id, p.location_id) IS NOT NULL"
            )
        )


def _log(conn, aid, message):
    conn.execute(
        sa.text(
            "INSERT INTO log_entry (asset_id, created_at, kind, message) "
            "VALUES (:aid, :at, 'change', :message)"
        ),
        {"aid": aid, "at": _now(), "message": message},
    )


def _paths(conn):
    """{tag: path} for every location, the names from the top down, read up the old
    location links while they are there."""
    rows = {
        aid: (name, parent)
        for aid, name, parent in conn.execute(
            sa.text("SELECT asset_id, name, parent_id FROM locations")
        )
    }

    def path(tag):
        names, seen = [], set()
        while tag in rows and tag not in seen:
            seen.add(tag)
            names.insert(0, rows[tag][0])
            tag = rows[tag][1]
        return " / ".join(names)

    return {tag: path(tag) for tag in rows}


def _say_which_location_went(conn):
    """A part with a host and a location of its own stays with its host. Its history
    says which location it no longer claims, so the answer it used to give is not
    lost without trace."""
    # Only while every old column is still there to read: a run that stopped after
    # dropping one of them had already written these lines.
    if not {"computer_id", "parent_id", "location_id"} <= _columns("parts"):
        return
    if "parent_id" not in _columns("locations"):
        return
    paths = _paths(conn)
    for aid, parent, computer, where in conn.execute(
        sa.text(
            "SELECT asset_id, parent_id, computer_id, location_id FROM parts "
            "WHERE location_id IS NOT NULL AND (parent_id IS NOT NULL OR computer_id IS NOT NULL)"
        )
    ).all():
        verb, host = ("mounted on", parent) if parent else ("fitted in", computer)
        place = paths.get(where) or where
        _log(conn, aid, f"stays {verb} {host.upper()}, and no longer also says it is kept in {place}")


def _dispose_what_was_left_inside(conn):
    """Anything still in the collection inside a machine or a part that has been
    disposed of goes with it: the date and the reason of the nearest disposed thing
    it is inside, as disposal.py would have written them."""
    inside = dict(conn.execute(sa.text("SELECT asset_id, inside_id FROM register")).all())
    gone = {}
    for table in ("computers", "parts"):
        for aid, at, note in conn.execute(
            sa.text(f"SELECT asset_id, disposed_at, disposed_note FROM {table} WHERE disposed = 1")
        ):
            gone[aid.upper()] = (at, note or "")
    live = [
        (table, aid)
        for table in ("computers", "parts")
        for (aid,) in conn.execute(sa.text(f"SELECT asset_id FROM {table} WHERE disposed = 0"))
    ]
    for table, aid in live:
        up, seen = inside.get(aid), {aid.upper()}
        while up and up.upper() not in seen and up.upper() not in gone:
            seen.add(up.upper())
            up = inside.get(up)
        if not up or up.upper() not in gone:
            continue
        at, note = gone[up.upper()]
        conn.execute(
            sa.text(
                f"UPDATE {table} SET disposed = 1, disposed_at = :at, disposed_note = :note "
                "WHERE asset_id = :aid"
            ),
            {"at": at, "note": note, "aid": aid},
        )
        when = at.isoformat() if at else "date unknown"
        _log(conn, aid, f"marked disposed with {up.upper()} ({when})" + (f": {note}" if note else ""))


def _point_scans_at_what_they_took_out_of(conn):
    if "was_computer" not in _columns("stock_check_scans"):
        return
    conn.execute(
        sa.text(
            "UPDATE moves m JOIN stock_check_scans s ON s.move_id = m.id "
            "SET m.from_id = UPPER(COALESCE(s.was_parent, s.was_computer)), m.from_path = '' "
            "WHERE s.was_parent IS NOT NULL OR s.was_computer IS NOT NULL"
        )
    )


def _ticks(conn):
    """Every machine and part told or not as the switch says today."""
    shown = conn.execute(sa.text("SELECT value FROM setting WHERE name = 'public_locations'")).scalar()
    on = (shown or "0").strip().lower() not in _OFF
    for table in ("computers", "parts"):
        if "location_public" not in _columns(table):
            op.add_column(
                table,
                sa.Column("location_public", sa.Boolean(), nullable=False, server_default="0"),
            )
            if on:
                conn.execute(sa.text(f"UPDATE {table} SET location_public = 1"))


def _hang_kinds_off_the_register():
    for table, _what in KINDS:
        if _fk_on(table, "asset_id") is None:
            op.create_foreign_key(
                f"fk_{table}_register", table, "register", ["asset_id"], ["asset_id"]
            )


def _drop_link(table, column):
    if column not in _columns(table):
        return
    if (name := _fk_on(table, column)) is not None:
        op.drop_constraint(name, table, type_="foreignkey")
    if _has_index(table, f"ix_{table}_{column}"):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_column(table, column)


def upgrade():
    conn = op.get_bind()
    _refuse_shared_tags(conn)
    _make_register(conn)
    _copy_links(conn)
    _say_which_location_went(conn)
    _dispose_what_was_left_inside(conn)
    _point_scans_at_what_they_took_out_of(conn)
    _ticks(conn)
    _hang_kinds_off_the_register()
    for table, column in (
        ("parts", "computer_id"),
        ("parts", "parent_id"),
        ("parts", "location_id"),
        ("computers", "location_id"),
        ("locations", "parent_id"),
    ):
        _drop_link(table, column)
    for column in ("was_computer", "was_parent"):
        if column in _columns("stock_check_scans"):
            op.drop_column("stock_check_scans", column)


def downgrade():
    """The five columns back, each filled from the register by what holds a thing;
    then the register goes. What cannot come back is a tag kept only to stop it being
    issued again, and a part's second answer, which the upgrade had already let go."""
    conn = op.get_bind()
    links = (
        ("locations", "parent_id", "locations", "fk_locations_parent_id"),
        ("computers", "location_id", "locations", "fk_computers_location_id"),
        ("parts", "computer_id", "computers", "fk_parts_computer_id"),
        ("parts", "parent_id", "parts", "fk_parts_parent_id"),
        ("parts", "location_id", "locations", "fk_parts_location_id"),
    )
    for table, column, _target, _name in links:
        if column not in _columns(table):
            op.add_column(table, sa.Column(column, sa.String(length=16), nullable=True))
    for column in ("was_computer", "was_parent"):
        if column not in _columns("stock_check_scans"):
            op.add_column("stock_check_scans", sa.Column(column, sa.String(length=16), nullable=True))
    if _has_table("register"):
        for table, column, held_by in (
            ("locations", "parent_id", "location"),
            ("computers", "location_id", "location"),
            ("parts", "computer_id", "computer"),
            ("parts", "parent_id", "part"),
            ("parts", "location_id", "location"),
        ):
            conn.execute(
                sa.text(
                    f"UPDATE {table} t JOIN register r ON r.asset_id = t.asset_id "
                    "JOIN register h ON h.asset_id = r.inside_id "
                    f"SET t.{column} = r.inside_id WHERE h.what = '{held_by}'"
                )
            )
        conn.execute(
            sa.text(
                "UPDATE stock_check_scans s JOIN moves m ON m.id = s.move_id "
                "JOIN register h ON h.asset_id = m.from_id "
                "SET s.was_computer = IF(h.what = 'computer', m.from_id, NULL), "
                "s.was_parent = IF(h.what = 'part', m.from_id, NULL) "
                "WHERE h.what IN ('computer', 'part')"
            )
        )
    for table, column, target, name in links:
        if not _has_index(table, f"ix_{table}_{column}"):
            op.create_index(f"ix_{table}_{column}", table, [column])
        if _fk_on(table, column) is None:
            op.create_foreign_key(name, table, target, [column], ["asset_id"], ondelete="SET NULL")
    for table in ("computers", "parts"):
        if "location_public" in _columns(table):
            op.drop_column(table, "location_public")
    for table, _what in KINDS:
        if (name := _fk_on(table, "asset_id")) is not None:
            op.drop_constraint(name, table, type_="foreignkey")
    if _has_table("register"):
        op.drop_table("register")
