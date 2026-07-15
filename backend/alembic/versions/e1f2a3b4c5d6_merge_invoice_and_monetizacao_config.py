"""merge heads: invoice_requested_at (nota fiscal) + monetização configurável/indicação

Revision ID: e1f2a3b4c5d6
Revises: b4d6e1f8a9c2, d4e9a1b7f320
Create Date: 2026-07-15 00:00:00.000000
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = ('b4d6e1f8a9c2', 'd4e9a1b7f320')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
