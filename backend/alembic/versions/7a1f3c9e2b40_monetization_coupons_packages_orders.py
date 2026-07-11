"""monetization: cupons tipados, selos de pacote, cupom/afiliado/NF no pedido

Revision ID: 7a1f3c9e2b40
Revises: 360b5c6c7be5
Create Date: 2026-07-10 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.base import JSONB, enum_type
from app.domains.enums import CouponDiscountType, PackageBadge

# revision identifiers, used by Alembic.
revision: str = '7a1f3c9e2b40'
down_revision: Union[str, None] = '360b5c6c7be5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    op.add_column("app_coupons", sa.Column("discount_type", enum_type(CouponDiscountType), nullable=True))
    op.add_column("app_coupons", sa.Column("discount_value", _MONEY, nullable=True))
    op.add_column("app_coupons", sa.Column("bonus_credits", sa.Integer(), nullable=True))
    op.add_column("app_coupons", sa.Column("min_purchase_brl", _MONEY, nullable=True))
    op.add_column("app_coupons", sa.Column("package_id", sa.Uuid(), sa.ForeignKey(
        "app_credit_packages.id", ondelete="SET NULL"), nullable=True))
    op.add_column("app_coupons", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_coupons", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))

    op.add_column("app_credit_packages", sa.Column("featured_badge", enum_type(PackageBadge), nullable=True))
    op.add_column("app_credit_packages", sa.Column(
        "sort_order", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("app_payment_orders", sa.Column("coupon_id", sa.Uuid(), sa.ForeignKey(
        "app_coupons.id", ondelete="SET NULL"), nullable=True))
    op.add_column("app_payment_orders", sa.Column("affiliate_attribution_id", sa.Uuid(), nullable=True))
    op.add_column("app_payment_orders", sa.Column("invoice_url", sa.String(500), nullable=True))
    op.add_column("app_payment_orders", sa.Column("invoice_status", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("app_payment_orders", "invoice_status")
    op.drop_column("app_payment_orders", "invoice_url")
    op.drop_column("app_payment_orders", "affiliate_attribution_id")
    op.drop_column("app_payment_orders", "coupon_id")

    op.drop_column("app_credit_packages", "sort_order")
    op.drop_column("app_credit_packages", "featured_badge")

    op.drop_column("app_coupons", "valid_to")
    op.drop_column("app_coupons", "valid_from")
    op.drop_column("app_coupons", "package_id")
    op.drop_column("app_coupons", "min_purchase_brl")
    op.drop_column("app_coupons", "bonus_credits")
    op.drop_column("app_coupons", "discount_type")
