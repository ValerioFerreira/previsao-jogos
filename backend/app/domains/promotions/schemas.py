"""Schemas do domínio promotions (cupons públicos)."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class CouponValidateRequest(BaseModel):
    code: str
    amount_brl: Decimal
    credits: int
    package_id: str | None = None


class CouponPreview(BaseModel):
    coupon_id: str
    code: str
    discount_type: str | None
    original_amount_brl: Decimal
    final_amount_brl: Decimal
    bonus_credits: int
    promo_credits: int = 0   # créditos PROMOCIONAIS concedidos no resgate (ex.: 5 do convite)
