"""Pagamentos: pacotes de crédito, ordens, webhooks (idempotentes) e cartões tokenizados.
NUNCA armazenar PAN/CVV — apenas o token do gateway. Gateway trocável via adapter."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import PaymentProvider, PaymentStatus

_MONEY = Numeric(18, 2)


class CreditPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Pacotes de crédito (base: 1 crédito = R$1,00). Suporta bônus/promoções futuras."""
    __tablename__ = "app_credit_packages"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_brl: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    bonus_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PaymentOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_payment_orders"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(enum_type(PaymentProvider), nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_credit_packages.id", ondelete="SET NULL"), nullable=True
    )
    amount_brl: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus), default=PaymentStatus.created, nullable=False
    )
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)  # pix|card|boleto...
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentWebhook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eventos de webhook do gateway — processados de forma idempotente."""
    __tablename__ = "app_payment_webhooks"

    provider: Mapped[PaymentProvider] = mapped_column(enum_type(PaymentProvider), nullable=False)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cartão tokenizado pelo gateway (sem dados sensíveis)."""
    __tablename__ = "app_payment_cards"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(enum_type(PaymentProvider), nullable=False)
    provider_token: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    exp_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
