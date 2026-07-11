"""Rastreamento de clique/atribuição + cálculo de comissão. Comissão só é calculada
quando o pedido é confirmado (chamado a partir de payments/service._credit_if_paid),
e só uma vez por PaymentOrder (unique em AffiliateCommission.order_id)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.affiliates.models import Affiliate, AffiliateAttribution, AffiliateCommission

_DEFAULT_ATTRIBUTION_DAYS = 30


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
