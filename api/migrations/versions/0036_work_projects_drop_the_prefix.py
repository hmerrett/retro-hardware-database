"""a project raised from an item is called what the item is called, and nothing else

The work box names a project after the item it is about, because the form asks for
no name and the item is the only thing known at that moment. It wrote "Work
required by item: Amstrad PC1640"; it writes "Amstrad PC1640" now. The prefix said
the same thing on every row it appeared on, which is a word that has stopped
carrying information, and it pushed the only part that varies to where a narrow
column cuts it off.

This brings the ones already written into line. General rather than particular,
which is what makes it a migration and not a tools/ script (ADR-0002): it renames
whatever rows match the generated shape on whatever database it is run against,
and does nothing at all on one where none do -- a fresh install included.

The rule is 0033's, deliberately narrow. A project is renamed only where its name
is exactly the generated form for the one item it is about, so a project somebody
has since named by hand is left alone even if it still starts with those words. A
project about two things was never named this way and is not touched.

The downgrade puts the prefix back on the same narrow rule, and shares that rule's
one imprecision: a project a person named by hand exactly what its item is called
comes back prefixed. 0033's downgrade has the same property, for the same reason --
the name is the only evidence, and after the rename it no longer says who wrote it.

display_name is spelled out again below rather than imported from the app, for the
reason 0033's was: a migration that imports the app is a migration that stops
running the day the app changes shape.

Revision ID: 0036_work_projects_drop_prefix
Revises: 0035_public_files
Create Date: 2026-09-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_work_projects_drop_prefix"
down_revision = "0035_public_files"
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
        called = names.get(item)
        if called and project_name == f"{PREFIX}{called}":
            _rename(bind, project_id, called)


def downgrade():
    bind = op.get_bind()
    names = _named_items(bind)
    for project_id, project_name, item in _projects_about_one_item(bind):
        called = names.get(item)
        if called and project_name == called:
            _rename(bind, project_id, f"{PREFIX}{called}")
