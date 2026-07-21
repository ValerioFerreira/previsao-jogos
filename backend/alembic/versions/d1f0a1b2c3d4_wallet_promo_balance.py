"""wallet promo_balance + lançamentos promo no ledger

Saldo de créditos PROMOCIONAIS (consumidos antes do pago, sempre imediatos, nunca
reservados). Ver app/domains/wallet/models.py.

Revision ID: d1f0a1b2c3d4
Revises: 3549706daeb8
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1f0a1b2c3d4"
down_revision: Union[str, None] = "3549706daeb8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT NULL em tabela com linhas: adiciona com server_default p/ backfill, depois remove
    # o default (o modelo usa default Python, sem server_default).
    op.add_column("app_wallets", sa.Column("promo_balance", sa.Numeric(18, 2), nullable=False, server_default="0"))
    op.alter_column("app_wallets", "promo_balance", server_default=None)

    op.add_column("app_credit_transactions", sa.Column("promo_delta", sa.Numeric(18, 2), nullable=False, server_default="0"))
    op.alter_column("app_credit_transactions", "promo_delta", server_default=None)
    op.add_column("app_credit_transactions", sa.Column("promo_after", sa.Numeric(18, 2), nullable=False, server_default="0"))
    op.alter_column("app_credit_transactions", "promo_after", server_default=None)


def downgrade() -> None:
    op.drop_column("app_credit_transactions", "promo_after")
    op.drop_column("app_credit_transactions", "promo_delta")
    op.drop_column("app_wallets", "promo_balance")
