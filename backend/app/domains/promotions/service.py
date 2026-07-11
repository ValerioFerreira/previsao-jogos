"""Cupons: validação/preview (checkout) e resgate (só a partir do webhook de pagamento
confirmado — nunca por chamada direta do cliente). Cupom concede benefício ao usuário;
é independente da atribuição de afiliado/comissão (ver app.domains.affiliates)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.enums import CouponDiscountType
from app.domains.promotions import schemas
from app.domains.promotions.models import Coupon


def _get_active_coupon(db: Session, code: str) -> Coupon:
    coupon = db.execute(select(Coupon).where(Coupon.code == code.strip().upper())).scalar_one_or_none()
    if coupon is None or not coupon.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cupom inválido.")
    now = datetime.now(timezone.utc)
    if coupon.valid_from and now < coupon.valid_from:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cupom ainda não é válido.")
    if coupon.valid_to and now > coupon.valid_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cupom expirado.")
    if coupon.usage_limit is not None and coupon.redemptions >= coupon.usage_limit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cupom esgotado.")
    return coupon


def _user_redemption_count(db: Session, coupon_id, user_id) -> int:
    from app.domains.payments.models import PaymentOrder
    from app.domains.enums import PaymentStatus
    return db.execute(select(func.count(PaymentOrder.id)).where(
        PaymentOrder.coupon_id == coupon_id, PaymentOrder.user_id == user_id,
        PaymentOrder.status == PaymentStatus.paid,
    )).scalar_one()


def compute_benefit(coupon: Coupon, amount_brl: Decimal, credits: int) -> tuple[Decimal, int]:
    """Retorna (novo_amount_brl, bonus_credits) aplicando o benefício do cupom."""
    if coupon.discount_type == CouponDiscountType.percentage and coupon.discount_value:
        pct = Decimal(coupon.discount_value) / Decimal(100)
        new_amount = (amount_brl * (Decimal(1) - pct)).quantize(Decimal("0.01"))
        return max(new_amount, Decimal("0.00")), 0
    if coupon.discount_type == CouponDiscountType.fixed and coupon.discount_value:
        new_amount = amount_brl - Decimal(coupon.discount_value)
        return max(new_amount, Decimal("0.00")), 0
    if coupon.discount_type == CouponDiscountType.bonus_credits and coupon.bonus_credits:
        return amount_brl, int(coupon.bonus_credits)
    return amount_brl, 0


def validate_coupon(db: Session, user_id: uuid.UUID, data: schemas.CouponValidateRequest) -> schemas.CouponPreview:
    coupon = _get_active_coupon(db, data.code)
    if coupon.per_user_limit is not None:
        used = _user_redemption_count(db, coupon.id, user_id)
        if used >= coupon.per_user_limit:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Você já usou esse cupom.")
    if coupon.package_id is not None and str(coupon.package_id) != (data.package_id or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cupom não é válido para este pacote.")
    if coupon.min_purchase_brl is not None and data.amount_brl < coupon.min_purchase_brl:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail=f"Valor mínimo de compra: R$ {coupon.min_purchase_brl}.")

    new_amount, bonus = compute_benefit(coupon, data.amount_brl, data.credits)
    return schemas.CouponPreview(
        coupon_id=str(coupon.id), code=coupon.code,
        discount_type=coupon.discount_type.value if coupon.discount_type else None,
        original_amount_brl=data.amount_brl, final_amount_brl=new_amount,
        bonus_credits=bonus,
    )


def mark_redeemed(db: Session, coupon_id) -> None:
    """Incrementa `redemptions` — chamado só quando o pagamento confirma (idempotência
    fica a cargo do caller: só chamar uma vez por PaymentOrder pago)."""
    coupon = db.get(Coupon, coupon_id)
    if coupon is not None:
        coupon.redemptions += 1
