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
    featured_badge: str | None = None


class CheckoutRequest(BaseModel):
    package_id: str | None = None
    credits: int | None = Field(default=None, ge=1, le=100000)
    coupon_code: str | None = None

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


class OrderListItem(BaseModel):
    order_id: str
    provider: str
    method: str | None
    status: str
    amount_brl: Decimal
    credits: int
    coupon_code: str | None = None
    discount_amount_brl: Decimal | None = None
    checkout: dict | None = None
    invoice_url: str | None = None
    invoice_status: str | None = None
    created_at: str
    paid_at: str | None
