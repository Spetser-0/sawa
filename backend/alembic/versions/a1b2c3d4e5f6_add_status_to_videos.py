"""add status column to videos

Revision ID: a1b2c3d4e5f6
Revises: 5b7d478bac90
Create Date: 2026-07-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5b7d478bac90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('videos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(), nullable=True))
    # Backfill existing rows as "uploaded"
    op.execute("UPDATE videos SET status = 'uploaded' WHERE status IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('videos', schema=None) as batch_op:
        batch_op.drop_column('status')
