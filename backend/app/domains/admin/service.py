"""Serviços do Painel Administrativo. Toda mutação registra AdminAuditLog (auditoria completa).
Opera sobre os mesmos serviços de domínio (ledger, legal, etc.) — sem duplicar regra."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from app.domains.admin import schemas
from app.domains.admin.models import AdminAuditLog, Banner, PlatformSetting
from app.domains.affiliates.models import Affiliate, AffiliateCommission
from app.domains.analysis.models import Analysis
from app.domains.analytics.models import Event
from app.domains.bets.models import Bet
from app.domains.enums import CreditTxType, PaymentStatus, UserStatus
from app.domains.legal import service as legal_service
from app.domains.payments.models import CreditPackage, PaymentOrder
from app.domains.promotions.models import Coupon, Promotion
from app.domains.support import schemas as support_schemas
from app.domains.support import service as support_service
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


# --------------------------------------------------------------- cupons
def _coupon_out(c: Coupon) -> dict:
    return {"id": str(c.id), "promotion_id": str(c.promotion_id), "code": c.code,
           "discount_type": c.discount_type.value if c.discount_type else None,
           "discount_value": str(c.discount_value) if c.discount_value is not None else None,
           "bonus_credits": c.bonus_credits, "min_purchase_brl": str(c.min_purchase_brl) if c.min_purchase_brl else None,
           "package_id": str(c.package_id) if c.package_id else None,
           "usage_limit": c.usage_limit, "per_user_limit": c.per_user_limit, "redemptions": c.redemptions,
           "valid_from": c.valid_from.isoformat() if c.valid_from else None,
           "valid_to": c.valid_to.isoformat() if c.valid_to else None, "active": c.active}


def create_coupon(db: Session, admin: User, data: schemas.CouponRequest, ip) -> dict:
    from app.domains.enums import CouponDiscountType
    try:
        dtype = CouponDiscountType(data.discount_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de desconto inválido.")
    if db.execute(select(Coupon).where(Coupon.code == data.code)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Código de cupom já existe.")
    c = Coupon(
        promotion_id=uuid.UUID(data.promotion_id), code=data.code.strip().upper(), discount_type=dtype,
        discount_value=data.discount_value, bonus_credits=data.bonus_credits,
        min_purchase_brl=data.min_purchase_brl,
        package_id=uuid.UUID(data.package_id) if data.package_id else None,
        usage_limit=data.usage_limit, per_user_limit=data.per_user_limit,
        valid_from=data.valid_from, valid_to=data.valid_to, active=data.active,
    )
    db.add(c); db.flush()
    audit(db, admin, "coupon_create", "coupon", c.id, after={"code": c.code}, ip=ip)
    db.commit()
    return _coupon_out(c)


def patch_coupon(db: Session, admin: User, coupon_id: str, data: schemas.CouponPatch, ip) -> dict:
    from app.domains.enums import CouponDiscountType
    try:
        c = db.get(Coupon, uuid.UUID(coupon_id))
    except ValueError:
        c = None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cupom não encontrado.")
    before = _coupon_out(c)
    if data.discount_type is not None: c.discount_type = CouponDiscountType(data.discount_type)
    if data.discount_value is not None: c.discount_value = data.discount_value
    if data.bonus_credits is not None: c.bonus_credits = data.bonus_credits
    if data.min_purchase_brl is not None: c.min_purchase_brl = data.min_purchase_brl
    if data.package_id is not None: c.package_id = uuid.UUID(data.package_id) if data.package_id else None
    if data.usage_limit is not None: c.usage_limit = data.usage_limit
    if data.per_user_limit is not None: c.per_user_limit = data.per_user_limit
    if data.valid_from is not None: c.valid_from = data.valid_from
    if data.valid_to is not None: c.valid_to = data.valid_to
    if data.active is not None: c.active = data.active
    audit(db, admin, "coupon_update", "coupon", c.id, before=before, after=_coupon_out(c), ip=ip)
    db.commit()
    return _coupon_out(c)


def list_coupons(db: Session) -> dict:
    rows = db.execute(select(Coupon).order_by(Coupon.created_at.desc())).scalars().all()
    return {"items": [_coupon_out(c) for c in rows]}


# --------------------------------------------------------------- afiliados
def _affiliate_out(a: Affiliate, db: Session) -> dict:
    due = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == a.id, AffiliateCommission.status == "devida")).scalar_one()
    paid = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == a.id, AffiliateCommission.status == "paga")).scalar_one()
    return {"id": str(a.id), "name": a.name, "code": a.code, "user_id": str(a.user_id) if a.user_id else None,
           "commission_pct": str(a.commission_pct) if a.commission_pct else None,
           "commission_fixed_brl": str(a.commission_fixed_brl) if a.commission_fixed_brl else None,
           "status": a.status, "notes": a.notes,
           "commission_due_brl": str(due), "commission_paid_brl": str(paid)}


def create_affiliate(db: Session, admin: User, data: schemas.AffiliateRequest, ip) -> dict:
    if db.execute(select(Affiliate).where(Affiliate.code == data.code)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Código de afiliado já existe.")
    a = Affiliate(name=data.name, code=data.code.strip().lower(),
                 user_id=uuid.UUID(data.user_id) if data.user_id else None,
                 commission_pct=data.commission_pct, commission_fixed_brl=data.commission_fixed_brl,
                 notes=data.notes)
    db.add(a); db.flush()
    audit(db, admin, "affiliate_create", "affiliate", a.id, after={"code": a.code}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def patch_affiliate(db: Session, admin: User, affiliate_id: str, data: schemas.AffiliatePatch, ip) -> dict:
    try:
        a = db.get(Affiliate, uuid.UUID(affiliate_id))
    except ValueError:
        a = None
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Afiliado não encontrado.")
    before = {"status": a.status, "commission_pct": str(a.commission_pct) if a.commission_pct else None}
    if data.name is not None: a.name = data.name
    if data.commission_pct is not None: a.commission_pct = data.commission_pct
    if data.commission_fixed_brl is not None: a.commission_fixed_brl = data.commission_fixed_brl
    if data.status is not None: a.status = data.status
    if data.notes is not None: a.notes = data.notes
    audit(db, admin, "affiliate_update", "affiliate", a.id, before=before,
          after={"status": a.status}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def list_affiliates(db: Session) -> dict:
    rows = db.execute(select(Affiliate).order_by(Affiliate.created_at.desc())).scalars().all()
    return {"items": [_affiliate_out(a, db) for a in rows]}


# --------------------------------------------------------------- pacotes de crédito
def list_packages_admin(db: Session) -> dict:
    rows = db.execute(select(CreditPackage).order_by(CreditPackage.sort_order, CreditPackage.credits)).scalars().all()
    return {"items": [{"id": str(p.id), "name": p.name, "credits": p.credits, "price_brl": str(p.price_brl),
                       "bonus_credits": p.bonus_credits, "featured_badge": p.featured_badge.value if p.featured_badge else None,
                       "sort_order": p.sort_order, "active": p.active} for p in rows]}


def patch_package(db: Session, admin: User, package_id: str, data: schemas.PackagePatch, ip) -> dict:
    from app.domains.enums import PackageBadge
    try:
        p = db.get(CreditPackage, uuid.UUID(package_id))
    except ValueError:
        p = None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado.")
    before = {"name": p.name, "price_brl": str(p.price_brl), "featured_badge": p.featured_badge.value if p.featured_badge else None}
    if data.name is not None: p.name = data.name
    if data.credits is not None: p.credits = data.credits
    if data.price_brl is not None: p.price_brl = data.price_brl
    if data.bonus_credits is not None: p.bonus_credits = data.bonus_credits
    if "featured_badge" in data.model_fields_set:
        p.featured_badge = PackageBadge(data.featured_badge) if data.featured_badge else None
    if data.sort_order is not None: p.sort_order = data.sort_order
    if data.active is not None: p.active = data.active
    audit(db, admin, "package_update", "credit_package", p.id, before=before,
          after={"name": p.name, "price_brl": str(p.price_brl)}, ip=ip)
    db.commit()
    return {"id": str(p.id), "name": p.name, "active": p.active}


# --------------------------------------------------------------- dashboard executivo
def analytics_dashboard(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month0 = today0.replace(day=1)
    year0 = today0.replace(month=1, day=1)

    def revenue_since(since: datetime) -> Decimal:
        return db.execute(select(func.coalesce(func.sum(PaymentOrder.amount_brl), 0)).where(
            PaymentOrder.status == PaymentStatus.paid, PaymentOrder.paid_at >= since,
        )).scalar_one()

    paid_stmt = select(PaymentOrder).where(PaymentOrder.status == PaymentStatus.paid)
    total_paid_orders = db.execute(select(func.count()).select_from(paid_stmt.subquery())).scalar_one()
    total_revenue = db.execute(select(func.coalesce(func.sum(PaymentOrder.amount_brl), 0)).where(
        PaymentOrder.status == PaymentStatus.paid)).scalar_one()
    ticket_medio = (total_revenue / total_paid_orders) if total_paid_orders else Decimal(0)

    by_package = db.execute(
        select(CreditPackage.name, func.count(PaymentOrder.id), func.coalesce(func.sum(PaymentOrder.amount_brl), 0))
        .join(PaymentOrder, PaymentOrder.package_id == CreditPackage.id)
        .where(PaymentOrder.status == PaymentStatus.paid)
        .group_by(CreditPackage.name).order_by(func.count(PaymentOrder.id).desc())
    ).all()

    credit_totals = dict(db.execute(
        select(CreditTransaction.type, func.coalesce(func.sum(CreditTransaction.amount), 0))
        .group_by(CreditTransaction.type)
    ).all())

    checkout_started = db.execute(select(func.count(Event.id)).where(Event.event_type == "checkout_started")).scalar_one()
    credit_purchase = db.execute(select(func.count(Event.id)).where(Event.event_type == "credit_purchase")).scalar_one()
    conversion_rate = (credit_purchase / checkout_started) if checkout_started else None
    abandon_rate = (1 - conversion_rate) if conversion_rate is not None else None

    active_users_30d = db.execute(select(func.count(func.distinct(Event.user_id))).where(
        Event.created_at >= now - timedelta(days=30), Event.user_id.is_not(None))).scalar_one()
    paying_users = db.execute(select(func.count(func.distinct(PaymentOrder.user_id))).where(
        PaymentOrder.status == PaymentStatus.paid)).scalar_one()

    return {
        "revenue": {
            "today_brl": str(revenue_since(today0)), "month_brl": str(revenue_since(month0)),
            "year_brl": str(revenue_since(year0)), "total_brl": str(total_revenue),
            "ticket_medio_brl": str(ticket_medio),
        },
        "by_package": [{"name": n, "orders": c, "revenue_brl": str(r)} for n, c, r in by_package],
        "credits": {
            "vendidos": str(credit_totals.get(CreditTxType.purchase, 0)),
            "promocionais": str(credit_totals.get(CreditTxType.promo_credit, 0) + credit_totals.get(CreditTxType.bonus, 0)),
            "usados": str(abs(credit_totals.get(CreditTxType.consumption, 0))),
        },
        "funnel": {
            "checkout_started": checkout_started, "credit_purchase": credit_purchase,
            "conversion_rate": conversion_rate, "abandon_rate": abandon_rate,
        },
        "users": {"active_30d": active_users_30d, "paying_total": paying_users},
    }


# --------------------------------------------------------------- suporte
def list_tickets(db: Session, status_filter: str | None) -> dict:
    rows = support_service.list_all(db, status_filter)
    return {"items": [{"id": str(t.id), "user_id": str(t.user_id), "category": t.category,
                       "subject": t.subject, "message": t.message, "status": t.status,
                       "order_id": str(t.order_id) if t.order_id else None, "admin_notes": t.admin_notes,
                       "created_at": t.created_at.isoformat(),
                       "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None} for t in rows]}


def patch_ticket(db: Session, admin: User, ticket_id: str, data: support_schemas.TicketPatch, ip) -> dict:
    t = support_service.patch_ticket(db, uuid.UUID(ticket_id), data)
    audit(db, admin, "support_ticket_update", "support_ticket", t.id, after={"status": t.status}, ip=ip)
    db.commit()
    return {"id": str(t.id), "status": t.status}


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
