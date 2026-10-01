"""add transcript pipeline states and metadata

Revision ID: add_transcript_pipeline_states
Revises: e7b5fc44bba9
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_transcript_pipeline_states'
down_revision: Union[str, Sequence[str], None] = 'e7b5fc44bba9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to transcripts table
    op.add_column('transcripts', sa.Column('error_code', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('provider', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('model', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('timestamp_source', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('transcripts', sa.Column('current_stage', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove columns
    op.drop_column('transcripts', 'retry_count')
    op.drop_column('transcripts', 'current_stage')
    op.drop_column('transcripts', 'progress_percent')
    op.drop_column('transcripts', 'timestamp_source')
    op.drop_column('transcripts', 'model')
    op.drop_column('transcripts', 'provider')
    op.drop_column('transcripts', 'error_code')