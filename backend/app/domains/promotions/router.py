"""Rotas públicas de cupom — validação (preview) usada pelo campo "Aplicar" na Carteira.
O resgate (incremento de `redemptions`) acontece só dentro do fluxo de pagamento
confirmado (payments/service.py), nunca por chamada direta do cliente."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.admin.models import Banner
from app.domains.auth.deps import get_current_user, get_db
from app.domains.promotions import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/promotions", tags=["promotions"])


@router.post("/coupons/validate", response_model=schemas.CouponPreview)
def validate_coupon(data: schemas.CouponValidateRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return service.validate_coupon(db, user.id, data)


banners_router = APIRouter(tags=["banners"])


@banners_router.get("/banners/active")
def active_banners(db: Session = Depends(get_db)):
    """Público — consumido pela Carteira para o banner promocional."""
    now = datetime.now(timezone.utc)
    rows = db.execute(select(Banner).where(
        Banner.active.is_(True),
        or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
        or_(Banner.ends_at.is_(None), Banner.ends_at >= now),
    ).order_by(Banner.created_at.desc())).scalars().all()
    return {"items": [{"id": str(b.id), "title": b.title, "body": b.body, "type": b.type} for b in rows]}
