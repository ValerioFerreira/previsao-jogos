"""Rotas da carteira: saldo (disponível/reservado) e histórico de movimentações."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.users.models import User
from app.domains.wallet import schemas
from app.domains.wallet.models import CreditTransaction, Wallet
from app.domains.wallet.service import get_or_create_wallet

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=schemas.WalletResponse)
def get_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = get_or_create_wallet(db, user.id)
    db.commit()
    return schemas.WalletResponse(
        available_balance=wallet.available_balance, reserved_balance=wallet.reserved_balance
    )


@router.get("/transactions", response_model=schemas.TransactionsPage)
def transactions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    type: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    wallet = get_or_create_wallet(db, user.id)
    stmt = select(CreditTransaction).where(CreditTransaction.wallet_id == wallet.id)
    if type:
        stmt = stmt.where(CreditTransaction.type == type)
    if status:
        stmt = stmt.where(CreditTransaction.status == status)
    if since:
        stmt = stmt.where(CreditTransaction.created_at >= since)
    if until:
        stmt = stmt.where(CreditTransaction.created_at <= until)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(CreditTransaction.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    db.commit()
    items = [schemas.TransactionItem(
        id=str(t.id), type=t.type.value, status=t.status.value, amount=t.amount,
        reserved_delta=t.reserved_delta, balance_after=t.balance_after,
        reserved_after=t.reserved_after, description=t.description,
        reference_type=t.reference_type, created_at=t.created_at,
    ) for t in rows]
    return schemas.TransactionsPage(items=items, total=total, limit=limit, offset=offset)
