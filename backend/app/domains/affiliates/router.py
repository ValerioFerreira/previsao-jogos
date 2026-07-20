"""Rotas públicas de rastreamento (clique/attach) + solicitação de parceria + portal do
parceiro. O portal usa a conta de usuário comum (role=partner) linkada via
`Affiliate.user_id`, criada na aprovação da solicitação (ver admin/service.py) — sem
login próprio separado."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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


@router.post("/apply", response_model=schemas.PartnerApplicationResponse, status_code=201)
def apply(data: schemas.PartnerApplicationRequest, db: Session = Depends(get_db)):
    """Solicitação pública de parceria — fica `pending` até o admin aprovar/rejeitar."""
    service.apply_for_partnership(db, data)
    db.commit()
    return schemas.PartnerApplicationResponse()


_ALLOWED_DISCOUNT_TIERS = (5, 10, 15, 20, 25)


@router.get("/suggest-code", response_model=schemas.CodeSuggestionResponse)
def suggest_code(full_name: str, discount_pct: int, db: Session = Depends(get_db)):
    """Sugestão automática de código —
    chamada pelo formulário de solicitação a cada mudança de nome/tier de desconto."""
    if discount_pct not in _ALLOWED_DISCOUNT_TIERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Desconto deve ser 5, 10, 15, 20 ou 25.")
    prefix = service.suggest_code_prefix(db, full_name or "parceiro")
    return schemas.CodeSuggestionResponse(prefix=prefix, code=f"{prefix}{discount_pct}")


def _get_affiliate_for_user(user: User, db: Session) -> Affiliate:
    affiliate = db.execute(select(Affiliate).where(Affiliate.user_id == user.id)).scalar_one_or_none()
    if affiliate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Você não é um parceiro.")
    return affiliate


@router.get("/me", response_model=schemas.PortalStats)
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    affiliate = _get_affiliate_for_user(user, db)
    return schemas.PortalStats(**service.compute_portal_stats(db, affiliate))


@router.get("/portal/me", response_model=schemas.PortalStats)
def portal_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    affiliate = _get_affiliate_for_user(user, db)
    return schemas.PortalStats(**service.compute_portal_stats(db, affiliate))


@router.get("/portal/timeseries", response_model=schemas.TimeseriesResponse)
def portal_timeseries(
    granularity: str = "day",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    affiliate = _get_affiliate_for_user(user, db)
    if granularity not in ("day", "month"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="granularity deve ser 'day' ou 'month'.")
    fmt = "%Y-%m-%d" if granularity == "day" else "%Y-%m"
    since = datetime.now(timezone.utc) - timedelta(days=90 if granularity == "day" else 365)

    buckets: dict[str, dict] = {}

    def _bucket(b: str) -> dict:
        return buckets.setdefault(b, {"clicks": 0, "conversions": 0, "revenue": Decimal("0"), "commission": Decimal("0")})

    attributions = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.affiliate_id == affiliate.id, AffiliateAttribution.attributed_at >= since,
    )).scalars().all()
    for a in attributions:
        _bucket(a.attributed_at.strftime(fmt))["clicks"] += 1
        if a.converted_at:
            _bucket(a.converted_at.strftime(fmt))["conversions"] += 1

    commissions = db.execute(
        select(AffiliateCommission, PaymentOrder.amount_brl)
        .join(PaymentOrder, PaymentOrder.id == AffiliateCommission.order_id)
        .where(AffiliateCommission.affiliate_id == affiliate.id, AffiliateCommission.created_at >= since)
    ).all()
    for c, amount_brl in commissions:
        b = _bucket(c.created_at.strftime(fmt))
        b["revenue"] += Decimal(amount_brl)
        b["commission"] += Decimal(c.amount_brl)

    items = [
        schemas.TimeseriesPoint(
            bucket=b, clicks=v["clicks"], conversions=v["conversions"],
            revenue_brl=str(v["revenue"]), commission_brl=str(v["commission"]),
        )
        for b, v in sorted(buckets.items())
    ]
    return schemas.TimeseriesResponse(granularity=granularity, items=items)
