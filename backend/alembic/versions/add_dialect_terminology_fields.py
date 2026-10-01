"""add dialect and terminology fields

Revision ID: add_dialect_terminology_fields
Revises: add_transcript_pipeline_states
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_dialect_terminology_fields'
down_revision: Union[str, Sequence[str], None] = 'add_transcript_pipeline_states'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to transcripts table
    op.add_column('transcripts', sa.Column('dialect_selected', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('terminology_applied', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('transcripts', sa.Column('terminology_dictionary_used', sa.Text(), nullable=True))
    
    # Create terminology_dictionaries table
    op.create_table(
        'terminology_dictionaries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('entries_json', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_terminology_dictionaries_user_id', 'terminology_dictionaries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_terminology_dictionaries_user_id', table_name='terminology_dictionaries')
    op.drop_table('terminology_dictionaries')
    op.drop_column('transcripts', 'terminology_dictionary_used')
    op.drop_column('transcripts', 'terminology_applied')
    op.drop_column('transcripts', 'dialect_selected')