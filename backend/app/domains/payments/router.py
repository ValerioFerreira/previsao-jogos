"""Rotas de compra de créditos: pacotes, checkout, confirmação mock e webhook."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.payments import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/packages", response_model=list[schemas.PackageItem])
def packages(db: Session = Depends(get_db)):
    service.seed_default_packages(db)
    return service.list_packages(db)


@router.post("/checkout", response_model=schemas.CheckoutResponse, status_code=201)
def checkout(data: schemas.CheckoutRequest, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return service.create_order(db, user, data)


@router.post("/mock/confirm/{order_id}", response_model=schemas.OrderResponse)
def mock_confirm(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """DEV: simula o pagamento (provider mock) e credita a carteira."""
    return service.confirm_mock(db, user, order_id)


@router.post("/webhook/{provider}")
async def webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        payload = {}
    return service.handle_webhook(db, provider, payload, dict(request.headers), body)
