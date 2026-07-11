"""add affiliates + campaigns domains (afiliados, atribuição, comissão, campanha, A/B)

Revision ID: 3f7d9b2c4e11
Revises: 9c2e5a7b1d33
Create Date: 2026-07-11 00:40:00.000000
"""
from typing import Sequence, Union

from alembic import op

from app.db.models import Base

# revision identifiers, used by Alembic.
revision: str = '3f7d9b2c4e11'
down_revision: Union[str, None] = '9c2e5a7b1d33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = [
    "app_affiliates", "app_affiliate_attributions", "app_affiliate_commissions",
    "app_campaigns", "app_campaign_packages", "app_campaign_coupons", "app_campaign_affiliates",
    "app_experiments", "app_experiment_variants",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in _TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in reversed(_TABLES)]
    Base.metadata.drop_all(bind=bind, tables=tables)
