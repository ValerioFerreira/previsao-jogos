"""add screenshot incidents table

Revision ID: 360b5c6c7be5
Revises: 6456607c3e72
Create Date: 2026-07-10 22:34:31.180740

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.models import Base

# revision identifiers, used by Alembic.
revision: str = '360b5c6c7be5'
down_revision: Union[str, None] = '6456607c3e72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "app_screenshot_incidents"


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[_TABLE]], checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, tables=[Base.metadata.tables[_TABLE]])
