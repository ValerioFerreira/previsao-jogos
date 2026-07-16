"""add invoice_provider_id and invoice_number to app_payment_orders (NFE.io)

Revision ID: f7c1b2e9d4a3
Revises: e1f2a3b4c5d6
Create Date: 2026-07-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7c1b2e9d4a3'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_payment_orders", sa.Column(
        "invoice_provider_id", sa.String(120), nullable=True))
    op.create_index(
        "ix_app_payment_orders_invoice_provider_id", "app_payment_orders",
        ["invoice_provider_id"])
    op.add_column("app_payment_orders", sa.Column(
        "invoice_number", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("app_payment_orders", "invoice_number")
    op.drop_index("ix_app_payment_orders_invoice_provider_id", table_name="app_payment_orders")
    op.drop_column("app_payment_orders", "invoice_provider_id")
