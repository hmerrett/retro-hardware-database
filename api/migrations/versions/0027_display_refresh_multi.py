"""a screen may do more than one refresh rate, and say so

The refresh rate was one whole number: the highest a monitor would manage at the
resolution beside it. That is the right thing to record about a tube being judged on
whether it flickers, and the wrong thing to record about hardware driven at
television rates -- where the question is not how high the screen will go but
whether it will come down to meet the machine.

A screen answers it more than once, in other words, exactly as it answers the line
rate and the sockets. An Acorn AKF18 takes 47-90 Hz; a monitor beside it may list
60 Hz and 85 Hz and nothing between; and an integer column holding the highest of
those drops the 50 Hz that decides whether an Archimedes or an Amiga puts a picture
up at all.

So `refresh_hz` becomes `refresh`, text, holding the rates as they are ticked or the
range a multiscan claims -- the same shape `sync` and `interface` already have. What
is already recorded comes across as the figure it was, with the unit it is read in:
85 becomes "85 Hz", which is what the form and the page were showing anyway.

The remaining two numbers stay numbers. A screen size and a dot pitch each have one
value per screen and always did, so "every 14-inch and under" and "anything finer
than 0.28" are still comparisons rather than text searches.

Revision ID: 0027_display_refresh_multi
Revises: 0026_display_sync
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0027_display_refresh_multi"
down_revision = "0026_display_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("display_spec", sa.Column("refresh", sa.String(255)))
    # The figure with the unit it was always displayed in, so a record reopens on
    # the answer the list offers rather than on a bare number beside "custom".
    op.execute("UPDATE display_spec SET refresh = CONCAT(refresh_hz, ' Hz') "
               "WHERE refresh_hz IS NOT NULL")
    op.drop_column("display_spec", "refresh_hz")


def downgrade():
    op.add_column("display_spec", sa.Column("refresh_hz", sa.Integer()))
    # Only a single figure can go back into an integer column. A screen that has
    # since been recorded as doing several rates, or a range, is left with none
    # rather than having one end of its answer chosen for it.
    op.execute("UPDATE display_spec SET refresh_hz = CAST(refresh AS UNSIGNED) "
               "WHERE refresh REGEXP '^[0-9]+ *[Hh]?[Zz]?$'")
    op.drop_column("display_spec", "refresh")
