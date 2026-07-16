"""add cpf to app_affiliates (login do portal do afiliado: email+CPF)

Revision ID: b6d8e0f1a3c5
Revises: a2b4c6d8e0f1
Create Date: 2026-07-16 02:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b6d8e0f1a3c5'
down_revision: Union[str, None] = 'a2b4c6d8e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_affiliates", sa.Column("cpf", sa.String(11), nullable=True))


def downgrade() -> None:
    op.drop_column("app_affiliates", "cpf")
