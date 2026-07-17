"""Rastreamento de clique/atribuição + cálculo de comissão. Comissão só é calculada
quando o pedido é confirmado (chamado a partir de payments/service._credit_if_paid),
e só uma vez por PaymentOrder (unique em AffiliateCommission.order_id)."""
from __future__ import annotations

import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.affiliates import schemas
from app.domains.affiliates.models import Affiliate, AffiliateAttribution, AffiliateCommission
from app.domains.enums import PartnerPaymentType

_DEFAULT_ATTRIBUTION_DAYS = 30
_CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
COMMISSION_BUDGET_PCT = Decimal(30)


def _attribution_window_days(db: Session) -> int:
    from app.domains.admin.models import PlatformSetting
    s = db.execute(select(PlatformSetting).where(
        PlatformSetting.key == "affiliate_attribution_days")).scalar_one_or_none()
    if s and s.value and isinstance(s.value, dict) and "days" in s.value:
        try:
            return int(s.value["days"])
        except (TypeError, ValueError):
            pass
    return _DEFAULT_ATTRIBUTION_DAYS


def _generate_affiliate_code(db: Session, full_name: str) -> str:
    """Código curto derivado do nome + sufixo aleatório (mesmo padrão de
    auth/service.py::_generate_referral_code) — nunca colide por natureza."""
    first_name = (full_name.split() or ["parceiro"])[0]
    ascii_name = unicodedata.normalize("NFKD", first_name).encode("ascii", "ignore").decode("ascii")
    prefix = "".join(ch for ch in ascii_name.lower() if ch.isalnum())[:10] or "parceiro"
    for _ in range(20):
        suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        code = f"{prefix}{suffix}"
        if db.execute(select(Affiliate.id).where(Affiliate.code == code)).scalar_one_or_none() is None:
            return code
    raise RuntimeError("Não foi possível gerar um código de parceiro único.")


def apply_for_partnership(db: Session, data: "schemas.PartnerApplicationRequest") -> Affiliate:
    """Solicitação pública de parceria — nasce `pending`, sem User/Coupon (só criados na
    aprovação, ver admin/service.py::approve_affiliate)."""
    dup = db.execute(select(Affiliate).where(
        (Affiliate.cpf == data.cpf) | (func.lower(Affiliate.contact_email) == data.email.lower())
    )).scalars().all()
    for a in dup:
        if a.status in ("pending", "active", "paused"):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                detail="Já existe uma solicitação ou parceria com este CPF/e-mail.")
    code = _generate_affiliate_code(db, data.full_name)
    affiliate = Affiliate(
        name=data.full_name, code=code, status="pending",
        commission_pct=COMMISSION_BUDGET_PCT - data.discount_pct, discount_pct=data.discount_pct,
        payment_type=PartnerPaymentType(data.payment_type),
        cpf=data.cpf, contact_email=data.email.lower(), contact_phone=data.phone,
    )
    db.add(affiliate)
    db.flush()
    return affiliate


def track_click(db: Session, code: str, anon_id: str, user_id: uuid.UUID | None = None) -> AffiliateAttribution | None:
    affiliate = db.execute(select(Affiliate).where(
        Affiliate.code == code.strip().lower(), Affiliate.status == "active")).scalar_one_or_none()
    if affiliate is None:
        return None
    now = datetime.now(timezone.utc)
    days = _attribution_window_days(db)
    attr = AffiliateAttribution(
        affiliate_id=affiliate.id, user_id=user_id, anon_id=anon_id,
        attributed_at=now, expires_at=now + timedelta(days=days),
    )
    db.add(attr)
    return attr


def attach_user_on_signup(db: Session, anon_id: str, user_id: uuid.UUID) -> None:
    """Liga a atribuição anônima (clique pré-cadastro) à conta recém-criada."""
    if not anon_id:
        return
    attrs = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.anon_id == anon_id, AffiliateAttribution.user_id.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().all()
    for a in attrs:
        a.user_id = user_id


def _active_attribution_for_order(db: Session, user_id: uuid.UUID, paid_at: datetime) -> AffiliateAttribution | None:
    rows = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.user_id == user_id, AffiliateAttribution.converted_at.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().all()
    for a in rows:
        if a.expires_at is None or a.expires_at >= paid_at:
            return a
    return None


