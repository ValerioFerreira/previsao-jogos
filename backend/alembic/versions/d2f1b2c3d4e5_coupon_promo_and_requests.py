"""cupom: promo_credits/commission_pct/revenue_limit + tabela de solicitação de cupom

Ver app/domains/promotions/models.py (Coupon novos campos + PartnerCouponRequest).

Revision ID: d2f1b2c3d4e5
Revises: d1f0a1b2c3d4
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f1b2c3d4e5"
down_revision: Union[str, None] = "d1f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_coupons", sa.Column("promo_credits", sa.Integer(), nullable=True))
    op.add_column("app_coupons", sa.Column("commission_pct", sa.Numeric(6, 3), nullable=True))
    op.add_column("app_coupons", sa.Column("revenue_limit_brl", sa.Numeric(18, 2), nullable=True))

    op.create_table(
        "app_partner_coupon_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("affiliate_id", sa.Uuid(), nullable=False),
        sa.Column("requested_code", sa.String(length=12), nullable=False),
        sa.Column("discount_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="couponrequeststatus", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column(
            "limit_type",
            sa.Enum("days", "revenue", name="couponlimittype", native_enum=False, length=40),
            nullable=True,
        ),
        sa.Column("limit_days", sa.Integer(), nullable=True),
        sa.Column("limit_revenue_brl", sa.Numeric(18, 2), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("coupon_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["affiliate_id"], ["app_affiliates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coupon_id"], ["app_coupons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_partner_coupon_requests_affiliate_id"),
        "app_partner_coupon_requests", ["affiliate_id"], unique=False,
    )
    op.create_index(
        op.f("ix_app_partner_coupon_requests_status"),
        "app_partner_coupon_requests", ["status"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_app_partner_coupon_requests_status"), table_name="app_partner_coupon_requests")
    op.drop_index(op.f("ix_app_partner_coupon_requests_affiliate_id"), table_name="app_partner_coupon_requests")
    op.drop_table("app_partner_coupon_requests")
    op.drop_column("app_coupons", "revenue_limit_brl")
    op.drop_column("app_coupons", "commission_pct")
    op.drop_column("app_coupons", "promo_credits")
