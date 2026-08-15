"""a machine's TopBench score

Everything a computer's record holds is what it was built as: a CPU, an amount of
memory, the drives fitted. None of it says how fast the thing actually turns out to
be, and on a PC that is not always what the parts list predicts -- a cache left
disabled, a turbo button, a chipset set up wrong, and a 486DX2-66 scores like a
386.

TopBench is the DOS benchmark that answers it, and the number it gives is worth
keeping beside the parts that earned it. One nullable integer column: NULL is a
machine nobody has run it on, which is nearly all of them to begin with. Nothing
here guesses a score from a CPU -- an unmeasured machine has no score, and having
run it is the entire value of the field.

Only x86 machines get one (there is no TopBench for a Spectrum), but that is a
question for the form rather than for the column: the register does not hold an
architecture flag, and a NULL says "no score" whatever the machine is.

Revision ID: 0022_computer_topbench
Revises: 0021_fold_without_spaces
Create Date: 2026-08-15
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_computer_topbench"
down_revision = "0021_fold_without_spaces"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("computers", sa.Column("topbench", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("computers", "topbench")
