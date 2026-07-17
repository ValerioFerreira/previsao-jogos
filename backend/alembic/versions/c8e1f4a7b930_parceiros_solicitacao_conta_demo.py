"""programa de parceiros: solicitação/aprovação, cupom↔afiliado, conta demo

Revision ID: c8e1f4a7b930
Revises: b6d8e0f1a3c5
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8e1f4a7b930'
down_revision: Union[str, None] = 'b6d8e0f1a3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_affiliates", sa.Column("payment_type", sa.String(10), nullable=True))
    op.add_column("app_affiliates", sa.Column("discount_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("app_affiliates", sa.Column(
        "demo_access_enabled", sa.Boolean, nullable=False, server_default=sa.true()
    ))

    op.add_column("app_coupons", sa.Column("affiliate_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_app_coupons_affiliate_id", "app_coupons", "app_affiliates",
        ["affiliate_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("app_users", sa.Column(
        "is_demo", sa.Boolean, nullable=False, server_default=sa.false()
    ))

    op.create_table(
        "app_demo_access_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("affiliate_id", sa.Uuid(), sa.ForeignKey("app_affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cpf_used", sa.String(11), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_app_demo_access_logs_affiliate_id", "app_demo_access_logs", ["affiliate_id"])


def downgrade() -> None:
    op.drop_index("ix_app_demo_access_logs_affiliate_id", table_name="app_demo_access_logs")
    op.drop_table("app_demo_access_logs")
    op.drop_column("app_users", "is_demo")
    op.drop_constraint("fk_app_coupons_affiliate_id", "app_coupons", type_="foreignkey")
    op.drop_column("app_coupons", "affiliate_id")
    op.drop_column("app_affiliates", "demo_access_enabled")
    op.drop_column("app_affiliates", "discount_pct")
    op.drop_column("app_affiliates", "payment_type")
