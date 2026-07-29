"""normalise part specs into typed + list tables

Revision ID: 0002_normalise_specs
Revises: 0001_initial
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_normalise_specs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _fk():
    return sa.ForeignKey("parts.asset_id", ondelete="CASCADE")


def upgrade():
    op.create_table(
        "motherboard_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chipset", sa.String(255)),
        sa.Column("cpu_family", sa.String(255)),
        sa.Column("form_factor", sa.String(64)),
        sa.Column("cache", sa.String(64)),
        sa.Column("bios", sa.String(255)),
        sa.Column("onboard_video", sa.String(255)),
    )
    op.create_table(
        "cpu_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("socket", sa.String(64)),
        sa.Column("speed", sa.String(64)),
        sa.Column("fsb", sa.String(64)),
        sa.Column("cores", sa.Integer()),
        sa.Column("cache", sa.String(64)),
    )
    op.create_table(
        "ram_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("ram_type", sa.String(64)),
        sa.Column("size_kb", sa.Integer()),
        sa.Column("speed", sa.String(64)),
    )
    op.create_table(
        "video_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("connector", sa.String(255)),
        sa.Column("memory_kb", sa.Integer()),
        sa.Column("video_type", sa.String(64)),
    )
    op.create_table(
        "sound_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("fm", sa.String(255)),
        sa.Column("ports", sa.String(255)),
    )
    op.create_table(
        "network_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("connector", sa.String(255)),
    )
    op.create_table(
        "io_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
    )
    op.create_table(
        "storage_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("kind", sa.String(64)),
        sa.Column("interface", sa.String(64)),
        sa.Column("protocol", sa.String(64)),
        sa.Column("capacity", sa.String(64)),
        sa.Column("chs_c", sa.Integer()),
        sa.Column("chs_h", sa.Integer()),
        sa.Column("chs_s", sa.Integer()),
        sa.Column("media", sa.String(255)),
        sa.Column("speed", sa.String(64)),
        sa.Column("role", sa.String(255)),
    )
    for name, cols in (
        ("part_slot", [sa.Column("bus", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_ram_slot", [sa.Column("slot_type", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_port", [sa.Column("port", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_attribute", [sa.Column("akey", sa.String(128)), sa.Column("avalue", sa.Text())]),
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("part_id", sa.String(16), _fk(), nullable=False, index=True),
            *cols,
        )

    _backfill(op.get_bind())


def _backfill(bind):
    """Populate the new tables from each part's existing specs string.

    Deliberately avoids app.models: a migration is frozen in time, but the ORM
    keeps moving, so importing it makes this step break the moment a later
    migration adds a column (parent_id in 0003 did exactly that, leaving a fresh
    `alembic upgrade head` dead at 0001). Reads `parts` with explicit 0001-era
    columns and writes through tables reflected from what upgrade() just built,
    intersecting the parsed keys with the columns that actually exist.
    """
    from app import specstruct
    spec_table = {"motherboard": "motherboard_spec", "cpu": "cpu_spec",
                  "ram": "ram_spec", "video": "video_spec", "sound": "sound_spec",
                  "network": "network_spec", "io": "io_spec",
                  "storage": "storage_spec"}
    meta = sa.MetaData()
    tables = {n: sa.Table(n, meta, autoload_with=bind)
              for n in list(spec_table.values())
              + ["part_slot", "part_ram_slot", "part_port", "part_attribute"]}
    rows = bind.execute(sa.text("SELECT asset_id, type, specs FROM parts")).all()
    for asset_id, ptype, specs in rows:
        ptype = ptype or "other"
        st = specstruct.parse(ptype, specs or "")
        name = spec_table.get(ptype)
        if name:
            cols = dict(st.scalars)
            if ptype == "storage" and st.chs:
                cols["chs_c"], cols["chs_h"], cols["chs_s"] = st.chs
            # specstruct is the live module and has moved on since 0002 (0005
            # renamed the quantity columns), so a key it produces may not exist
            # in the table this migration builds. Refuse rather than drop it: a
            # database with rows to backfill here predates 0002 and must be
            # migrated with a checkout from that era.
            missing = set(cols) - set(tables[name].c.keys())
            if missing:
                raise RuntimeError(
                    f"0002 cannot backfill {name} for {asset_id}: specstruct "
                    f"produced {sorted(missing)}, which this migration's schema "
                    "does not have. The live spec model has changed since 0002. "
                    "Backfill from a checkout contemporary with this revision, "
                    "or start from an empty database.")
            bind.execute(tables[name].insert().values(part_id=asset_id, **cols))
        for tname, col, items in (("part_slot", "bus", st.slots),
                                  ("part_ram_slot", "slot_type", st.ram_slots),
                                  ("part_port", "port", st.ports)):
            for value, n in items:
                bind.execute(tables[tname].insert().values(
                    part_id=asset_id, **{col: value}, count=n))
        for k, v in st.attributes:
            bind.execute(tables["part_attribute"].insert().values(
                part_id=asset_id, akey=k or "", avalue=v))


def downgrade():
    for name in ("part_attribute", "part_port", "part_ram_slot", "part_slot",
                 "storage_spec", "io_spec", "network_spec", "sound_spec",
                 "video_spec", "ram_spec", "cpu_spec", "motherboard_spec"):
        op.drop_table(name)
