"""add app_events table (analytics/funil de conversão)

Revision ID: 9c2e5a7b1d33
Revises: 7a1f3c9e2b40
Create Date: 2026-07-11 00:10:00.000000
"""
from typing import Sequence, Union

from alembic import op

from app.db.models import Base

# revision identifiers, used by Alembic.
revision: str = '9c2e5a7b1d33'
down_revision: Union[str, None] = '7a1f3c9e2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "app_events"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[_TABLE]], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[_TABLE]])
