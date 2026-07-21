"""Promoções e campanhas — extensível por `type` + `config jsonb` (sem hardcode).
A promo "Só Paga se Acertar" é uma linha com type=refund_if_lose e max_odd=2.00.
Suporta futuramente cupons, cashback, indicação, bônus e campanhas sazonais."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONB, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import (
    CouponDiscountType,
    CouponLimitType,
    CouponRequestStatus,
    PromotionType,
)


class Promotion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_promotions"

    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[PromotionType] = mapped_column(enum_type(PromotionType), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # regras específicas
    max_odd: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )


class PromotionParticipation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_promotion_participations"

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_promotions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    reference_type: Mapped[str | None] = mapped_column(String(40), nullable=True)   # bet|analysis
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class Coupon(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_coupons"

    promotion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_promotions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    discount_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redemptions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Campos tipados (o CÁLCULO de desconto é independente do de comissão de afiliado —
    # ver PaymentOrder.affiliate_attribution_id no domínio payments/affiliates). Exceção
    # deliberada de atribuição (não de cálculo): quando affiliate_id está setado, este é
    # o "cupom de parceiro" — usá-lo no checkout também atribui a venda ao parceiro para
    # fins de comissão (ver payments/service.py::create_order).
    discount_type: Mapped[CouponDiscountType | None] = mapped_column(
        enum_type(CouponDiscountType), nullable=True
    )
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    bonus_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)  # créditos NORMAIS de bônus
    # créditos PROMOCIONAIS concedidos no resgate (5 no cupom de convite) — vão para
    # wallet.promo_balance, consumidos imediatamente e nunca reservados (ver wallet/models.py)
    promo_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # comissão POR-CUPOM do parceiro (= 30 - desconto). Preenchido nos cupons de parceiro para
    # permitir splits diferentes por cupom (convite vs promocional); fallback = affiliate.commission_pct.
    commission_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    # teto de faturamento PRÉ-DESCONTO (soma dos valores cheios das compras que usaram o cupom).
    # Só nos cupons promocionais limitados por faturamento; atingido o teto, o cupom é desativado.
    revenue_limit_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    min_purchase_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_credit_packages.id", ondelete="SET NULL"), nullable=True
    )
    affiliate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="SET NULL"), nullable=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_purchase_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)  # regras em texto livre p/ admin


class Referral(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Indicação entre usuários (créditos, independente do programa de afiliados — ver
    affiliates/models.py). status: pending (cadastrado, aguardando ativação da conta) |
    completed (bônus já concedido aos dois lados) — reward_config é um SNAPSHOT do
    PlatformSetting 'referral_bonus' no momento do cadastro, pra não mudar retroativamente
    o que já foi prometido se o admin alterar os valores depois."""
    __tablename__ = "app_referrals"

    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_users.id", ondelete="CASCADE"), index=True
    )
    referred_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    reward_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signup_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    signup_source: Mapped[str | None] = mapped_column(String(40), nullable=True)  # link|manual


class PartnerCouponRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Solicitação de CUPOM PROMOCIONAL feita pelo parceiro e analisada pelo admin.

    O parceiro escolhe um nome (≤12 chars) e a % de desconto/ganho (mesmo orçamento de 30
    pontos dos cupons de convite). Só pode haver UMA solicitação `pending` por parceiro por
    vez. O admin aprova definindo prazo (dias) OU teto de faturamento pré-desconto, ou
    rejeita com um motivo — e-mail enviado ao parceiro nos dois casos. Ao aprovar, um
    `Coupon` é criado e referenciado em `coupon_id`."""
    __tablename__ = "app_partner_coupon_requests"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    requested_code: Mapped[str] = mapped_column(String(12), nullable=False)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    status: Mapped[CouponRequestStatus] = mapped_column(
        enum_type(CouponRequestStatus), default=CouponRequestStatus.pending, nullable=False, index=True
    )
    # decisão do admin (aprovação)
    limit_type: Mapped[CouponLimitType | None] = mapped_column(enum_type(CouponLimitType), nullable=True)
    limit_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limit_revenue_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # decisão do admin (rejeição)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), nullable=True
    )
    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_coupons.id", ondelete="SET NULL"), nullable=True
    )
