"""merge transcript pipeline and video status branches

Revision ID: 88465a932734
Revises: a1b2c3d4e5f6, add_dialect_terminology_fields
Create Date: 2026-10-01 19:34:52.401972

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88465a932734'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'add_dialect_terminology_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
