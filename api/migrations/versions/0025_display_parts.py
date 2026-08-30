"""a screen is a part with specifications of its own

A monitor has been fileable since the beginning -- as a "peripheral", with whatever
somebody typed into its free-text specs box. That is the same arrangement every
other kind of part has been lifted out of in turn, and for the same reason: a
collection that cannot answer "every CRT", "every 14-inch and under" or "every
Trinitron" is not answering questions about the largest and heaviest objects in it.

So one typed table, on the pattern of the seven before it.

Two columns describe what makes the picture rather than one. `tech` is CRT or LCD
or OLED, and `panel` is how that technology is arranged: a shadow mask, an aperture
grille, TN, IPS. A Trinitron is a CRT with a grille in it, and a single field would
have meant filing one under its trade name stopped it counting as a CRT.

The three numbers are stored the way every quantity here is, as plain integers in a
small unit named by the column. A screen size is in tenths of an inch because 13.3"
is an ordinary size and whole inches could not hold it; a refresh rate is in whole
Hz; a dot pitch is in micrometres because 0.28 mm is not an integer, and the point
of storing it at all is that "anything finer than 0.28" should be a comparison
rather than a text search.

`resolution` is text, on purpose. A fixed panel has one native resolution and could
have been two integer columns, but a multisync CRT runs 640x480 through 1280x1024
and choosing one of those to store would be recording a fact nobody stated.

`colour` and `yellowing` are the pair the drive rows and the storage parts already
hold, from the same two vocabularies. A monitor's front is usually the largest piece
of beige plastic in the room and it yellows like the rest of it, so it is described
in words the register already had rather than in new ones.

Nothing is migrated into this table. A monitor already filed as a peripheral keeps
its free text and its asset tag; retyping it to Display and saving the form is what
moves it, with somebody looking at the thing. Backfilling a tube type out of a
sentence would be the register inventing what it holds.

Revision ID: 0025_display_parts
Revises: 0024_log_photos
Create Date: 2026-08-30
"""
import sqlalchemy as sa
from alembic import op

revision = "0025_display_parts"
down_revision = "0024_log_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "display_spec",
        sa.Column("part_id", sa.String(16), sa.ForeignKey("parts.asset_id",
                                                          ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("tech", sa.String(64)),
        sa.Column("panel", sa.String(64)),
        sa.Column("screen_in_tenths", sa.Integer()),
        sa.Column("aspect", sa.String(16)),
        sa.Column("resolution", sa.String(64)),
        sa.Column("refresh_hz", sa.Integer()),
        sa.Column("dot_pitch_um", sa.Integer()),
        sa.Column("interface", sa.String(255)),
        sa.Column("picture", sa.String(32)),
        sa.Column("colour", sa.String(32)),
        sa.Column("yellowing", sa.String(32)),
    )


def downgrade():
    op.drop_table("display_spec")
