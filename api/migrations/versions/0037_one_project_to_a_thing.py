"""one project to a thing, and a job may name the thing it is about

Two changes to the same idea (ADR-0016). project_asset was many-to-many, so a
thing could be on several projects at once; it is one project to a thing now, and
the unique constraint moves from the pair to the asset alone. project_task gains
an optional asset_id, so a job can say which of a project's things it is about --
which is what lets an item's page list its own jobs rather than the whole
project's.

The order matters, and MariaDB auto-commits DDL, so each step has to leave
something a re-run can carry on from. The column goes on first (harmless on its
own), then the duplicate memberships are resolved, then the constraint is
swapped. A failure at the last step leaves the first two done and re-running
redoes them harmlessly -- whereas swapping the constraint first would fail
against any database that still holds a duplicate, and fail every time.

Resolving duplicates is a general rule and not a judgement about anybody's rows,
which is what keeps it in the migration history at all (ADR-0002): where a thing
is on more than one project, the earliest membership is the one kept. Earliest
because it is the one that can be worked out from the data rather than chosen,
and because the first answer to "what is this for?" is the likeliest to be the
real one. Anything it drops is logged, so an owner can put it back by hand; a
downgrade cannot, and says so.

Revision ID: 0037_one_project_to_a_thing
Revises: 0036_work_projects_drop_prefix
Create Date: 2026-09-14
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0037_one_project_to_a_thing"
down_revision = "0036_work_projects_drop_prefix"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def extras(rows):
    """The memberships to drop, out of (id, project_id, asset_id) rows ordered by
    asset then id: every one but the earliest, for each asset held more than once.

    Taking rows rather than a connection so the rule can be tested on its own. It is
    the only part of this migration that decides anything, and it cannot be
    exercised through the schema once the constraint it exists to make possible is
    in place -- by then the database will not hold a duplicate to resolve."""
    seen, extra = set(), []
    for row in rows:
        asset = row[2]
        if asset in seen:
            extra.append(row)
        else:
            seen.add(asset)
    return extra


def _extra_memberships(bind):
    return extras(bind.execute(sa.text(
        "SELECT id, project_id, asset_id FROM project_asset ORDER BY asset_id, id"
    )).all())


def upgrade():
    bind = op.get_bind()
    op.add_column("project_task", sa.Column("asset_id", sa.String(16), nullable=True))
    op.create_index("ix_project_task_asset_id", "project_task", ["asset_id"])

    for row in _extra_memberships(bind):
        log.warning("0037: %s was also on %s; keeping the earlier project only",
                    row[2], row[1])
        bind.execute(sa.text("DELETE FROM project_asset WHERE id = :id"),
                     {"id": row[0]})

    op.drop_constraint("uq_project_asset", "project_asset", type_="unique")
    op.create_unique_constraint("uq_project_asset_item", "project_asset",
                                ["asset_id"])


def downgrade():
    """Back to many-to-many. The memberships the upgrade dropped are not restored:
    they were deleted, and nothing left in the schema records what they were. The
    log line is the only trace, which is why there is one."""
    op.drop_constraint("uq_project_asset_item", "project_asset", type_="unique")
    op.create_unique_constraint("uq_project_asset", "project_asset",
                                ["project_id", "asset_id"])
    op.drop_index("ix_project_task_asset_id", table_name="project_task")
    op.drop_column("project_task", "asset_id")
