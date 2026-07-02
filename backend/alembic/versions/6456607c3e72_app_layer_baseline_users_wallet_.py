"""app layer baseline (users, wallet, payments, analysis, bets, promotions, legal, admin)

Revision ID: 6456607c3e72
Revises: 
Create Date: 2026-07-02 17:04:37.133925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.models import Base


# revision identifiers, used by Alembic.
revision: str = '6456607c3e72'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _app_tables():
    """Só as tabelas da camada de aplicação (app_*), na ordem de dependência de FK."""
    return [t for t in Base.metadata.sorted_tables if t.name.startswith("app_")]


def upgrade() -> None:
    # Cria toda a camada de aplicação a partir do metadata dos modelos — garante
    # fidelidade exata (JSONB/UUID/variants/constraints) no backend de destino (Postgres).
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=_app_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_app_tables())))
