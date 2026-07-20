from __future__ import annotations

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
