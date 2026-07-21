"""Programa de parceiros (rótulo em português; nomes internos seguem em inglês —
"affiliate"). Independente de cupom (ver PaymentOrder.coupon_id vs
affiliate_attribution_id em payments/models.py) — a atribuição gera a comissão, o cupom
concede o benefício ao usuário; um pedido pode ter os dois, um só, ou nenhum. Exceção
deliberada: o cupom de um parceiro (Coupon.affiliate_id) atribui a venda automaticamente
no checkout, ver payments/service.py::create_order — mas o CÁLCULO de desconto e de
comissão continua sendo feito por cada domínio de forma independente."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_type
from app.domains.enums import CommissionKind, PartnerPaymentType


class Affiliate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_affiliates"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), unique=True, nullable=True
    )  # conta do parceiro no portal (role=partner) — criada na aprovação, ver affiliates/service.py
    commission_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    commission_fixed_brl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # pending (solicitação aguardando análise) | active | paused | rejected
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # CPF do parceiro — usado hoje para validar o acesso individual à conta demo
    # compartilhada (ver DemoAccessLog / auth/service.py::login_demo).
    cpf: Mapped[str | None] = mapped_column(String(11), nullable=True)

    # Forma de remuneração do parceiro (informativo, negociação de pagamento é externa).
    payment_type: Mapped[PartnerPaymentType | None] = mapped_column(enum_type(PartnerPaymentType), nullable=True)
    # Tier de desconto escolhido na solicitação (5/10/15/20/25) — orçamento de 30 pontos
    # percentuais: comission_pct é derivado como (30 - desconto) na aprovação. Agora suporta até 3 (CSV).
    discount_pcts: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Permite ao admin revogar o acesso deste parceiro específico à conta demo
    # compartilhada, sem precisar bloquear a conta demo inteira.
    demo_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Parceiro que INDICOU este parceiro (um nível só). O indicado não vê o vínculo; o
    # indicador ganha +5% da comissão do indicado (override, custo extra do sistema).
    parent_affiliate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="SET NULL"), index=True, nullable=True
    )


class DemoAccessLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Auditoria de uso da conta demo compartilhada — cada login-demo bem-sucedido grava
    quem (via CPF do parceiro) acessou, para o admin controlar quem tem acesso."""
    __tablename__ = "app_demo_access_logs"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    cpf_used: Mapped[str] = mapped_column(String(11), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AffiliateAttribution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Um clique/atribuição — janela de dias configurável via app_platform_settings."""
    __tablename__ = "app_affiliate_attributions"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    anon_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    attributed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AffiliateCommission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_affiliate_commissions"
    # Uma ordem pode gerar até 2 comissões: a DIRETA (parceiro dono do cupom) e o OVERRIDE
    # (parceiro que o indicou). Por isso o unique agora é composto (order_id, affiliate_id).
    __table_args__ = (UniqueConstraint("order_id", "affiliate_id", name="uq_commission_order_affiliate"),)

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_payment_orders.id", ondelete="CASCADE"), index=True
    )
    amount_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="devida", nullable=False)  # devida|paga
    # direct = comissão do dono do cupom; override = 5% extra ao parceiro que indicou o dono.
    kind: Mapped[CommissionKind] = mapped_column(
        enum_type(CommissionKind), default=CommissionKind.direct, nullable=False
    )
    # no override, o parceiro-filho que gerou a comissão-base (para o admin rastrear a origem).
    source_affiliate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="SET NULL"), index=True, nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_affiliate_payments.id", ondelete="SET NULL"), index=True, nullable=True
    )


class AffiliatePayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Lote de pagamento efetuado a um afiliado, cobrindo um período — permite controlar
    comissões devidas vs efetivamente pagas (cada AffiliateCommission incluída ganha
    payment_id + status='paga')."""
    __tablename__ = "app_affiliate_payments"

    affiliate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_affiliates.id", ondelete="CASCADE"), index=True
    )
    amount_brl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)  # pix|transferencia|...
    receipt_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|paid|canceled
