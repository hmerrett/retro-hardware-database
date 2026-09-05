"""one notation for a machine's CPU

Originally normalised the CPU notation on four specific machines in the original
database (e.g. 'Intel 486 SX 25' to 'Intel 486SX-25'). Those were one-off,
per-asset corrections, so they have been removed from the migration history: a
one-off tidy of specific rows belongs with the database it applies to, not in the
schema history every install replays. See ADR-0002. The corrections were applied
to the live database by the first run of this migration.

The revision is kept as a no-op so the migration chain and the applied history
stay intact.

Revision ID: 0013_normalise_cpu
Revises: 0012_computer_drives
Create Date: 2026-07-30
"""
revision = "0013_normalise_cpu"
down_revision = "0012_computer_drives"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
