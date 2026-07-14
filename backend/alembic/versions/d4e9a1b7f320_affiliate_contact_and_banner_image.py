"""add affiliate contact_email/contact_phone and banner image_url

Revision ID: d4e9a1b7f320
Revises: c4f7e2a891bd
Create Date: 2026-07-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e9a1b7f320'
down_revision: Union[str, None] = 'c4f7e2a891bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("app_affiliates", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("app_affiliates", sa.Column("contact_phone", sa.String(40), nullable=True))
    op.add_column("app_banners", sa.Column("image_url", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("app_banners", "image_url")
    op.drop_column("app_affiliates", "contact_phone")
    op.drop_column("app_affiliates", "contact_email")
