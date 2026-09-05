"""a project raised at check-in is named after the thing, not its tag

The work box names a project after the item it is about, because the form asks for
no name and the item is the only thing known at that moment. It used to write the
item's asset tag into that name -- "Work required by item: RH-J8JA" -- which is a
line you have to look up before it means anything, and a list of them is a list of
lookups. It says the item's name now: "Work required by item: Amstrad PC1640".

This brings the ones already written into line. General rather than particular,
which is what makes it a migration and not a tools/ script (ADR-0002): it renames
whatever rows match the old shape on whatever database it is run against, and does
nothing at all on one where none do -- a fresh install included.

The rule is deliberately narrow. A project is renamed only where its name is
exactly the old form built from the tag of an item it is actually about, so a
project somebody has since named by hand is left alone even if it still starts with
those words. Two projects can come out with the same name, where the collection
holds two of the same machine; that is what the project's own tag beside it on
every list is for, and inventing a distinction here would be inventing it in the
wrong place.

display_name is spelled out again below rather than imported from the app, for the
reason 0031's id allocator was: a migration that imports the app is a migration
that stops running the day the app changes shape.

Revision ID: 0033_work_project_names
Revises: 0032_unpublish_migrated_names
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0033_work_project_names"
down_revision = "0032_unpublish_migrated_names"
branch_labels = None
depends_on = None

PREFIX = "Work required by item: "


def _display_name(row):
    """What an item is called: its own name, else maker and model, else its tag.
    app/entry.py:display_name, kept in step by hand."""
    if (row["name"] or "").strip():
        return row["name"].strip()
    joined = " ".join(p for p in ((row["manufacturer"] or "").strip(),
                                  (row["model"] or "").strip()) if p).strip()
    return joined or row["asset_id"]


def _named_items(bind):
    """{asset_id: display name} for everything in the register."""
    out = {}
    for table in ("computers", "parts"):
        for row in bind.execute(sa.text(
                f"SELECT asset_id, name, manufacturer, model FROM {table}")):
            out[row.asset_id] = _display_name(row._mapping)
    return out


def _projects_about_one_item(bind):
    """(project_id, project name, the one asset it is about) for every project with
    exactly one item on it. A project about two things was never named this way."""
    rows = bind.execute(sa.text(
        "SELECT p.asset_id, p.name, MIN(a.asset_id) AS item, COUNT(*) AS n "
        "FROM projects p JOIN project_asset a ON a.project_id = p.asset_id "
        "GROUP BY p.asset_id, p.name")).all()
    return [(r.asset_id, r.name, r.item) for r in rows if r.n == 1]


def _rename(bind, old, new):
    bind.execute(sa.text("UPDATE projects SET name = :name WHERE asset_id = :id"),
                 {"name": new[:255], "id": old})


def upgrade():
    bind = op.get_bind()
    names = _named_items(bind)
    for project_id, project_name, item in _projects_about_one_item(bind):
        # Only the exact old form, built from the tag of the item this project is
        # about. Anything else is a name somebody chose.
        if project_name != f"{PREFIX}{item}":
            continue
        called = names.get(item)
        if called and called != item:
            _rename(bind, project_id, f"{PREFIX}{called}")


def downgrade():
    """Back to the tag. Read from the membership rather than from the name, because
    the name no longer holds a tag to read -- which is the whole of what changed."""
    bind = op.get_bind()
    names = _named_items(bind)
    for project_id, project_name, item in _projects_about_one_item(bind):
        called = names.get(item)
        if called and project_name == f"{PREFIX}{called}":
            _rename(bind, project_id, f"{PREFIX}{item}")
