"""Schemas da carteira."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class WalletResponse(BaseModel):
    available_balance: Decimal
    reserved_balance: Decimal
    promo_balance: Decimal = Decimal("0")   # créditos promocionais (consumidos antes do pago)
    currency: str = "credits"


class TransactionItem(BaseModel):
    id: str
    type: str
    status: str
    amount: Decimal
    reserved_delta: Decimal
    promo_delta: Decimal = Decimal("0")
    balance_after: Decimal
    reserved_after: Decimal
    promo_after: Decimal = Decimal("0")
    description: str | None
    reference_type: str | None
    home_team: str | None = None
    away_team: str | None = None
    created_at: datetime


class TransactionsPage(BaseModel):
    items: list[TransactionItem]
    total: int
    limit: int
    offset: int
