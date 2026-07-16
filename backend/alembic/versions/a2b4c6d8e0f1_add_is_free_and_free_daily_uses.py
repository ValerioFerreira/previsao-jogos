"""add is_free to app_analyses + app_free_daily_uses table (Copa do Mundo grátis / 1 análise grátis por dia)

Revision ID: a2b4c6d8e0f1
Revises: f7c1b2e9d4a3
Create Date: 2026-07-16 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.models import Base

# revision identifiers, used by Alembic.
revision: str = 'a2b4c6d8e0f1'
down_revision: Union[str, None] = 'f7c1b2e9d4a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_analyses", sa.Column(
        "is_free", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("app_analyses", "is_free", server_default=None)

    bind = op.get_bind()
    table = Base.metadata.tables["app_free_daily_uses"]
    Base.metadata.create_all(bind=bind, tables=[table], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    table = Base.metadata.tables["app_free_daily_uses"]
    Base.metadata.drop_all(bind=bind, tables=[table])
    op.drop_column("app_analyses", "is_free")
