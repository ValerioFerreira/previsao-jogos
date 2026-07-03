"""Enums de domínio (armazenados como VARCHAR portável — native_enum=False nos modelos)."""
from __future__ import annotations

import enum


class UserStatus(str, enum.Enum):
    pending_verification = "pending_verification"
    active = "active"
    blocked = "blocked"
    deleted = "deleted"


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"
    superadmin = "superadmin"


class OtpPurpose(str, enum.Enum):
    email_verify = "email_verify"
    password_reset = "password_reset"


class AuthEventType(str, enum.Enum):
    register = "register"
    otp_sent = "otp_sent"
    otp_verified = "otp_verified"
    otp_failed = "otp_failed"
    login_success = "login_success"
    login_failed = "login_failed"
    logout = "logout"
    password_set = "password_set"
    password_reset = "password_reset"
    account_locked = "account_locked"
    token_refreshed = "token_refreshed"


class LegalDocumentType(str, enum.Enum):
    terms = "terms"
    privacy = "privacy"
    lgpd = "lgpd"
    credits_policy = "credits_policy"
    promo_regulation = "promo_regulation"


class CreditTxType(str, enum.Enum):
    purchase = "purchase"
    bonus = "bonus"
    promo_credit = "promo_credit"
    reservation = "reservation"
    reservation_release = "reservation_release"
    consumption = "consumption"
    refund = "refund"
    chargeback = "chargeback"
    manual_adjustment = "manual_adjustment"
    cashback = "cashback"


class CreditTxStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    reversed = "reversed"


class PaymentProvider(str, enum.Enum):
    mock = "mock"
    asaas = "asaas"
    mercadopago = "mercadopago"
    pagarme = "pagarme"
    stripe = "stripe"


class PaymentStatus(str, enum.Enum):
    created = "created"
    pending = "pending"
    paid = "paid"
    failed = "failed"
    canceled = "canceled"
    refunded = "refunded"


class AnalysisType(str, enum.Enum):
    independent = "independent"
    future_match = "future_match"


class AnalysisStatus(str, enum.Enum):
    generated = "generated"
    consumed = "consumed"        # crédito consumido (independente ou aposta vencedora)
    reserved = "reserved"        # crédito reservado (partida futura, aguardando aposta/liquidação)


class BetStatus(str, enum.Enum):
    awaiting_start = "awaiting_start"
    in_progress = "in_progress"
    awaiting_settlement = "awaiting_settlement"
    won = "won"
    lost = "lost"
    credit_consumed = "credit_consumed"
    credit_refunded = "credit_refunded"
    canceled = "canceled"


class SettlementOutcome(str, enum.Enum):
    won = "won"
    lost = "lost"
    void = "void"


class PromotionType(str, enum.Enum):
    refund_if_lose = "refund_if_lose"   # "Só Paga se Acertar"
    bonus_credit = "bonus_credit"
    coupon = "coupon"
    cashback = "cashback"
    referral = "referral"
    seasonal = "seasonal"
