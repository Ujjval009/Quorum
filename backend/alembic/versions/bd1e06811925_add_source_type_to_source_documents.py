"""add source_type to source_documents

Revision ID: bd1e06811925
Revises: f3c52699384a
Create Date: 2026-06-09 11:27:15.902259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bd1e06811925'
down_revision: Union[str, None] = 'f3c52699384a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'source_documents',
        sa.Column('source_type', sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f('ix_source_documents_source_type'),
        'source_documents',
        ['source_type'],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_source_documents_source_type'), table_name='source_documents')
    op.drop_column('source_documents', 'source_type')
