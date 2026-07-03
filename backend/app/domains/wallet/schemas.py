"""Schemas da carteira."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class WalletResponse(BaseModel):
    available_balance: Decimal
    reserved_balance: Decimal
    currency: str = "credits"


class TransactionItem(BaseModel):
    id: str
    type: str
    status: str
    amount: Decimal
    reserved_delta: Decimal
    balance_after: Decimal
    reserved_after: Decimal
    description: str | None
    reference_type: str | None
    created_at: datetime


class TransactionsPage(BaseModel):
    items: list[TransactionItem]
    total: int
    limit: int
    offset: int
