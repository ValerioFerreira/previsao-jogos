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
    valid_days: int | None = None  # duração em dias a partir de agora — atalho para valid_to
    first_purchase_only: bool = False
    description: str | None = None
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
    first_purchase_only: bool | None = None
    description: str | None = None
    active: bool | None = None


# ---------- parceiros (afiliados) ----------
class AffiliateRequest(BaseModel):
    name: str
    code: str
    user_id: str | None = None
    commission_pct: Decimal | None = None
    commission_fixed_brl: Decimal | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    cpf: str | None = None  # também usado para validar o acesso à conta demo
    notes: str | None = None
    payment_type: str | None = None  # pf | pj
    discount_pcts: str | None = None  # tier de desconto (5/10/15/20/25) do cupom do parceiro


class AffiliatePatch(BaseModel):
    name: str | None = None
    code: str | None = None  # também atualiza o Coupon vinculado (ver affiliates/service.py::set_affiliate_code)
    commission_pct: Decimal | None = None
    commission_fixed_brl: Decimal | None = None
    status: str | None = None  # pending | active | paused | rejected
    contact_email: str | None = None
    contact_phone: str | None = None
    cpf: str | None = None
    notes: str | None = None
    payment_type: str | None = None  # pf | pj
    discount_pcts: str | None = None  # também atualiza os cupons do parceiro e recalcula commission_pct


class AffiliateApproveRequest(BaseModel):
    code: str | None = None  # se o admin quiser mudar o código sugerido/pedido antes de aprovar


class AffiliateRejectRequest(BaseModel):
    reason: str | None = None


class AffiliateDemoAccessRequest(BaseModel):
    enabled: bool


# ---------- pacotes de crédito ----------
class PackageRequest(BaseModel):
    name: str
    credits: int
    price_brl: Decimal
    bonus_credits: int = 0
    featured_badge: str | None = None
    sort_order: int = 0
    status: str = "ativo"  # ativo | oculto | arquivado


class PackagePatch(BaseModel):
    name: str | None = None
    credits: int | None = None
    price_brl: Decimal | None = None
    bonus_credits: int | None = None
    featured_badge: str | None = None  # mais_vendido|melhor_oferta|oferta_limitada|melhor_para_comecar|melhor_custo_beneficio|null
    sort_order: int | None = None
    status: str | None = None  # ativo | oculto | arquivado — NUNCA delete físico (pedidos antigos dependem do id)


# ---------- settings / banners ----------
class SettingRequest(BaseModel):
    value: dict
    description: str | None = None


class BannerRequest(BaseModel):
    title: str
    body: str | None = None
    image_url: str | None = None
    type: str = "info"
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int = 0
    sort_order: int = 0


class BannerPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    image_url: str | None = None
    type: str | None = None
    active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int | None = None
    sort_order: int | None = None


# ---------- campanhas ----------
class CampaignRequest(BaseModel):
    name: str
    banner_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int = 0
    active: bool = True


class CampaignPatch(BaseModel):
    name: str | None = None
    banner_id: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int | None = None
    active: bool | None = None


# ---------- pagamentos a afiliados ----------
class AffiliatePaymentRequest(BaseModel):
    amount_brl: Decimal
    period_start: datetime | None = None
    period_end: datetime | None = None
    method: str | None = None
    receipt_url: str | None = None
    notes: str | None = None


# ---------- documentos legais ----------
class LegalPublishRequest(BaseModel):
    type: str
    title: str
    body_md: str


# ---------- deep analysis ----------
class MatchDeepAnalysisRequest(BaseModel):
    fixture_id: int
    analyst_name: str
    markdown_content: str


class OkResponse(BaseModel):
    ok: bool = True
    detail: str | None = None
