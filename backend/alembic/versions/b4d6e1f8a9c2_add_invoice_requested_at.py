"""add invoice_requested_at to app_payment_orders (nota fiscal sob demanda)

Revision ID: b4d6e1f8a9c2
Revises: 5e8a1f4c7d22
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4d6e1f8a9c2'
down_revision: Union[str, None] = '5e8a1f4c7d22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_payment_orders", sa.Column(
        "invoice_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("app_payment_orders", "invoice_requested_at")
