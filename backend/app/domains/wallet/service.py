"""Serviço da carteira: criação e postagem de lançamentos no ledger.

Invariante: o saldo (available/reserved) é SEMPRE alterado por um lançamento
(CreditTransaction) na mesma transação. `post_transaction` é idempotente pela
`idempotency_key` — chamadas repetidas (webhook/retry) devolvem o lançamento existente.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.enums import CreditTxStatus, CreditTxType
from app.domains.wallet.models import CreditTransaction, Wallet


def get_or_create_wallet(db: Session, user_id: uuid.UUID) -> Wallet:
    wallet = db.execute(select(Wallet).where(Wallet.user_id == user_id)).scalar_one_or_none()
    if wallet is None:
        wallet = Wallet(user_id=user_id, available_balance=Decimal("0"), reserved_balance=Decimal("0"))
        db.add(wallet)
        db.flush()
    return wallet


def post_transaction(
    db: Session,
    *,
    wallet: Wallet,
    tx_type: CreditTxType,
    amount: Decimal,
    reserved_delta: Decimal = Decimal("0"),
    idempotency_key: str,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    description: str | None = None,
    created_by: uuid.UUID | None = None,
) -> CreditTransaction:
    """Aplica um lançamento ao ledger e atualiza os saldos cacheados na mesma transação.

    `amount`: variação do saldo DISPONÍVEL (assinado). `reserved_delta`: variação do
    saldo RESERVADO (assinado). Ex.: reservar 1 crédito = amount -1, reserved_delta +1.
    """
    existing = db.execute(
        select(CreditTransaction).where(CreditTransaction.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # idempotência: não duplica

    new_available = Decimal(wallet.available_balance) + amount
    new_reserved = Decimal(wallet.reserved_balance) + reserved_delta
    if new_available < 0 or new_reserved < 0:
        raise ValueError("Saldo insuficiente para o lançamento.")

    wallet.available_balance = new_available
    wallet.reserved_balance = new_reserved

    tx = CreditTransaction(
        wallet_id=wallet.id,
        type=tx_type,
        status=CreditTxStatus.completed,
        amount=amount,
        reserved_delta=reserved_delta,
        balance_after=new_available,
        reserved_after=new_reserved,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        idempotency_key=idempotency_key,
        created_by=created_by,
    )
    db.add(tx)
    db.flush()
    return tx
