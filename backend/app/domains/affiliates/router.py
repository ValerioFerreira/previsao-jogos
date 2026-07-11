"""Rotas públicas de rastreamento (clique/attach) + portal do afiliado (autenticado,
só para o usuário vinculado ao Affiliate.user_id)."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.affiliates import schemas, service
from app.domains.affiliates.models import Affiliate, AffiliateAttribution, AffiliateCommission
from app.domains.auth.deps import get_current_user, get_db
from app.domains.payments.models import PaymentOrder
from app.domains.users.models import User

router = APIRouter(prefix="/affiliates", tags=["affiliates"])


@router.post("/track", status_code=201)
def track_click(data: schemas.TrackClickRequest, db: Session = Depends(get_db)):
    service.track_click(db, data.code, data.anon_id)
    db.commit()
    return {"ok": True}


@router.post("/attach")
def attach_signup(data: schemas.AttachSignupRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    service.attach_user_on_signup(db, data.anon_id, user.id)
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=schemas.PortalStats)
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    affiliate = db.execute(select(Affiliate).where(Affiliate.user_id == user.id)).scalar_one_or_none()
    if affiliate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Você não é um afiliado.")

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

    return schemas.PortalStats(
        code=affiliate.code, link=f"{settings.frontend_base_url}/?ref={affiliate.code}",
        clicks=clicks, signups=signups, buyers=buyers,
        revenue_brl=str(revenue), commission_due_brl=str(due), commission_paid_brl=str(paid),
    )
