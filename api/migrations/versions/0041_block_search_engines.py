"""the search-engine setting is asked the other way up

`search_engines` was a permission -- on meant "this site may be listed" -- and it
is now `block_search_engines`, a refusal: on means "keep this site out". The words
on the page read better as the thing you are switching *on* rather than as the
thing you are switching off, and a preference that is off by default is easier to
reason about than one that is on.

Inverting the meaning under an unchanged key would have been the dangerous way to
do it: every installation that had saved "1" for "please list me" would have come
back up blocking itself, silently, with nothing in the interface to say why. So
the key changes name at the same moment the meaning flips, and this migration
carries the answer across rather than letting it fall back to a default that might
not be what was asked for.

General and data-driven, as a migration here must be (ADR-0002): it reads whatever
row is there, writes the opposite under the new name, and drops the old one.
A database that never had the row -- a fresh install, or one that never opened the
page -- gets nothing written and is correct by the default in settings.py.

Revision ID: 0041_block_search_engines
Revises: 0040_settings
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_block_search_engines"
down_revision = "0040_settings"
branch_labels = None
depends_on = None

OFF = ("0", "false", "no", "off")

OLD, NEW = "search_engines", "block_search_engines"


def _flip(conn, frm, to):
    """Move the stored answer from one key to the other, negated.

    settings.on's reading of what counts as off, copied rather than imported: a
    migration says what it did on the day it ran and must not change meaning when
    the application's own reading is tuned.
    """
    row = conn.execute(
        sa.text("SELECT value FROM setting WHERE name = :name"), {"name": frm}
    ).fetchone()
    if row is None:
        return
    was_on = str(row[0]).strip().lower() not in OFF
    conn.execute(sa.text("DELETE FROM setting WHERE name = :name"), {"name": to})
    conn.execute(
        sa.text("INSERT INTO setting (name, value, updated_at) VALUES (:name, :value, NOW())"),
        {"name": to, "value": "0" if was_on else "1"},
    )
    conn.execute(sa.text("DELETE FROM setting WHERE name = :name"), {"name": frm})


def upgrade():
    _flip(op.get_bind(), OLD, NEW)


def downgrade():
    _flip(op.get_bind(), NEW, OLD)
