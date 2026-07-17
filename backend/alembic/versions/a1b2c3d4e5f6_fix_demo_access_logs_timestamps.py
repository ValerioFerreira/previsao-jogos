"""fix app_demo_access_logs: created_at/updated_at sem server_default (bug da migration anterior)

A tabela foi criada com `op.create_table` manual, sem `server_default=now()` nas colunas
de timestamp — diferente do padrão usado em outras migrations do domínio (ver
3f7d9b2c4e11_add_affiliates_and_campaigns.py, que usa `Base.metadata.create_all`, que já
aplica o server_default do TimestampMixin corretamente). Sem o default no banco, todo
INSERT (sem informar created_at/updated_at explicitamente, como o ORM faz) violava
NOT NULL em produção.

Revision ID: a1b2c3d4e5f6
Revises: c8e1f4a7b930
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c8e1f4a7b930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("app_demo_access_logs", "created_at", server_default=sa.text("now()"))
    op.alter_column("app_demo_access_logs", "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    op.alter_column("app_demo_access_logs", "created_at", server_default=None)
    op.alter_column("app_demo_access_logs", "updated_at", server_default=None)
