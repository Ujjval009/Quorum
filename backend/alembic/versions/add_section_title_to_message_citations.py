"""Add section_title to message_citations

Revision ID: 6a7f8e9b1c2d
Revises: f3c52699384a
Create Date: 2026-06-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a7f8e9b1c2d'
down_revision = 'f3c52699384a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add section_title column to message_citations
    op.add_column(
        'message_citations',
        sa.Column('section_title', sa.String(512), nullable=True)
    )


def downgrade() -> None:
    # Remove section_title column from message_citations
    op.drop_column('message_citations', 'section_title')
