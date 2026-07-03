"""Aposta promocional ("Aposta Escolhida") — IMUTÁVEL após confirmação, com máquina de
estados e liquidação automática pós-jogo. A odd combinada nunca ultrapassa o teto (2.00)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import BetStatus, SettlementOutcome


class Bet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_bets"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_analyses.id", ondelete="RESTRICT"), unique=True, index=True
    )
    fixture_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    match_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    combined_odd: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)  # ≤ 2.000
    status: Mapped[BetStatus] = mapped_column(
        enum_type(BetStatus), default=BetStatus.awaiting_start, nullable=False, index=True
    )
    # reserva de crédito associada e o lançamento que a resolveu (consumo/estorno)
    reserved_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_credit_transactions.id", ondelete="SET NULL"), nullable=True
    )
    resolution_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_credit_transactions.id", ondelete="SET NULL"), nullable=True
    )
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_promotions.id", ondelete="SET NULL"), nullable=True
    )

    selections: Mapped[list["BetSelection"]] = relationship(
        back_populates="bet", cascade="all, delete-orphan"
    )
    settlement: Mapped["BetSettlement | None"] = relationship(
        back_populates="bet", uselist=False, cascade="all, delete-orphan"
    )


class BetSelection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mercado escolhido dentro da aposta (imutável). Odd individual do momento da análise."""
    __tablename__ = "app_bet_selections"

    bet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_bets.id", ondelete="CASCADE"), index=True)
    market_key: Mapped[str] = mapped_column(String(80), nullable=False)   # ex.: escanteios.total.over.9.5
    market_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    selection: Mapped[str] = mapped_column(String(80), nullable=False)    # ex.: over
    odd: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    snapshot_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # recorte do snapshot p/ liquidação

    bet: Mapped["Bet"] = relationship(back_populates="selections")


class BetSettlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Liquidação automática pós-jogo (após delay de segurança), via API-Football."""
    __tablename__ = "app_bet_settlements"

    bet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_bets.id", ondelete="CASCADE"), unique=True, index=True
    )
    safety_delay_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[SettlementOutcome | None] = mapped_column(enum_type(SettlementOutcome), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    api_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    bet: Mapped["Bet"] = relationship(back_populates="settlement")
