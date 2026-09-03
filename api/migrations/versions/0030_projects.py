"""projects: the work, as against the things it is done to

The register has held what is owned. This is what is intended: a repair, a build,
a machine wanted and not yet found. The two are described by different facts -- a
Spectrum has a board issue and a ULA, and "recap the +2A" has a state, a list of
jobs and a pile of things on order -- so a project is tables of its own rather
than more columns on an asset.

A project takes an asset id from the same allocator the two asset tables draw
from, and that is the whole of why it can keep a history: log_entry is keyed by a
plain asset id precisely because no one table owns the register, so a project
writes notes, folds its history and hangs photographs on its entries without a
line of new code. project_asset names its members the same way and for the same
reason -- what is in a project is a computer or a part, and no single foreign key
can point at both.

This lands on top of 0029_future_projects, which put a `project` flag and a
`project_note` on computers and parts. The two are not rivals and neither replaces
the other: that flag is a thing noticed -- a board that wants a recap, marked in a
second while standing at it -- and this is a piece of work committed to, with a
name, a list of jobs and things on order against it. One becomes the other often
enough that they share a page, and the flagged item says which project has taken
it on.

project_order is the first table here to record money. cost_p is an integer of
pence, following the rule every other quantity in this schema follows: stored in a
small unit named by the column suffix, so it sorts and adds exactly. NULL is a
cost not recorded, which is not the same as free.

Revision ID: 0030_projects
Revises: 0029_future_projects
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0030_projects"
down_revision = "0029_future_projects"
branch_labels = None
depends_on = None


def _project_fk():
    return sa.Column("project_id", sa.String(16), nullable=False)


def upgrade():
    op.create_table(
        "projects",
        sa.Column("asset_id", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        # A slug from projects.STATUSES, never the label shown on screen.
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="planned"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Three dates answering three questions, any of which can be unknown while
        # the others are not. None is inferred from another.
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("finished_at", sa.Date(), nullable=True),
    )
    op.create_table(
        "project_asset",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _project_fk(),
        # Plain, like log_entry's: it names something in the shared register, and
        # the register is two tables.
        sa.Column("asset_id", sa.String(16), nullable=False),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["projects.asset_id"],
                                ondelete="CASCADE"),
        # A thing is in a project once, however many times it is added.
        sa.UniqueConstraint("project_id", "asset_id", name="uq_project_asset"),
    )
    op.create_index("ix_project_asset_project_id", "project_asset", ["project_id"])
    op.create_index("ix_project_asset_asset_id", "project_asset", ["asset_id"])
    op.create_table(
        "project_task",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _project_fk(),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("done_at", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_project_task_project_id", "project_task", ["project_id"])
    op.create_table(
        "project_order",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        _project_fk(),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("supplier", sa.String(255), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        # Pence for the whole line as paid, not a unit price: that is the figure on
        # the receipt, and dividing it would invent a number nobody quoted.
        sa.Column("cost_p", sa.Integer(), nullable=True),
        sa.Column("ordered_at", sa.Date(), nullable=True),
        sa.Column("expected_at", sa.Date(), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("delivered_at", sa.Date(), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["projects.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_project_order_project_id", "project_order", ["project_id"])


def downgrade():
    op.drop_table("project_order")
    op.drop_table("project_task")
    op.drop_table("project_asset")
    op.drop_table("projects")
