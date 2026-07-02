"""Regras de compra de créditos. O crédito na carteira acontece SÓ quando a ordem é
paga (webhook do gateway ou confirmação mock), via lançamento idempotente no ledger."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.enums import CreditTxType, PaymentProvider, PaymentStatus
from app.domains.payments import schemas
from app.domains.payments.gateways import get_gateway
from app.domains.payments.models import CreditPackage, PaymentOrder, PaymentWebhook
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet, post_transaction

_DEFAULT_PACKAGES = [
    ("Avulso", 1, "1.00", 0),
    ("Pacote 10", 10, "10.00", 0),
    ("Pacote 50 (+5 bônus)", 50, "50.00", 5),
    ("Pacote 100 (+15 bônus)", 100, "100.00", 15),
]


def seed_default_packages(db: Session) -> None:
    if db.execute(select(CreditPackage.id).limit(1)).first() is not None:
        return
    for name, credits, price, bonus in _DEFAULT_PACKAGES:
        db.add(CreditPackage(name=name, credits=credits, price_brl=Decimal(price),
                             bonus_credits=bonus, active=True))
    db.commit()


def list_packages(db: Session) -> list[schemas.PackageItem]:
    rows = db.execute(select(CreditPackage).where(CreditPackage.active.is_(True))
                      .order_by(CreditPackage.credits)).scalars().all()
    return [schemas.PackageItem(
        id=str(p.id), name=p.name, credits=p.credits, price_brl=p.price_brl,
        bonus_credits=p.bonus_credits, total_credits=p.credits + p.bonus_credits,
    ) for p in rows]


def create_order(db: Session, user: User, data: schemas.CheckoutRequest) -> schemas.CheckoutResponse:
    if data.package_id:
        pkg = db.get(CreditPackage, uuid.UUID(data.package_id))
        if pkg is None or not pkg.active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado.")
        credits = pkg.credits + pkg.bonus_credits
        amount = Decimal(pkg.price_brl)
        package_id = pkg.id
    else:
        credits = int(data.credits)
        amount = (Decimal(credits) * Decimal(str(settings.credit_unit_price_brl))).quantize(Decimal("0.01"))
        package_id = None

    gateway = get_gateway()
    order = PaymentOrder(
        user_id=user.id, provider=PaymentProvider(gateway.name), package_id=package_id,
        amount_brl=amount, credits=credits, status=PaymentStatus.created,
        idempotency_key=f"order:{uuid.uuid4().hex}",
    )
    db.add(order)
    db.flush()

    res = gateway.create_checkout(order_id=str(order.id), amount_brl=amount,
                                  description=f"{credits} créditos", customer_email=user.email)
    order.provider_order_id = res.provider_order_id
    order.status = PaymentStatus.pending
    db.commit()

    return schemas.CheckoutResponse(
        order_id=str(order.id), provider=gateway.name, status=order.status.value,
        amount_brl=amount, credits=credits, checkout=res.checkout,
    )


def _credit_if_paid(db: Session, order: PaymentOrder, raw: dict | None) -> None:
    """Marca a ordem como paga e credita a carteira — idempotente."""
    if order.status == PaymentStatus.paid:
        return
    order.status = PaymentStatus.paid
    order.paid_at = datetime.now(timezone.utc)
    if raw is not None:
        order.raw_payload = raw
    wallet = get_or_create_wallet(db, order.user_id)
    post_transaction(
        db, wallet=wallet, tx_type=CreditTxType.purchase, amount=Decimal(order.credits),
        idempotency_key=f"payment:{order.id}", reference_type="payment_order",
        reference_id=order.id, description=f"Compra de {order.credits} créditos",
    )


def confirm_mock(db: Session, user: User, order_id: str) -> schemas.OrderResponse:
    """Simula o pagamento (apenas provider mock) — dispara o mesmo caminho de crédito."""
    if (settings.payment_provider or "mock").lower() != "mock":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Confirmação mock indisponível.")
    order = db.get(PaymentOrder, uuid.UUID(order_id))
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ordem não encontrada.")
    _credit_if_paid(db, order, {"mock_confirmed": True})
    db.commit()
    wallet = get_or_create_wallet(db, user.id)
    return schemas.OrderResponse(order_id=str(order.id), status=order.status.value,
                                 amount_brl=order.amount_brl, credits=order.credits,
                                 available_balance=wallet.available_balance)


def handle_webhook(db: Session, provider: str, payload: dict, headers: dict, body: bytes) -> dict:
    gateway = get_gateway()
    if not gateway.verify_signature(headers, body):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Assinatura inválida.")
    event = gateway.parse_webhook(payload)

    # registro idempotente do evento
    dup = db.execute(select(PaymentWebhook).where(
        PaymentWebhook.provider == PaymentProvider(provider),
        PaymentWebhook.external_id == event.external_id,
        PaymentWebhook.event == event.event,
    )).scalar_one_or_none()
    if dup is not None and dup.processed_at is not None:
        return {"status": "already_processed"}

    wh = dup or PaymentWebhook(provider=PaymentProvider(provider), event=event.event,
                               external_id=event.external_id, payload=event.raw,
                               signature_verified=True)
    if dup is None:
        db.add(wh)

    order = db.execute(select(PaymentOrder).where(
        PaymentOrder.provider_order_id == event.external_id
    )).scalar_one_or_none()
    if order is not None and event.status == "paid":
        _credit_if_paid(db, order, event.raw)
    wh.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "processed"}
