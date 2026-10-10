"""each label its own: the two labels set up separately, and a print job says which

ADR-0037. The two labels shared one setting for their codes and one for their face,
and only the first had somewhere to go: `label_codes`, `label_type` and
`label_destination`. Each label now has its own of all three, so the shared two are
copied to both labels and the destination to the first, and the old keys go. This
is a general, data-driven copy of whatever an installation had chosen, and does
nothing where nothing was chosen (database-standards): a key that was never saved
is the default, and the defaults are the labels as they always were.

A print job gains `label`, which of the two it is for. A job already on the queue
is the first label's, which is what every job was before there were two.

MariaDB auto-commits DDL, so each step is written to be run again: the column is
added only if it is missing, a setting is copied only to a key that has none yet,
and the old keys go last, once they have been read.

Revision ID: 0048_each_label_its_own
Revises: 0047_where_a_thing_is
Create Date: 2026-10-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_each_label_its_own"
down_revision = "0047_where_a_thing_is"
branch_labels = None
depends_on = None

# The old key, and the keys of the labels it was shared by.
COPIES = (
    ("label_codes", ("label_small_codes", "label_full_codes")),
    ("label_type", ("label_small_type", "label_full_type")),
    ("label_destination", ("label_small_destination",)),
)

# What the version before this understood of each, for the way back: a label that
# has since been given no code at all goes back to the default rather than to a
# value the older code would have to guess about.
UNDERSTOOD = {
    "label_codes": {"qr", "code128", "both"},
    "label_type": {"label", "look"},
}


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _stored(conn, name):
    """A setting's row as (value, updated_at), or None where it was never saved."""
    row = conn.execute(
        sa.text("SELECT value, updated_at FROM setting WHERE name = :name"), {"name": name}
    ).first()
    return None if row is None else (row[0], row[1])


def _keep(conn, name, value, when):
    """Write a setting, unless it already has a row of its own."""
    if _stored(conn, name) is None:
        conn.execute(
            sa.text("INSERT INTO setting (name, value, updated_at) VALUES (:name, :value, :at)"),
            {"name": name, "value": value, "at": when},
        )


def upgrade():
    if "label" not in _columns("print_job"):
        op.add_column(
            "print_job",
            sa.Column("label", sa.String(length=8), nullable=False, server_default="small"),
        )
    conn = op.get_bind()
    for old, new in COPIES:
        was = _stored(conn, old)
        if was is None:
            continue
        for name in new:
            _keep(conn, name, *was)
    for old, _ in COPIES:
        conn.execute(sa.text("DELETE FROM setting WHERE name = :name"), {"name": old})


def downgrade():
    """Back to one code and one face for both labels and a destination for the
    first: the first label's, since it is the one that had all three. What the
    second label had of its own, and the rest of what each was set up with -- its
    name, its stock, what was on it -- the older version has nowhere to keep."""
    conn = op.get_bind()
    for old, new in COPIES:
        first = _stored(conn, new[0])
        if first is not None and first[0] in UNDERSTOOD.get(old, {first[0]}):
            _keep(conn, old, *first)
    conn.execute(
        sa.text(
            "DELETE FROM setting WHERE name LIKE 'label\\_small\\_%' OR name LIKE 'label\\_full\\_%'"
        )
    )
    if "label" in _columns("print_job"):
        op.drop_column("print_job", "label")
