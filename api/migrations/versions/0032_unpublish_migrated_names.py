"""take back the names 0031 wrote onto public pages

0031 turned each flagged item into a private project and wrote a line into that
item's own history saying so -- "wanted for <name> (RH-XXXX)". The reasoning was
that a plan with a page of its own no longer needs the register to be quiet about
it. That was wrong in the one way that matters: the project it makes is private,
and an item's history is public.

So the line announced a private project, and its tag, on the page of the machine
it was about -- which is precisely the fifth of the five places a private project
is meant not to appear, opened by the migration that closed the other four.

The app has never written such a line (main._member_log declines while a project is
private, and _publish_log deletes them when one is withdrawn). This does for the
rows already written what _publish_log would have done: takes out any entry naming
a private project on an item that project is about. Matched on the tag, which is
what makes a line that project's whatever the name has since become.

Nothing is written to say the lines were removed. An entry saying "a line about a
private project was deleted here" is the disclosure again, in the past tense.

Revision ID: 0032_unpublish_migrated_names
Revises: 0031_private_projects
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0032_unpublish_migrated_names"
down_revision = "0031_private_projects"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT a.asset_id, a.project_id FROM project_asset a"
        " JOIN projects p ON p.asset_id = a.project_id WHERE p.private = 1")).all()
    for asset_id, project_id in rows:
        bind.execute(sa.text(
            "DELETE FROM log_entry WHERE asset_id = :a AND message LIKE :m"),
            {"a": asset_id, "m": f"%({project_id})%"})


def downgrade():
    """Nothing. The lines should not have been written, and putting them back would
    be republishing the names they carry."""
