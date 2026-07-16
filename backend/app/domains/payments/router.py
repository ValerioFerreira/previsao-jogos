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
    return service.list_packages(db)


@router.post("/checkout", response_model=schemas.CheckoutResponse, status_code=201)
def checkout(data: schemas.CheckoutRequest, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return service.create_order(db, user, data)


@router.get("/packages/recommended", response_model=schemas.PackageItem | None)
def recommended_package(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.recommend_package(db, user)


@router.get("/orders", response_model=list[schemas.OrderListItem])
def orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Minhas compras."""
    return service.list_orders(db, user)


@router.get("/orders/pending", response_model=list[schemas.OrderListItem])
def pending_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pagamentos pendentes (recuperação de PIX) — banner na Carteira."""
    return service.list_orders(db, user, only_pending=True)


@router.post("/orders/{order_id}/request-invoice", response_model=schemas.OrderListItem)
def request_invoice(order_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cliente pede a nota fiscal do pedido (emissão automática já rodou; aqui só libera a
    exibição/reenvio para o cliente)."""
    return service.request_invoice(db, user, order_id)


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
    # Diagnóstico temporário (investigação de assinatura MP divergente mesmo com secret
    # confirmado): captura o que dict(headers)/dict(query_params) poderia estar mascarando
    # silenciosamente — headers repetidos (dict() só mantém o último) e a query string crua.
    all_request_ids = request.headers.getlist("x-request-id")
    if len(all_request_ids) != 1:
        print(f"[DIAG] webhook {provider}: x-request-id aparece {len(all_request_ids)}x -> {all_request_ids}")
    print(f"[DIAG] webhook {provider}: query_string_crua={request.url.query!r} "
          f"x-signature_bruto={request.headers.get('x-signature')!r} "
          f"todos_headers={list(request.headers.items())!r}")
    return service.handle_webhook(db, provider, payload, dict(request.headers), body,
                                  dict(request.query_params))
