"""Regras de compra de créditos. O crédito na carteira acontece SÓ quando a ordem é
paga (webhook do gateway ou confirmação mock), via lançamento idempotente no ledger."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.enums import CreditTxType, PackageStatus, PaymentProvider, PaymentStatus
from app.domains.payments import schemas
from app.domains.payments.gateways import get_gateway
from app.domains.affiliates import service as affiliates_service
from app.domains.analytics import service as analytics_service
from app.domains.notifications import service as notifications_service
from app.domains.payments.invoicing import get_invoice_provider, issue_invoice
from app.domains.payments.models import CreditPackage, PaymentOrder, PaymentWebhook
from app.domains.promotions import service as promotions_service
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet, post_transaction


def list_packages(db: Session) -> list[schemas.PackageItem]:
    """Pacotes à venda — 100% gerenciados pelo painel admin (sem defaults hardcoded;
    `POST /admin/packages` é o único jeito de criar um novo)."""
    rows = db.execute(select(CreditPackage).where(CreditPackage.status == PackageStatus.ativo)
                      .order_by(CreditPackage.sort_order, CreditPackage.credits)).scalars().all()
    return [schemas.PackageItem(
        id=str(p.id), name=p.name, credits=p.credits, price_brl=p.price_brl,
        bonus_credits=p.bonus_credits, total_credits=p.credits + p.bonus_credits,
        featured_badge=p.featured_badge.value if p.featured_badge else None,
    ) for p in rows]


def create_order(db: Session, user: User, data: schemas.CheckoutRequest) -> schemas.CheckoutResponse:
    analytics_service.track(db, "checkout_started", user_id=user.id, package_id=data.package_id, credits=data.credits)
    if data.package_id:
        pkg = db.get(CreditPackage, uuid.UUID(data.package_id))
        if pkg is None or pkg.status != PackageStatus.ativo:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado.")
        credits = pkg.credits + pkg.bonus_credits
        amount = Decimal(pkg.price_brl)
        package_id = pkg.id
    else:
        credits = int(data.credits)
        amount = (Decimal(credits) * Decimal(str(settings.credit_unit_price_brl))).quantize(Decimal("0.01"))
        package_id = None

    original_amount = amount
    coupon_id = None
    if data.coupon_code:
        from app.domains.promotions import schemas as promo_schemas
        from app.domains.promotions.models import Coupon
        preview = promotions_service.validate_coupon(db, user.id, promo_schemas.CouponValidateRequest(
            code=data.coupon_code, amount_brl=amount, credits=credits,
            package_id=str(package_id) if package_id else None,
        ))
        coupon_id = uuid.UUID(preview.coupon_id)
        amount = preview.final_amount_brl
        credits += preview.bonus_credits
        analytics_service.track(db, "coupon_applied", user_id=user.id, code=data.coupon_code)

        # Cupom de parceiro (Coupon.affiliate_id) — usá-lo no checkout já atribui a venda
        # ao parceiro para fins de comissão, sem depender de clique prévio em ?ref=código
        # (o CÁLCULO de desconto e de comissão continuam totalmente independentes).
        coupon = db.get(Coupon, coupon_id)
        if coupon is not None and coupon.affiliate_id is not None:
            affiliates_service.attach_checkout_attribution(db, user_id=user.id, affiliate_id=coupon.affiliate_id)

    discount_amount = (original_amount - amount) if original_amount > amount else Decimal("0")

    gateway = get_gateway()
    order = PaymentOrder(
        user_id=user.id, provider=PaymentProvider(gateway.name), package_id=package_id,
        coupon_id=coupon_id, amount_brl=amount, discount_amount_brl=discount_amount,
        credits=credits, status=PaymentStatus.created,
        idempotency_key=f"order:{uuid.uuid4().hex}",
    )
    db.add(order)
    db.flush()

    res = gateway.create_checkout(order_id=str(order.id), amount_brl=amount,
                                  description=f"{credits} créditos", customer_email=user.email)
    order.provider_order_id = res.provider_order_id
    order.status = PaymentStatus.pending
    order.raw_payload = res.checkout  # permite reabrir o checkout (PIX pendente) depois
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
    if order.coupon_id is not None:
        promotions_service.mark_redeemed(db, order.coupon_id)
    affiliates_service.commission_for_order(db, order)
    analytics_service.track(db, "credit_purchase", user_id=order.user_id,
                            order_id=str(order.id), amount_brl=str(order.amount_brl), credits=order.credits)
    notifications_service.notify(db, order.user_id, "payment_approved", "Pagamento aprovado",
                                 f"+{order.credits} créditos adicionados à sua carteira.")
    issue_invoice(db, order)


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


def recommend_package(db: Session, user: User) -> schemas.PackageItem | None:
    """Heurística (não-ML): olha o consumo médio mensal de créditos do usuário e sugere
    o pacote cujo total de créditos fica mais próximo, arredondando para cima. Usuário
    sem histórico suficiente recebe o pacote de melhor custo-benefício (mais bônus
    proporcional) como default."""
    from datetime import datetime, timedelta, timezone
    from app.domains.wallet.models import CreditTransaction, Wallet
    from app.domains.enums import CreditTxType

    packages = list_packages(db)
    if not packages:
        return None

    wallet = db.execute(select(Wallet).where(Wallet.user_id == user.id)).scalar_one_or_none()
    monthly_consumption = None
    if wallet is not None:
        since = datetime.now(timezone.utc) - timedelta(days=90)
        total_consumed = db.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.wallet_id == wallet.id,
                CreditTransaction.type == CreditTxType.consumption,
                CreditTransaction.created_at >= since,
            )
        ).scalar_one()
        if total_consumed:
            monthly_consumption = abs(Decimal(total_consumed)) / Decimal(3)

    if monthly_consumption and monthly_consumption > 0:
        best = min(packages, key=lambda p: abs(Decimal(p.total_credits) - monthly_consumption))
        return best

    # Sem histórico: melhor custo-benefício = maior % de crédito bônus sobre o total.
    def bonus_ratio(p):
        return (p.bonus_credits / p.total_credits) if p.total_credits else 0
    return max(packages, key=bonus_ratio)


def _to_order_list_item(o: PaymentOrder, coupon_code: str | None = None) -> schemas.OrderListItem:
    return schemas.OrderListItem(
        order_id=str(o.id), provider=o.provider.value, method=o.method, status=o.status.value,
        amount_brl=o.amount_brl, credits=o.credits,
        coupon_code=coupon_code, discount_amount_brl=o.discount_amount_brl,
        checkout=o.raw_payload if o.status == PaymentStatus.pending else None,
        invoice_url=o.invoice_url, invoice_status=o.invoice_status,
        invoice_requested_at=o.invoice_requested_at.isoformat() if o.invoice_requested_at else None,
        created_at=o.created_at.isoformat(), paid_at=o.paid_at.isoformat() if o.paid_at else None,
    )


def list_orders(db: Session, user: User, only_pending: bool = False) -> list[schemas.OrderListItem]:
    """Minhas compras (Fase 6) — se only_pending, filtra pedidos PIX/pendentes para o
    banner de recuperação de pagamento (reabre o QR/copia-e-cola salvo em raw_payload)."""
    from app.domains.promotions.models import Coupon

    stmt = select(PaymentOrder).where(PaymentOrder.user_id == user.id)
    if only_pending:
        stmt = stmt.where(PaymentOrder.status == PaymentStatus.pending)
    rows = db.execute(stmt.order_by(PaymentOrder.created_at.desc()).limit(50)).scalars().all()
    coupon_ids = {o.coupon_id for o in rows if o.coupon_id}
    coupons_by_id = {}
    if coupon_ids:
        coupons_by_id = {c.id: c.code for c in db.execute(
            select(Coupon).where(Coupon.id.in_(coupon_ids))).scalars().all()}
    return [_to_order_list_item(o, coupons_by_id.get(o.coupon_id) if o.coupon_id else None) for o in rows]


def request_invoice(db: Session, user: User, order_id: str) -> schemas.OrderListItem:
    """Nota fiscal sob demanda: a emissão já roda automática em `_credit_if_paid` (best-effort,
    para todo pedido pago — mantém a declaração fiscal íntegra mesmo se o cliente nunca pedir);
    aqui só marcamos que o cliente pediu para VER/receber a nota, e tentamos emitir de novo caso
    a tentativa automática ainda esteja pendente/tenha falhado."""
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    order = db.get(PaymentOrder, oid)
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    if order.status != PaymentStatus.paid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nota fiscal só pode ser pedida para pedidos pagos.")

    if order.invoice_requested_at is None:
        order.invoice_requested_at = datetime.now(timezone.utc)
    if order.invoice_status != "issued":
        if order.invoice_provider_id:
            # Já existe um documento em andamento no provedor — reconsulta o status
            # em vez de reemitir (evita nota fiscal duplicada para o mesmo pedido).
            try:
                result = get_invoice_provider().check_status(provider_invoice_id=order.invoice_provider_id)
                order.invoice_url = result.url
                order.invoice_status = result.status
                order.invoice_number = result.invoice_number
            except Exception as e:
                print(f"[AVISO] check_status({order.id}): {e}")
        else:
            issue_invoice(db, order)
    db.commit()
    db.refresh(order)
    return _to_order_list_item(order)


def cancel_order(db: Session, user: User, order_id: str) -> schemas.OrderListItem:
    """Cliente desiste de um pedido ainda pendente (ex.: PIX que não vai mais pagar) —
    não mexe no ledger, já que nada foi creditado enquanto o pedido está `pending`."""
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    order = db.get(PaymentOrder, oid)
    if order is None or order.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    if order.status != PaymentStatus.pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Só é possível cancelar pedidos pendentes.")
    order.status = PaymentStatus.canceled
    db.commit()
    db.refresh(order)
    return _to_order_list_item(order)


def poll_pending_invoices(db: Session) -> dict:
    """Reconsulta no provedor os documentos ainda 'pending' (emissão assíncrona,
    ex.: NFE.io) e persiste a transição de status. Uso agendado (cron periódico),
    análogo a `bets/settlement.py::run_due_settlements`."""
    provider = get_invoice_provider()
    rows = db.execute(
        select(PaymentOrder).where(
            PaymentOrder.invoice_status == "pending",
            PaymentOrder.invoice_provider_id.is_not(None),
        )
    ).scalars().all()
    checked, issued, failed, errors = 0, 0, 0, 0
    for order in rows:
        checked += 1
        try:
            result = provider.check_status(provider_invoice_id=order.invoice_provider_id)
            order.invoice_url = result.url
            order.invoice_status = result.status
            order.invoice_number = result.invoice_number
            if result.status == "issued":
                issued += 1
            elif result.status == "failed":
                failed += 1
        except Exception as e:
            errors += 1
            print(f"[AVISO] poll_pending_invoices check_status({order.id}): {e}")
    db.commit()
    return {"checked": checked, "issued": issued, "failed": failed, "errors": errors}


def handle_webhook(db: Session, provider: str, payload: dict, headers: dict, body: bytes,
                    query_params: dict | None = None) -> dict:
    gateway = get_gateway()
    if not gateway.verify_signature(headers, body, query_params or {}):
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
    elif order is not None and event.status == "failed":
        order.status = PaymentStatus.failed
        analytics_service.track(db, "payment_failed", user_id=order.user_id, order_id=str(order.id))
    wh.processed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "processed"}
