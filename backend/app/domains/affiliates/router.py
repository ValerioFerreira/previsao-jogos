"""Rotas públicas de rastreamento (clique/attach) + portal do afiliado. O portal aceita
duas formas de acesso: (a) conta de usuário comum linkada via `Affiliate.user_id` (legado,
exige cadastro completo), ou (b) login próprio do afiliado por email+CPF
(`POST /affiliates/login`), sem precisar de conta de usuário — emite um JWT de escopo
restrito (`scope=affiliate`) que só abre as rotas deste router."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.domains.affiliates import schemas, service
from app.domains.affiliates.models import Affiliate, AffiliateAttribution, AffiliateCommission
from app.domains.auth.deps import get_current_user, get_db
from app.domains.payments.models import PaymentOrder
from app.domains.users.models import User

router = APIRouter(prefix="/affiliates", tags=["affiliates"])

_affiliate_bearer = HTTPBearer(auto_error=False)
_AFFILIATE_TOKEN_TTL_MIN = 12 * 60  # 12h — sem refresh token, evita relogar toda hora


def get_current_affiliate(
    creds: HTTPAuthorizationCredentials | None = Depends(_affiliate_bearer),
    db: Session = Depends(get_db),
) -> Affiliate:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    try:
        payload = security.decode_access_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    if payload.get("scope") != "affiliate":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido para esta operação.")
    affiliate = db.get(Affiliate, uuid.UUID(payload["sub"]))
    if affiliate is None or affiliate.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Afiliado inválido.")
    return affiliate


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


@router.post("/login", response_model=schemas.AffiliateTokenResponse)
def login(data: schemas.AffiliateLoginRequest, db: Session = Depends(get_db)):
    """Login próprio do afiliado — email + CPF, sem precisar de conta de usuário
    (ver aviso de segurança no docstring do módulo/`Affiliate.cpf`)."""
    email = data.email.strip().lower()
    cpf = "".join(ch for ch in data.cpf if ch.isdigit())
    affiliate = db.execute(select(Affiliate).where(
        func.lower(Affiliate.contact_email) == email, Affiliate.cpf == cpf,
    )).scalar_one_or_none()
    if affiliate is None or affiliate.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="E-mail ou CPF inválido.")
    token = security.create_access_token(
        str(affiliate.id), extra={"scope": "affiliate"}, ttl_min=_AFFILIATE_TOKEN_TTL_MIN,
    )
    return schemas.AffiliateTokenResponse(access_token=token, expires_in=_AFFILIATE_TOKEN_TTL_MIN * 60)


def _portal_stats(affiliate: Affiliate, db: Session) -> schemas.PortalStats:
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


@router.get("/me", response_model=schemas.PortalStats)
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Legado — conta de usuário comum linkada via `Affiliate.user_id`. Afiliados logados
    por e-mail+CPF usam `GET /affiliates/portal/me` (token de escopo `affiliate`)."""
    affiliate = db.execute(select(Affiliate).where(Affiliate.user_id == user.id)).scalar_one_or_none()
    if affiliate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Você não é um afiliado.")
    return _portal_stats(affiliate, db)


@router.get("/portal/me", response_model=schemas.PortalStats)
def portal_stats(affiliate: Affiliate = Depends(get_current_affiliate), db: Session = Depends(get_db)):
    return _portal_stats(affiliate, db)


@router.get("/portal/timeseries", response_model=schemas.TimeseriesResponse)
def portal_timeseries(
    granularity: str = "day",
    affiliate: Affiliate = Depends(get_current_affiliate),
    db: Session = Depends(get_db),
):
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
