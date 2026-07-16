"""Análise (previsão) com SNAPSHOT IMUTÁVEL + versionamento.

No momento da geração salvamos o snapshot completo (probabilidades, mercados, odds,
indicadores, dados de gráfico) e as versões (algoritmo/dados/hash dos artefatos). O
snapshot NUNCA muda, mesmo que o algoritmo evolua — garante que o histórico mostre
exatamente o que existia quando a análise foi gerada.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import AnalysisStatus, AnalysisType


class Analysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    type: Mapped[AnalysisType] = mapped_column(enum_type(AnalysisType), nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(
        enum_type(AnalysisStatus), default=AnalysisStatus.generated, nullable=False
    )

    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)
    tournament: Mapped[str] = mapped_column(String(120), nullable=False)
    fixture_id: Mapped[int | None] = mapped_column(nullable=True, index=True)  # partida oficial futura

    # versionamento (exigido no spec)
    algo_version: Mapped[str] = mapped_column(String(40), nullable=False)
    data_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # snapshot imutável da previsão completa
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # lançamento de crédito associado (consumo imediato ou reserva) — None quando a
    # análise foi gratuita (Copa do Mundo ou cota diária, ver `is_free`)
    credit_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_credit_transactions.id", ondelete="SET NULL"), nullable=True
    )
    # True = não consumiu/reservou crédito (Copa do Mundo grátis ou a cota diária grátis).
    # Análises gratuitas não têm crédito reservado, por isso não habilitam "Monte sua Aposta".
    is_free: Mapped[bool] = mapped_column(default=False, nullable=False)


class FreeDailyUse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Registro da 'análise grátis do dia' de um usuário — 1 por dia, garantido pela
    unique constraint (não por lógica de aplicação, que teria corrida em concorrência)."""
    __tablename__ = "app_free_daily_uses"
    __table_args__ = (UniqueConstraint("user_id", "used_on", name="uq_free_daily_use_user_day"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    used_on: Mapped[date] = mapped_column(Date, nullable=False)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_analyses.id", ondelete="SET NULL"), nullable=True
    )
