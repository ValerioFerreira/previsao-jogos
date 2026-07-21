"""Carteira de créditos e o LEDGER (fonte de verdade do saldo).

Regra inegociável: o saldo NUNCA é alterado diretamente. Toda mudança é um lançamento
(CreditTransaction) escrito na MESMA transação que atualiza os saldos cacheados da carteira.
Cada movimento tem `idempotency_key` única para garantir que webhooks/retries não dupliquem.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import CreditTxStatus, CreditTxType

_MONEY = Numeric(18, 2)


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_wallets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), unique=True, index=True
    )
    # saldos cacheados, derivados do ledger (atualizados na mesma transação do lançamento)
    available_balance: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)
    reserved_balance: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)
    # saldo de créditos PROMOCIONAIS (ex.: 5 do cupom de convite). Consumidos SEMPRE antes
    # do saldo pago e SEMPRE de forma imediata — nunca entram em reserva, logo não habilitam
    # a "Aposta Escolhida". O crédito diário promocional (1/dia, não acumula) é servido pela
    # cota FreeDailyUse e não passa por aqui.
    promo_balance: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)

    transactions: Mapped[list["CreditTransaction"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class CreditTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_credit_transactions"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_wallets.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[CreditTxType] = mapped_column(enum_type(CreditTxType), nullable=False)
    status: Mapped[CreditTxStatus] = mapped_column(
        enum_type(CreditTxStatus), default=CreditTxStatus.completed, nullable=False
    )
    # valores assinados; reserved_delta move entre disponível e reservado; promo_delta move
    # o saldo promocional (independente de available/reserved)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    reserved_delta: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)
    promo_delta: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    reserved_after: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    promo_after: Mapped[Decimal] = mapped_column(_MONEY, default=0, nullable=False)

    # rastreabilidade / origem
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)  # payment_order|bet|analysis|promotion|admin
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )  # admin, quando manual

    wallet: Mapped["Wallet"] = relationship(back_populates="transactions")
