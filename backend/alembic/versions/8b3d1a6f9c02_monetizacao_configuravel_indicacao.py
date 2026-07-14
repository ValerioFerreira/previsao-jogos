"""monetização configurável: status de pacote, banner priority/sort, cupom 1a-compra+regras,
desconto no pedido, indicação (referral_code+auditoria), pagamentos a afiliados

Revision ID: 8b3d1a6f9c02
Revises: 5e8a1f4c7d22
Create Date: 2026-07-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.base import enum_type
from app.db.models import Base
from app.domains.enums import PackageStatus

# revision identifiers, used by Alembic.
revision: str = '8b3d1a6f9c02'
down_revision: Union[str, None] = '5e8a1f4c7d22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    bind = op.get_bind()

    # --- pacotes: status (ativo/oculto/arquivado) em vez de active bool ---
    op.add_column("app_credit_packages", sa.Column(
        "status", enum_type(PackageStatus), nullable=False, server_default=PackageStatus.ativo.value))
    op.execute("UPDATE app_credit_packages SET status = 'arquivado' WHERE active = false")
    op.drop_column("app_credit_packages", "active")
    # PackageBadge ganhou 2 valores novos (melhor_para_comecar/melhor_custo_beneficio) —
    # a coluna é VARCHAR sem CHECK constraint (native_enum=False, create_constraint=False
    # por padrão no SQLAlchemy 2.0), então nenhuma alteração de schema é necessária pra isso.

    # --- banners: prioridade de campanha + ordem fina ---
    op.add_column("app_banners", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("app_banners", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    # --- cupons: só-primeira-compra + regras em texto livre ---
    op.add_column("app_coupons", sa.Column(
        "first_purchase_only", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("app_coupons", sa.Column("description", sa.String(500), nullable=True))

    # --- pedido: valor do desconto aplicado (auditoria/analytics de cupom) ---
    op.add_column("app_payment_orders", sa.Column(
        "discount_amount_brl", _MONEY, nullable=False, server_default="0"))

    # --- indicação entre usuários (User.referral_code + auditoria em Referral) ---
    op.add_column("app_users", sa.Column("referral_code", sa.String(30), nullable=True))
    op.create_index("ix_app_users_referral_code", "app_users", ["referral_code"], unique=True)

    op.add_column("app_referrals", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("app_referrals", sa.Column("signup_ip", sa.String(64), nullable=True))
    op.add_column("app_referrals", sa.Column("user_agent", sa.String(300), nullable=True))
    op.add_column("app_referrals", sa.Column("signup_source", sa.String(40), nullable=True))

    # --- pagamentos a afiliados: tabela nova + FK em AffiliateCommission ---
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables["app_affiliate_payments"]], checkfirst=True)
    op.add_column("app_affiliate_commissions", sa.Column(
        "payment_id", sa.Uuid(), sa.ForeignKey("app_affiliate_payments.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("app_affiliate_commissions", "payment_id")
    op.drop_table("app_affiliate_payments")

    op.drop_column("app_referrals", "signup_source")
    op.drop_column("app_referrals", "user_agent")
    op.drop_column("app_referrals", "signup_ip")
    op.drop_column("app_referrals", "completed_at")

    op.drop_index("ix_app_users_referral_code", table_name="app_users")
    op.drop_column("app_users", "referral_code")

    op.drop_column("app_payment_orders", "discount_amount_brl")

    op.drop_column("app_coupons", "description")
    op.drop_column("app_coupons", "first_purchase_only")

    op.drop_column("app_banners", "sort_order")
    op.drop_column("app_banners", "priority")

    op.add_column("app_credit_packages", sa.Column("active", sa.Boolean(), nullable=False, server_default="true"))
    op.execute("UPDATE app_credit_packages SET active = false WHERE status = 'arquivado'")
    op.drop_column("app_credit_packages", "status")
