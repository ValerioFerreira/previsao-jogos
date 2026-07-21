"""afiliado: indicação de parceiros (parent) + comissão override (kind/source/unique composto)

Ver app/domains/affiliates/models.py.

Revision ID: d3f2c3d4e5f6
Revises: d2f1b2c3d4e5
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f2c3d4e5f6"
down_revision: Union[str, None] = "d2f1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Indicação de parceiros (um nível): quem indicou este parceiro.
    op.add_column("app_affiliates", sa.Column("parent_affiliate_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_app_affiliates_parent_affiliate_id"),
        "app_affiliates", ["parent_affiliate_id"], unique=False,
    )
    op.create_foreign_key(
        "fk_app_affiliates_parent_affiliate",
        "app_affiliates", "app_affiliates",
        ["parent_affiliate_id"], ["id"], ondelete="SET NULL",
    )

    # Comissão: kind (direct|override) + source (parceiro-filho que gerou o override).
    op.add_column(
        "app_affiliate_commissions",
        sa.Column(
            "kind",
            sa.Enum("direct", "override", name="commissionkind", native_enum=False, length=40),
            nullable=False, server_default="direct",
        ),
    )
    op.alter_column("app_affiliate_commissions", "kind", server_default=None)
    op.add_column("app_affiliate_commissions", sa.Column("source_affiliate_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_app_affiliate_commissions_source_affiliate_id"),
        "app_affiliate_commissions", ["source_affiliate_id"], unique=False,
    )
    op.create_foreign_key(
        "fk_app_affiliate_commissions_source_affiliate",
        "app_affiliate_commissions", "app_affiliates",
        ["source_affiliate_id"], ["id"], ondelete="SET NULL",
    )

    # Uma ordem passa a poder ter 2 comissões (direta + override): troca o unique(order_id)
    # por um unique composto (order_id, affiliate_id) e mantém um índice simples em order_id.
    op.drop_constraint("app_affiliate_commissions_order_id_key", "app_affiliate_commissions", type_="unique")
    op.create_index(
        op.f("ix_app_affiliate_commissions_order_id"),
        "app_affiliate_commissions", ["order_id"], unique=False,
    )
    op.create_unique_constraint(
        "uq_commission_order_affiliate", "app_affiliate_commissions", ["order_id", "affiliate_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_commission_order_affiliate", "app_affiliate_commissions", type_="unique")
    op.drop_index(op.f("ix_app_affiliate_commissions_order_id"), table_name="app_affiliate_commissions")
    op.create_unique_constraint("app_affiliate_commissions_order_id_key", "app_affiliate_commissions", ["order_id"])
    op.drop_constraint("fk_app_affiliate_commissions_source_affiliate", "app_affiliate_commissions", type_="foreignkey")
    op.drop_index(op.f("ix_app_affiliate_commissions_source_affiliate_id"), table_name="app_affiliate_commissions")
    op.drop_column("app_affiliate_commissions", "source_affiliate_id")
    op.drop_column("app_affiliate_commissions", "kind")
    op.drop_constraint("fk_app_affiliates_parent_affiliate", "app_affiliates", type_="foreignkey")
    op.drop_index(op.f("ix_app_affiliates_parent_affiliate_id"), table_name="app_affiliates")
    op.drop_column("app_affiliates", "parent_affiliate_id")
