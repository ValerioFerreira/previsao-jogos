"""Schemas de pagamentos / compra de créditos."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class PackageItem(BaseModel):
    id: str
    name: str
    credits: int
    price_brl: Decimal
    bonus_credits: int
    total_credits: int


class CheckoutRequest(BaseModel):
    package_id: str | None = None
    credits: int | None = Field(default=None, ge=1, le=100000)

    @model_validator(mode="after")
    def _one_of(self):
        if not self.package_id and not self.credits:
            raise ValueError("Informe package_id ou credits.")
        return self


class CheckoutResponse(BaseModel):
    order_id: str
    provider: str
    status: str
    amount_brl: Decimal
    credits: int
    checkout: dict


class OrderResponse(BaseModel):
    order_id: str
    status: str
    amount_brl: Decimal
    credits: int
    available_balance: Decimal | None = None
