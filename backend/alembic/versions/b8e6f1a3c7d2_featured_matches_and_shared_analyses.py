"""partidas em destaque (home) + análises compartilhadas com token público

Ver app/domains/admin/models.py (FeaturedMatch, SharedAnalysis).

Revision ID: b8e6f1a3c7d2
Revises: d3f2c3d4e5f6
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.base import JSONB

revision: str = "b8e6f1a3c7d2"
down_revision: Union[str, None] = "d3f2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_featured_matches",
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="selecao"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_app_featured_matches_fixture_id"), "app_featured_matches", ["fixture_id"], unique=True
    )

    op.create_table(
        "app_shared_analyses",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=True),
        sa.Column("home_team", sa.String(length=160), nullable=False),
        sa.Column("away_team", sa.String(length=160), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="selecao"),
        sa.Column("tournament", sa.String(length=160), nullable=False),
        sa.Column("neutral", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("match_date", sa.String(length=40), nullable=True),
        sa.Column("league_name", sa.String(length=160), nullable=True),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_shared_analyses_token"), "app_shared_analyses", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_shared_analyses_token"), table_name="app_shared_analyses")
    op.drop_table("app_shared_analyses")
    op.drop_index(op.f("ix_app_featured_matches_fixture_id"), table_name="app_featured_matches")
    op.drop_table("app_featured_matches")
