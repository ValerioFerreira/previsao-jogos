"""Schemas do Painel Administrativo."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------- usuários ----------
class AdminUserItem(BaseModel):
    id: str
    full_name: str
    email: str
    cpf: str
    phone: str
    status: str
    role: str
    created_at: datetime
    last_login_at: datetime | None
    available_balance: Decimal | None = None
    reserved_balance: Decimal | None = None


class AdminUsersPage(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int
    offset: int


class BlockRequest(BaseModel):
    reason: str | None = None


# ---------- créditos (concessão/estorno/ajuste manual) ----------
class CreditAdjustRequest(BaseModel):
    amount: Decimal                 # positivo credita; negativo debita (manual_adjustment)
    kind: str = "manual_adjustment"  # manual_adjustment | bonus | promo_credit | cashback | refund
    reason: str = Field(min_length=3, max_length=300)


# ---------- promoções ----------
class PromotionRequest(BaseModel):
    code: str
    name: str
    type: str
    config: dict | None = None
    max_odd: Decimal | None = None
    active: bool = True


class PromotionPatch(BaseModel):
    name: str | None = None
    config: dict | None = None
    max_odd: Decimal | None = None
    active: bool | None = None


# ---------- cupons ----------
class CouponRequest(BaseModel):
    promotion_id: str
    code: str
    discount_type: str  # percentage | fixed | bonus_credits
    discount_value: Decimal | None = None
    bonus_credits: int | None = None
    min_purchase_brl: Decimal | None = None
    package_id: str | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    active: bool = True


class CouponPatch(BaseModel):
    discount_type: str | None = None
    discount_value: Decimal | None = None
    bonus_credits: int | None = None
    min_purchase_brl: Decimal | None = None
    package_id: str | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    active: bool | None = None


# ---------- afiliados ----------
class AffiliateRequest(BaseModel):
    name: str
    code: str
    user_id: str | None = None
    commission_pct: Decimal | None = None
    commission_fixed_brl: Decimal | None = None
    notes: str | None = None


class AffiliatePatch(BaseModel):
    name: str | None = None
    commission_pct: Decimal | None = None
    commission_fixed_brl: Decimal | None = None
    status: str | None = None  # active | paused
    notes: str | None = None


# ---------- pacotes de crédito ----------
class PackagePatch(BaseModel):
    name: str | None = None
    credits: int | None = None
    price_brl: Decimal | None = None
    bonus_credits: int | None = None
    featured_badge: str | None = None  # mais_vendido | melhor_oferta | oferta_limitada | null p/ remover
    sort_order: int | None = None
    active: bool | None = None


# ---------- settings / banners ----------
class SettingRequest(BaseModel):
    value: dict
    description: str | None = None


class BannerRequest(BaseModel):
    title: str
    body: str | None = None
    type: str = "info"
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


# ---------- documentos legais ----------
class LegalPublishRequest(BaseModel):
    type: str
    title: str
    body_md: str


class OkResponse(BaseModel):
    ok: bool = True
    detail: str | None = None