def commission_for_order(db: Session, order) -> AffiliateCommission | None:
    """Chamado quando um PaymentOrder é confirmado — calcula e registra a comissão do
    afiliado (se houver atribuição válida dentro da janela), independentemente de o
    pedido ter usado cupom ou não."""
    existing = db.execute(select(AffiliateCommission).where(
        AffiliateCommission.order_id == order.id)).scalar_one_or_none()
    if existing is not None:
        return existing

    attr = _active_attribution_for_order(db, order.user_id, order.paid_at or datetime.now(timezone.utc))
    if attr is None:
        return None
    affiliate = db.get(Affiliate, attr.affiliate_id)
    if affiliate is None or affiliate.status != "active":
        return None

    amount = Decimal("0.00")
    if affiliate.commission_pct:
        amount += (Decimal(order.amount_brl) * Decimal(affiliate.commission_pct) / Decimal(100))
    if affiliate.commission_fixed_brl:
        amount += Decimal(affiliate.commission_fixed_brl)
    if amount <= 0:
        return None

    attr.converted_at = datetime.now(timezone.utc)
    order.affiliate_attribution_id = attr.id
    commission = AffiliateCommission(affiliate_id=affiliate.id, order_id=order.id,
                                     amount_brl=amount.quantize(Decimal("0.01")), status="devida")
    db.add(commission)
    return commission


def attach_checkout_attribution(db: Session, user_id: uuid.UUID, affiliate_id: uuid.UUID) -> AffiliateAttribution:
    """Chamado quando um cupom de parceiro (Coupon.affiliate_id) é usado no checkout —
    atribui a venda ao parceiro imediatamente, sem depender de clique prévio em
    `?ref=código` (reaproveita uma atribuição em aberto do mesmo usuário/parceiro, se
    houver, em vez de acumular atribuições redundantes)."""
    existing = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.user_id == user_id, AffiliateAttribution.affiliate_id == affiliate_id,
        AffiliateAttribution.converted_at.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().first()
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    days = _attribution_window_days(db)
    attr = AffiliateAttribution(
        affiliate_id=affiliate_id, user_id=user_id, anon_id=None,
        attributed_at=now, expires_at=now + timedelta(days=days),
    )
    db.add(attr)
    db.flush()
    return attr


def validate_demo_cpf(db: Session, cpf: str) -> Affiliate | None:
    """Allowlist da conta demo compartilhada — só parceiros ativos com acesso não
    revogado pelo admin (ver DemoAccessLog / auth/service.py::login_demo)."""
    digits = "".join(ch for ch in cpf if ch.isdigit())
    return db.execute(select(Affiliate).where(
        Affiliate.cpf == digits, Affiliate.status == "active", Affiliate.demo_access_enabled.is_(True),
    )).scalar_one_or_none()


def compute_portal_stats(db: Session, affiliate: Affiliate) -> dict:
    """Métricas agregadas do parceiro — reaproveitado pelo portal (`affiliates/router.py`)
    e pela página de detalhe do admin (`admin/service.py::get_affiliate_detail`)."""
    from app.domains.payments.models import PaymentOrder

    clicks = db.execute(select(func.count(AffiliateAttribution.id)).where(
        AffiliateAttribution.affiliate_id == affiliate.id)).scalar_one()
    signups = db.execute(select(func.count(func.distinct(AffiliateAttribution.user_id))).where(
        AffiliateAttribution.affiliate_id == affiliate.id, AffiliateAttribution.user_id.is_not(None),
    )).scalar_one()
    buyers = db.execute(select(func.count(AffiliateCommission.id)).where(
        AffiliateCommission.affiliate_id == affiliate.id)).scalar_one()
    revenue = db.execute(
        select(func.coalesce(func.sum(PaymentOrder.amount_brl), 0))
        .join(AffiliateCommission, AffiliateCommission.order_id == PaymentOrder.id)
        .where(AffiliateCommission.affiliate_id == affiliate.id)
    ).scalar_one()
    due = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == affiliate.id, AffiliateCommission.status == "devida")).scalar_one()
    paid = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == affiliate.id, AffiliateCommission.status == "paga")).scalar_one()

    return {
        "code": affiliate.code, "link": f"{settings.frontend_base_url}/?ref={affiliate.code}",
        "clicks": clicks, "signups": signups, "buyers": buyers,
        "revenue_brl": str(revenue), "commission_due_brl": str(due), "commission_paid_brl": str(paid),
    }
