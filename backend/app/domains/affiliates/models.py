"""Programa de afiliados/influenciadores. Independente de cupom (ver PaymentOrder.coupon_id
vs affiliate_attribution_id em payments/models.py) — o link atribui a comissão, o cupom
concede o benefício ao usuário; um pedido pode ter os dois, um só, ou nenhum."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Affiliate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_affiliates"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), unique=True, nullable=True
    )  # login do afiliado no portal (opcional)
    commission_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    commission_fixed_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active|paused
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AffiliateAttribution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Um clique/atribuição — janela de dias configurável via app_platform_settings."""
    __tablename__ = "app_affiliate_attributions"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    anon_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    attributed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AffiliateCommission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_affiliate_commissions"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_payment_orders.id", ondelete="CASCADE"), unique=True
    )
    amount_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="devida", nullable=False)  # devida|paga
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
