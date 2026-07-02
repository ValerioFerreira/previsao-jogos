"""Serviços do Painel Administrativo. Toda mutação registra AdminAuditLog (auditoria completa).
Opera sobre os mesmos serviços de domínio (ledger, legal, etc.) — sem duplicar regra."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.admin import schemas
from app.domains.admin.models import AdminAuditLog, Banner, PlatformSetting
from app.domains.analysis.models import Analysis
from app.domains.bets.models import Bet
from app.domains.enums import CreditTxType, UserStatus
from app.domains.legal import service as legal_service
from app.domains.payments.models import PaymentOrder
from app.domains.promotions.models import Promotion
from app.domains.users.models import User
from app.domains.wallet.models import CreditTransaction, Wallet
from app.domains.wallet.service import get_or_create_wallet, post_transaction

_CREDIT_KINDS = {
    "manual_adjustment": CreditTxType.manual_adjustment,
    "bonus": CreditTxType.bonus,
    "promo_credit": CreditTxType.promo_credit,
    "cashback": CreditTxType.cashback,
    "refund": CreditTxType.refund,
}


def audit(db: Session, admin: User, action: str, target_type=None, target_id=None,
          before=None, after=None, ip=None) -> None:
    db.add(AdminAuditLog(admin_id=admin.id, action=action, target_type=target_type,
                         target_id=target_id, before=before, after=after, ip=ip))


# --------------------------------------------------------------- usuários
def list_users(db: Session, q: str | None, limit: int, offset: int) -> schemas.AdminUsersPage:
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like),
                              User.cpf.like(f"%{q}%"), User.phone.like(f"%{q}%")))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    ids = [u.id for u in rows]
    wallets = {w.user_id: w for w in db.execute(select(Wallet).where(Wallet.user_id.in_(ids))).scalars()} if ids else {}
    items = [schemas.AdminUserItem(
        id=str(u.id), full_name=u.full_name, email=u.email, cpf=u.cpf, phone=u.phone,
        status=u.status.value, role=u.role.value, created_at=u.created_at, last_login_at=u.last_login_at,
        available_balance=(wallets.get(u.id).available_balance if wallets.get(u.id) else None),
        reserved_balance=(wallets.get(u.id).reserved_balance if wallets.get(u.id) else None),
    ) for u in rows]
    return schemas.AdminUsersPage(items=items, total=total, limit=limit, offset=offset)


def _get_user(db: Session, user_id: str) -> User:
    try:
        u = db.get(User, uuid.UUID(user_id))
    except ValueError:
        u = None
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return u


def get_user(db: Session, user_id: str) -> schemas.AdminUserItem:
    u = _get_user(db, user_id)
    w = get_or_create_wallet(db, u.id); db.commit()
    return schemas.AdminUserItem(
        id=str(u.id), full_name=u.full_name, email=u.email, cpf=u.cpf, phone=u.phone,
        status=u.status.value, role=u.role.value, created_at=u.created_at, last_login_at=u.last_login_at,
        available_balance=w.available_balance, reserved_balance=w.reserved_balance,
    )


def set_blocked(db: Session, admin: User, user_id: str, blocked: bool, reason: str | None, ip) -> None:
    u = _get_user(db, user_id)
    before = u.status.value
    u.status = UserStatus.blocked if blocked else UserStatus.active
    audit(db, admin, "block_user" if blocked else "unblock_user", "user", u.id,
          before={"status": before}, after={"status": u.status.value, "reason": reason}, ip=ip)
    db.commit()


def adjust_credits(db: Session, admin: User, user_id: str, data: schemas.CreditAdjustRequest, ip) -> dict:
    u = _get_user(db, user_id)
    kind = _CREDIT_KINDS.get(data.kind)
    if kind is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de crédito inválido.")
    wallet = get_or_create_wallet(db, u.id)
    try:
        tx = post_transaction(
            db, wallet=wallet, tx_type=kind, amount=Decimal(data.amount),
            idempotency_key=f"admin-adj:{uuid.uuid4().hex}", reference_type="admin",
            description=f"[admin] {data.reason}", created_by=admin.id,
        )
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Saldo insuficiente para o débito.")
    audit(db, admin, "credit_adjust", "user", u.id,
          after={"amount": str(data.amount), "kind": data.kind, "reason": data.reason, "tx": str(tx.id)}, ip=ip)
    db.commit()
    return {"available_balance": str(wallet.available_balance), "reserved_balance": str(wallet.reserved_balance),
            "transaction_id": str(tx.id)}


# --------------------------------------------------------------- financeiro / listagens
def list_payments(db: Session, limit: int, offset: int) -> dict:
    total = db.execute(select(func.count(PaymentOrder.id))).scalar_one()
    rows = db.execute(select(PaymentOrder).order_by(PaymentOrder.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return {"items": [{"id": str(o.id), "user_id": str(o.user_id), "provider": o.provider.value,
                       "amount_brl": str(o.amount_brl), "credits": o.credits, "status": o.status.value,
                       "created_at": o.created_at.isoformat(), "paid_at": o.paid_at.isoformat() if o.paid_at else None}
                      for o in rows], "total": total, "limit": limit, "offset": offset}


def list_transactions(db: Session, user_id: str | None, limit: int, offset: int) -> dict:
    stmt = select(CreditTransaction)
    if user_id:
        w = db.execute(select(Wallet).where(Wallet.user_id == uuid.UUID(user_id))).scalar_one_or_none()
        stmt = stmt.where(CreditTransaction.wallet_id == (w.id if w else uuid.uuid4()))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(CreditTransaction.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [{"id": str(t.id), "wallet_id": str(t.wallet_id), "type": t.type.value,
                       "amount": str(t.amount), "balance_after": str(t.balance_after),
                       "reference_type": t.reference_type, "description": t.description,
                       "created_at": t.created_at.isoformat()} for t in rows],
            "total": total, "limit": limit, "offset": offset}


def list_analyses(db: Session, limit: int, offset: int) -> dict:
    total = db.execute(select(func.count(Analysis.id))).scalar_one()
    rows = db.execute(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [{"id": str(a.id), "user_id": str(a.user_id), "type": a.type.value, "status": a.status.value,
                       "home_team": a.home_team, "away_team": a.away_team, "tournament": a.tournament,
                       "created_at": a.created_at.isoformat()} for a in rows],
            "total": total, "limit": limit, "offset": offset}


def list_bets(db: Session, limit: int, offset: int) -> dict:
    total = db.execute(select(func.count(Bet.id))).scalar_one()
    rows = db.execute(select(Bet).order_by(Bet.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [{"id": str(b.id), "user_id": str(b.user_id), "analysis_id": str(b.analysis_id),
                       "status": b.status.value, "combined_odd": str(b.combined_odd), "fixture_id": b.fixture_id,
                       "created_at": b.created_at.isoformat()} for b in rows],
            "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------- promoções
def create_promotion(db: Session, admin: User, data: schemas.PromotionRequest, ip) -> dict:
    from app.domains.enums import PromotionType
    try:
        ptype = PromotionType(data.type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de promoção inválido.")
    if db.execute(select(Promotion).where(Promotion.code == data.code)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Código de promoção já existe.")
    p = Promotion(code=data.code, name=data.name, type=ptype, config=data.config,
                  max_odd=data.max_odd, active=data.active, created_by=admin.id)
    db.add(p); db.flush()
    audit(db, admin, "promotion_create", "promotion", p.id, after={"code": data.code, "type": data.type}, ip=ip)
    db.commit()
    return {"id": str(p.id), "code": p.code, "type": p.type.value, "active": p.active}


def patch_promotion(db: Session, admin: User, promo_id: str, data: schemas.PromotionPatch, ip) -> dict:
    try:
        p = db.get(Promotion, uuid.UUID(promo_id))
    except ValueError:
        p = None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Promoção não encontrada.")
    before = {"active": p.active, "name": p.name}
    if data.name is not None: p.name = data.name
    if data.config is not None: p.config = data.config
    if data.max_odd is not None: p.max_odd = data.max_odd
    if data.active is not None: p.active = data.active
    audit(db, admin, "promotion_update", "promotion", p.id, before=before,
          after={"active": p.active, "name": p.name}, ip=ip)
    db.commit()
    return {"id": str(p.id), "code": p.code, "active": p.active}


def list_promotions(db: Session) -> dict:
    rows = db.execute(select(Promotion).order_by(Promotion.created_at.desc())).scalars().all()
    return {"items": [{"id": str(p.id), "code": p.code, "name": p.name, "type": p.type.value,
                       "active": p.active, "max_odd": str(p.max_odd) if p.max_odd else None,
                       "config": p.config} for p in rows]}


# --------------------------------------------------------------- documentos legais
def publish_document(db: Session, admin: User, data: schemas.LegalPublishRequest, ip) -> dict:
    doc = legal_service.publish(db, data.type, data.title, data.body_md, admin.id)
    audit(db, admin, "legal_publish", "legal_document", doc.id,
          after={"type": data.type, "version": doc.version}, ip=ip)
    db.commit()
    return {"id": str(doc.id), "type": doc.type.value, "version": doc.version}


# --------------------------------------------------------------- settings / banners
def set_setting(db: Session, admin: User, key: str, data: schemas.SettingRequest, ip) -> dict:
    s = db.execute(select(PlatformSetting).where(PlatformSetting.key == key)).scalar_one_or_none()
    before = s.value if s else None
    if s is None:
        s = PlatformSetting(key=key, value=data.value, description=data.description); db.add(s)
    else:
        s.value = data.value
        if data.description is not None: s.description = data.description
    audit(db, admin, "setting_set", "platform_setting", None, before=before, after=data.value, ip=ip)
    db.commit()
    return {"key": key, "value": data.value}


def get_settings(db: Session) -> dict:
    rows = db.execute(select(PlatformSetting)).scalars().all()
    return {"items": [{"key": s.key, "value": s.value, "description": s.description} for s in rows]}


def create_banner(db: Session, admin: User, data: schemas.BannerRequest, ip) -> dict:
    b = Banner(title=data.title, body=data.body, type=data.type, active=data.active,
               starts_at=data.starts_at, ends_at=data.ends_at)
    db.add(b); db.flush()
    audit(db, admin, "banner_create", "banner", b.id, after={"title": data.title}, ip=ip)
    db.commit()
    return {"id": str(b.id), "title": b.title, "active": b.active}


def list_banners(db: Session) -> dict:
    rows = db.execute(select(Banner).order_by(Banner.created_at.desc())).scalars().all()
    return {"items": [{"id": str(b.id), "title": b.title, "body": b.body, "type": b.type,
                       "active": b.active} for b in rows]}


# --------------------------------------------------------------- auditoria
def list_audit(db: Session, limit: int, offset: int) -> dict:
    total = db.execute(select(func.count(AdminAuditLog.id))).scalar_one()
    rows = db.execute(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    return {"items": [{"id": str(a.id), "admin_id": str(a.admin_id) if a.admin_id else None,
                       "action": a.action, "target_type": a.target_type,
                       "target_id": str(a.target_id) if a.target_id else None,
                       "before": a.before, "after": a.after, "created_at": a.created_at.isoformat()}
                      for a in rows], "total": total, "limit": limit, "offset": offset}
