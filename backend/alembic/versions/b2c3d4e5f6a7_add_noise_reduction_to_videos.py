"""add noise_reduction to videos

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'videos',
        sa.Column('noise_reduction', sa.Boolean(), nullable=True, server_default='false')
    )


def downgrade() -> None:
    op.drop_column('videos', 'noise_reduction')
