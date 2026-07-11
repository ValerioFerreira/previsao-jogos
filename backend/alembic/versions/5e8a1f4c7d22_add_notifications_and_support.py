"""add notifications + support domains

Revision ID: 5e8a1f4c7d22
Revises: 3f7d9b2c4e11
Create Date: 2026-07-11 01:10:00.000000
"""
from typing import Sequence, Union

from alembic import op

from app.db.models import Base

# revision identifiers, used by Alembic.
revision: str = '5e8a1f4c7d22'
down_revision: Union[str, None] = '3f7d9b2c4e11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ["app_notifications", "app_support_tickets"]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in _TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in reversed(_TABLES)]
    Base.metadata.drop_all(bind=bind, tables=tables)
