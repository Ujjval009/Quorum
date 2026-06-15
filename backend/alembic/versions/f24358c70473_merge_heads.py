"""merge heads

Revision ID: f24358c70473
Revises: 6a7f8e9b1c2d, bd1e06811925
Create Date: 2026-06-10 11:07:23.695238

"""
from typing import Sequence, Union



revision: str = 'f24358c70473'
down_revision: Union[str, None] = ('6a7f8e9b1c2d', 'bd1e06811925')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
