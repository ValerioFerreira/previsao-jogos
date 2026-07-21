from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, field_validator

from app.core.validators import is_valid_cpf, is_valid_phone, normalize_cpf, normalize_phone

_ALLOWED_DISCOUNT_TIERS = (Decimal(5), Decimal(10), Decimal(15), Decimal(20), Decimal(25))


class TrackClickRequest(BaseModel):
    code: str
    anon_id: str


class PartnerApplicationRequest(BaseModel):
    full_name: str
    cpf: str
    email: EmailStr
    phone: str
    payment_type: str  # pf | pj
    discount_pcts: list[Decimal]
    # Prefixo de texto do código (ex. "VALERIO" em "VALERIO15") — o sufixo numérico do
    # desconto é sempre calculado pelo servidor, nunca vem do cliente (ver
    # affiliates/service.py::resolve_partner_code). None/vazio = sistema sugere sozinho.
    code_prefix: str | None = None
    # Código do parceiro que INDICOU este candidato (via link de indicação de parceiros).
    # O candidato não vê o vínculo; serve só para atrelar parent_affiliate_id (Fase 3).
    ref_partner: str | None = None

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        if not is_valid_cpf(v):
            raise ValueError("CPF inválido.")
        return normalize_cpf(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not is_valid_phone(v):
            raise ValueError("Telefone inválido.")
        return normalize_phone(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if " " not in v:
            raise ValueError("Informe o nome completo.")
        return v

    @field_validator("payment_type")
    @classmethod
    def _payment_type(cls, v: str) -> str:
        if v not in ("pf", "pj"):
            raise ValueError("Forma de pagamento deve ser 'pf' ou 'pj'.")
        return v

    @field_validator("discount_pcts")
    @classmethod
    def _discount_pcts(cls, v: list[Decimal]) -> list[Decimal]:
        if not v or len(v) > 3:
            raise ValueError("Escolha de 1 a 3 opções de desconto.")
        for tier in v:
            if tier not in _ALLOWED_DISCOUNT_TIERS:
                raise ValueError("Desconto deve ser 5, 10, 15, 20 ou 25.")
        return list(set(v))


class PartnerApplicationResponse(BaseModel):
    ok: bool = True
    message: str = "Solicitação enviada. Entraremos em contato em breve."


class CodeSuggestionResponse(BaseModel):
    prefix: str
    code: str


class AttachSignupRequest(BaseModel):
    anon_id: str


class PortalStats(BaseModel):
    code: str
    link: str
    clicks: int
    signups: int
    buyers: int
    revenue_brl: str
    commission_due_brl: str
    commission_paid_brl: str


class TimeseriesPoint(BaseModel):
    bucket: str  # "2026-07-16" (day) ou "2026-07" (month)
    clicks: int
    conversions: int
    revenue_brl: str
    commission_brl: str


class TimeseriesResponse(BaseModel):
    granularity: str
    items: list[TimeseriesPoint]


# --- Cupom promocional solicitado pelo parceiro (analisado pelo admin) ---

class CouponRequestCreate(BaseModel):
    requested_code: str
    discount_pct: int

    @field_validator("requested_code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not (1 <= len(v) <= 12):
            raise ValueError("O nome do cupom deve ter de 1 a 12 caracteres.")
        if not v.isalnum():
            raise ValueError("O nome do cupom deve conter apenas letras e números.")
        return v

    @field_validator("discount_pct")
    @classmethod
    def _pct(cls, v: int) -> int:
        # orçamento de 30 pontos: desconto ao usuário + comissão ao parceiro = 30.
        if not (1 <= v <= 29):
            raise ValueError("O desconto deve ser de 1% a 29%.")
        return v


class CouponRequestItem(BaseModel):
    id: str
    requested_code: str
    discount_pct: Decimal
    status: str
    limit_type: str | None = None
    limit_days: int | None = None
    limit_revenue_brl: Decimal | None = None
    rejection_reason: str | None = None
    coupon_code: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class ReferredPartner(BaseModel):
    id: str
    name: str
    code: str
    status: str
    users_count: int              # usuários atrelados (compradores via cupons do indicado)
    revenue_brl: str              # faturamento gerado pelo indicado
    override_due_brl: str         # quanto o sistema deve ao indicador por este indicado


class ReferredPartnersResponse(BaseModel):
    override_pct: Decimal
    total_override_due_brl: str
    items: list[ReferredPartner]
