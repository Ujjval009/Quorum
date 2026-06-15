"""add updated_at to chat_messages

Revision ID: f3c52699384a
Revises: 8e750286004e
Create Date: 2026-06-09 09:52:22.619026

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3c52699384a'
down_revision: Union[str, None] = '8e750286004e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('chat_messages', 'updated_at')
