"""Serviços do Painel Administrativo. Toda mutação registra AdminAuditLog (auditoria completa).
Opera sobre os mesmos serviços de domínio (ledger, legal, etc.) — sem duplicar regra."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.domains.admin import schemas
from app.domains.admin.models import AdminAuditLog, Banner, PlatformSetting
from app.domains.affiliates import service as affiliates_service
from app.domains.affiliates.models import Affiliate, AffiliateCommission, AffiliatePayment, DemoAccessLog
from app.domains.analysis.models import Analysis
from app.domains.analytics.models import Event
from app.domains.bets.models import Bet
from app.domains.campaigns.models import Campaign, CampaignAffiliate, CampaignCoupon, CampaignPackage
from app.domains.enums import CreditTxType, PaymentStatus, UserRole, UserStatus
from app.domains.legal import service as legal_service
from app.domains.payments.models import CreditPackage, PaymentOrder
from app.domains.promotions.models import Coupon, Promotion
from app.domains.support import schemas as support_schemas
from app.domains.support import service as support_service
from app.domains.users.models import User
from app.domains.wallet.models import CreditTransaction, Wallet
from app.domains.wallet.service import get_or_create_wallet, post_transaction

_PARTNER_PROMOTION_CODE = "parceiros"


def _utc(dt: datetime | None) -> datetime | None:
    """Normaliza para aware-UTC — no SQLite (dev/testes) DateTime(timezone=True) não
    preserva tzinfo na volta (mesmo padrão de affiliates/service.py::_utc)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

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
           "valid_to": c.valid_to.isoformat() if c.valid_to else None,
           "first_purchase_only": c.first_purchase_only, "description": c.description, "active": c.active}


def create_coupon(db: Session, admin: User, data: schemas.CouponRequest, ip) -> dict:
    from app.domains.enums import CouponDiscountType
    try:
        dtype = CouponDiscountType(data.discount_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de desconto inválido.")
    if db.execute(select(Coupon).where(Coupon.code == data.code)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Código de cupom já existe.")
    valid_to = data.valid_to
    if valid_to is None and data.valid_days:
        valid_to = datetime.now(timezone.utc) + timedelta(days=data.valid_days)
    c = Coupon(
        promotion_id=uuid.UUID(data.promotion_id), code=data.code.strip().upper(), discount_type=dtype,
        discount_value=data.discount_value, bonus_credits=data.bonus_credits,
        min_purchase_brl=data.min_purchase_brl,
        package_id=uuid.UUID(data.package_id) if data.package_id else None,
        usage_limit=data.usage_limit, per_user_limit=data.per_user_limit,
        valid_from=data.valid_from, valid_to=valid_to,
        first_purchase_only=data.first_purchase_only, description=data.description, active=data.active,
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
    if data.first_purchase_only is not None: c.first_purchase_only = data.first_purchase_only
    if data.description is not None: c.description = data.description
    if data.active is not None: c.active = data.active
    audit(db, admin, "coupon_update", "coupon", c.id, before=before, after=_coupon_out(c), ip=ip)
    db.commit()
    return _coupon_out(c)


def delete_coupon(db: Session, admin: User, coupon_id: str, ip) -> None:
    try:
        c = db.get(Coupon, uuid.UUID(coupon_id))
    except ValueError:
        c = None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cupom não encontrado.")
    audit(db, admin, "coupon_delete", "coupon", c.id, before={"code": c.code}, ip=ip)
    db.delete(c)
    db.commit()


def list_coupons(db: Session) -> dict:
    rows = db.execute(select(Coupon).order_by(Coupon.created_at.desc())).scalars().all()
    return {"items": [_coupon_out(c) for c in rows]}


def coupon_analytics(db: Session) -> dict:
    """Por cupom: receita gerada, desconto total concedido, ticket médio, resgates,
    conversão (pagos / vezes que o cupom foi aplicado no checkout) e um ROI simplificado
    (receita / desconto concedido — proxy, não mede incrementalidade real sem holdout)."""
    rows = db.execute(select(Coupon).order_by(Coupon.created_at.desc())).scalars().all()
    out = []
    for c in rows:
        paid = db.execute(select(PaymentOrder).where(
            PaymentOrder.coupon_id == c.id, PaymentOrder.status == PaymentStatus.paid)).scalars().all()
        revenue = sum((o.amount_brl for o in paid), Decimal("0"))
        discount = sum((o.discount_amount_brl for o in paid), Decimal("0"))
        applied = db.execute(select(func.count(Event.id)).where(
            Event.event_type == "coupon_applied", Event.event_metadata["code"].as_string() == c.code
        )).scalar_one()
        conversion = (len(paid) / applied) if applied else None
        roi = float(revenue / discount) if discount > 0 else None
        out.append({
            "coupon_id": str(c.id), "code": c.code, "redemptions": c.redemptions,
            "orders_paid": len(paid), "revenue_brl": str(revenue), "discount_given_brl": str(discount),
            "ticket_medio_brl": str(revenue / len(paid)) if paid else "0",
            "conversion": conversion, "roi": roi,
        })
    return {"items": out}


# --------------------------------------------------------------- parceiros (afiliados)
def _affiliate_out(a: Affiliate, db: Session) -> dict:
    due = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == a.id, AffiliateCommission.status == "devida")).scalar_one()
    paid = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == a.id, AffiliateCommission.status == "paga")).scalar_one()
    account_status = None
    if a.user_id:
        u = db.get(User, a.user_id)
        account_status = u.status.value if u else None
    return {"id": str(a.id), "name": a.name, "code": a.code, "user_id": str(a.user_id) if a.user_id else None,
           "commission_pct": str(a.commission_pct) if a.commission_pct else None,
           "commission_fixed_brl": str(a.commission_fixed_brl) if a.commission_fixed_brl else None,
           "status": a.status, "notes": a.notes,
           "contact_email": a.contact_email, "contact_phone": a.contact_phone,
           "payment_type": a.payment_type.value if a.payment_type else None,
           "discount_pct": str(a.discount_pct) if a.discount_pct is not None else None,
           "demo_access_enabled": a.demo_access_enabled, "account_status": account_status,
           "commission_due_brl": str(due), "commission_paid_brl": str(paid)}


def _get_affiliate(db: Session, affiliate_id: str) -> Affiliate:
    try:
        a = db.get(Affiliate, uuid.UUID(affiliate_id))
    except ValueError:
        a = None
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Parceiro não encontrado.")
    return a


def _get_or_create_partner_promotion(db: Session) -> Promotion:
    from app.domains.enums import PromotionType
    promo = db.execute(select(Promotion).where(Promotion.code == _PARTNER_PROMOTION_CODE)).scalar_one_or_none()
    if promo is None:
        promo = Promotion(code=_PARTNER_PROMOTION_CODE, name="Cupons de parceiros",
                          type=PromotionType.coupon, active=True)
        db.add(promo)
        db.flush()
    return promo


def _create_partner_invite(db: Session, admin: User, affiliate: Affiliate, ip) -> None:
    """Cria (ou reaproveita) a conta do parceiro (role=partner) + o cupom vinculado ao seu
    código, e envia o e-mail com o link para definir senha (mesmo padrão de token de
    escopo restrito usado no cadastro comum — ver auth/service.py::set_password)."""
    from app.core import security
    from app.core.email import EmailSendError, send_partner_invite_email
    from app.domains.enums import CouponDiscountType

    if not (affiliate.cpf and affiliate.contact_email and affiliate.contact_phone):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="CPF, e-mail e telefone são obrigatórios para enviar o convite.")

    user = db.get(User, affiliate.user_id) if affiliate.user_id else None
    if user is None:
        user = db.execute(select(User).where(User.email == affiliate.contact_email.lower())).scalar_one_or_none()
    if user is None:
        user = User(
            full_name=affiliate.name, email=affiliate.contact_email.lower(),
            cpf=affiliate.cpf, phone=affiliate.contact_phone,
            status=UserStatus.pending_verification, role=UserRole.partner,
        )
        db.add(user)
        db.flush()
    else:
        user.role = UserRole.partner
    affiliate.user_id = user.id

    if affiliate.discount_pct is not None:
        promo = _get_or_create_partner_promotion(db)
        coupon = db.execute(select(Coupon).where(Coupon.affiliate_id == affiliate.id)).scalar_one_or_none()
        if coupon is None:
            db.add(Coupon(
                promotion_id=promo.id, code=affiliate.code.strip().upper(),
                discount_type=CouponDiscountType.percentage, discount_value=affiliate.discount_pct,
                affiliate_id=affiliate.id, active=True,
            ))
        else:
            coupon.discount_value = affiliate.discount_pct
            coupon.active = True

    token = security.create_access_token(str(user.id), extra={"scope": "partner_invite"})
    link = f"{settings.frontend_base_url}/parceiro/definir-senha?token={token}"
    try:
        send_partner_invite_email(affiliate.contact_email, link)
    except EmailSendError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            detail="Não foi possível enviar o e-mail de convite. Tente novamente em instantes.") from e


def create_affiliate(db: Session, admin: User, data: schemas.AffiliateRequest, ip) -> dict:
    from app.domains.enums import PartnerPaymentType
    if affiliates_service.code_in_use(db, data.code):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Código de afiliado já existe.")
    a = Affiliate(name=data.name, code=data.code.strip().upper(),
                 user_id=uuid.UUID(data.user_id) if data.user_id else None,
                 commission_pct=data.commission_pct, commission_fixed_brl=data.commission_fixed_brl,
                 contact_email=data.contact_email, contact_phone=data.contact_phone,
                 cpf=data.cpf, notes=data.notes,
                 payment_type=PartnerPaymentType(data.payment_type) if data.payment_type else None,
                 discount_pct=data.discount_pct, status="active")
    db.add(a); db.flush()
    audit(db, admin, "affiliate_create", "affiliate", a.id, after={"code": a.code}, ip=ip)
    # Recrutamento direto pelo admin (sem passar pela fila de solicitação): já provisiona
    # a conta do parceiro e envia o convite, se houver contato completo o bastante e o
    # afiliado não estiver sendo linkado a uma conta de usuário já existente.
    if data.user_id is None and a.cpf and a.contact_email and a.contact_phone:
        _create_partner_invite(db, admin, a, ip)
    db.commit()
    return _affiliate_out(a, db)


def patch_affiliate(db: Session, admin: User, affiliate_id: str, data: schemas.AffiliatePatch, ip) -> dict:
    from app.domains.enums import PartnerPaymentType
    a = _get_affiliate(db, affiliate_id)
    before = {"status": a.status, "commission_pct": str(a.commission_pct) if a.commission_pct else None}
    if data.name is not None: a.name = data.name
    if data.code is not None: affiliates_service.set_affiliate_code(db, a, data.code)
    if data.commission_fixed_brl is not None: a.commission_fixed_brl = data.commission_fixed_brl
    if data.status is not None: a.status = data.status
    if data.contact_email is not None: a.contact_email = data.contact_email
    if data.contact_phone is not None: a.contact_phone = data.contact_phone
    if data.cpf is not None: a.cpf = data.cpf
    if data.notes is not None: a.notes = data.notes
    if data.payment_type is not None: a.payment_type = PartnerPaymentType(data.payment_type)
    if data.discount_pct is not None:
        a.discount_pct = data.discount_pct
        coupon = db.execute(select(Coupon).where(Coupon.affiliate_id == a.id)).scalar_one_or_none()
        if coupon is not None:
            coupon.discount_value = data.discount_pct
    # commission_pct explícito sempre vence; senão, se o tier de desconto mudou, deriva
    # da fórmula (30 - desconto) — mesma regra usada na aprovação da solicitação.
    if data.commission_pct is not None:
        a.commission_pct = data.commission_pct
    elif data.discount_pct is not None:
        a.commission_pct = affiliates_service.COMMISSION_BUDGET_PCT - data.discount_pct
    audit(db, admin, "affiliate_update", "affiliate", a.id, before=before,
          after={"status": a.status}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def approve_affiliate(db: Session, admin: User, affiliate_id: str, ip, code: str | None = None) -> dict:
    a = _get_affiliate(db, affiliate_id)
    if a.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitação não está pendente.")
    before = {"status": a.status}
    if code is not None and code.strip():
        affiliates_service.set_affiliate_code(db, a, code)
    a.status = "active"
    _create_partner_invite(db, admin, a, ip)
    audit(db, admin, "affiliate_approve", "affiliate", a.id, before=before, after={"status": a.status}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def reject_affiliate(db: Session, admin: User, affiliate_id: str, data: schemas.AffiliateRejectRequest, ip) -> dict:
    a = _get_affiliate(db, affiliate_id)
    if a.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Solicitação não está pendente.")
    before = {"status": a.status}
    a.status = "rejected"
    if data.reason:
        a.notes = data.reason
    audit(db, admin, "affiliate_reject", "affiliate", a.id, before=before,
          after={"status": a.status, "reason": data.reason}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def resend_affiliate_invite(db: Session, admin: User, affiliate_id: str, ip) -> dict:
    a = _get_affiliate(db, affiliate_id)
    if a.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Só é possível reenviar convite para parceiros ativos.")
    _create_partner_invite(db, admin, a, ip)
    audit(db, admin, "affiliate_resend_invite", "affiliate", a.id, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def set_affiliate_demo_access(db: Session, admin: User, affiliate_id: str,
                              data: schemas.AffiliateDemoAccessRequest, ip) -> dict:
    a = _get_affiliate(db, affiliate_id)
    before = {"demo_access_enabled": a.demo_access_enabled}
    a.demo_access_enabled = data.enabled
    audit(db, admin, "affiliate_demo_access", "affiliate", a.id, before=before,
          after={"demo_access_enabled": a.demo_access_enabled}, ip=ip)
    db.commit()
    return _affiliate_out(a, db)


def get_affiliate_detail(db: Session, affiliate_id: str) -> dict:
    a = _get_affiliate(db, affiliate_id)
    stats = affiliates_service.compute_portal_stats(db, a) if a.user_id else {
        "code": a.code, "link": f"{settings.frontend_base_url}/?ref={a.code}",
        "clicks": 0, "signups": 0, "buyers": 0, "revenue_brl": "0",
        "commission_due_brl": "0", "commission_paid_brl": "0",
    }
    demo_logs = db.execute(select(DemoAccessLog).where(
        DemoAccessLog.affiliate_id == a.id).order_by(DemoAccessLog.created_at.desc()).limit(50)).scalars().all()
    return {
        **_affiliate_out(a, db), **stats,
        "payments": list_affiliate_payments(db, affiliate_id)["items"],
        "demo_access_logs": [{"cpf_used": l.cpf_used, "ip": l.ip, "created_at": l.created_at.isoformat()}
                             for l in demo_logs],
    }


def demo_usage_by_cpf(db: Session) -> dict:
    """Quantas análises cada CPF gerou na conta demo compartilhada — para o admin flagar
    parceiro revendendo análises por fora. A conta demo é UMA só (User.is_demo), então não
    dá pra saber por CPF direto da Analysis; aproximamos por janelas de sessão: cada
    DemoAccessLog marca o início de uma janela (até o próximo login-demo, de qualquer CPF,
    ou agora) e contamos as análises da conta demo criadas dentro dela."""
    demo_user = db.execute(select(User).where(User.is_demo.is_(True))).scalars().first()
    if demo_user is None:
        return {"items": []}
    logs = db.execute(select(DemoAccessLog).order_by(DemoAccessLog.created_at.asc())).scalars().all()
    if not logs:
        return {"items": []}
    analysis_times = [_utc(t) for t in db.execute(select(Analysis.created_at).where(
        Analysis.user_id == demo_user.id).order_by(Analysis.created_at.asc())).scalars().all()]

    now = datetime.now(timezone.utc)
    per_cpf: dict[str, dict] = {}
    n = len(logs)
    for i, log in enumerate(logs):
        window_start = _utc(log.created_at)
        window_end = _utc(logs[i + 1].created_at) if i + 1 < n else now
        count = sum(1 for t in analysis_times if window_start <= t < window_end)
        entry = per_cpf.setdefault(log.cpf_used, {
            "cpf": log.cpf_used, "affiliate_id": str(log.affiliate_id),
            "logins": 0, "analyses": 0, "last_login_at": window_start,
        })
        entry["logins"] += 1
        entry["analyses"] += count
        if window_start > entry["last_login_at"]:
            entry["last_login_at"] = window_start

    affiliate_ids = {uuid.UUID(e["affiliate_id"]) for e in per_cpf.values()}
    affiliates = {a.id: a for a in db.execute(select(Affiliate).where(Affiliate.id.in_(affiliate_ids))).scalars()}
    items = []
    for e in per_cpf.values():
        aff = affiliates.get(uuid.UUID(e["affiliate_id"]))
        items.append({
            "cpf": e["cpf"], "affiliate_name": aff.name if aff else None,
            "logins": e["logins"], "analyses": e["analyses"],
            "last_login_at": e["last_login_at"].isoformat(),
        })
    items.sort(key=lambda e: e["analyses"], reverse=True)
    return {"items": items}


def list_affiliates(db: Session, status_filter: str | None = None) -> dict:
    stmt = select(Affiliate)
    if status_filter:
        stmt = stmt.where(Affiliate.status == status_filter)
    rows = db.execute(stmt.order_by(Affiliate.created_at.desc())).scalars().all()
    return {"items": [_affiliate_out(a, db) for a in rows]}


# --------------------------------------------------------------- pagamentos a afiliados
def create_affiliate_payment(db: Session, admin: User, affiliate_id: str,
                             data: schemas.AffiliatePaymentRequest, ip) -> dict:
    """Registra um lote de pagamento e marca em lote as comissões 'devida' do afiliado no
    período coberto como 'paga' — nunca cria comissão nova, só liquida as existentes."""
    try:
        aff_uuid = uuid.UUID(affiliate_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Afiliado não encontrado.")
    if db.get(Affiliate, aff_uuid) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Afiliado não encontrado.")

    payment = AffiliatePayment(
        affiliate_id=aff_uuid, amount_brl=data.amount_brl,
        period_start=data.period_start, period_end=data.period_end,
        paid_at=datetime.now(timezone.utc), method=data.method,
        receipt_url=data.receipt_url, notes=data.notes, status="paid",
    )
    db.add(payment); db.flush()

    stmt = select(AffiliateCommission).where(
        AffiliateCommission.affiliate_id == aff_uuid, AffiliateCommission.status == "devida")
    if data.period_start:
        stmt = stmt.where(AffiliateCommission.created_at >= data.period_start)
    if data.period_end:
        stmt = stmt.where(AffiliateCommission.created_at <= data.period_end)
    commissions = db.execute(stmt).scalars().all()
    for c in commissions:
        c.status = "paga"; c.paid_at = payment.paid_at; c.payment_id = payment.id

    audit(db, admin, "affiliate_payment_create", "affiliate_payment", payment.id,
          after={"affiliate_id": affiliate_id, "amount_brl": str(data.amount_brl),
                "commissions_covered": len(commissions)}, ip=ip)
    db.commit()
    return {"id": str(payment.id), "affiliate_id": affiliate_id, "amount_brl": str(payment.amount_brl),
           "status": payment.status, "commissions_covered": len(commissions)}


def list_affiliate_payments(db: Session, affiliate_id: str) -> dict:
    rows = db.execute(select(AffiliatePayment).where(
        AffiliatePayment.affiliate_id == uuid.UUID(affiliate_id)
    ).order_by(AffiliatePayment.created_at.desc())).scalars().all()
    return {"items": [{"id": str(p.id), "amount_brl": str(p.amount_brl),
                       "period_start": p.period_start.isoformat() if p.period_start else None,
                       "period_end": p.period_end.isoformat() if p.period_end else None,
                       "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                       "method": p.method, "receipt_url": p.receipt_url, "notes": p.notes,
                       "status": p.status} for p in rows]}


# --------------------------------------------------------------- campanhas
def _campaign_out(db: Session, c: Campaign) -> dict:
    package_ids = [str(r[0]) for r in db.execute(
        select(CampaignPackage.package_id).where(CampaignPackage.campaign_id == c.id))]
    coupon_ids = [str(r[0]) for r in db.execute(
        select(CampaignCoupon.coupon_id).where(CampaignCoupon.campaign_id == c.id))]
    affiliate_ids = [str(r[0]) for r in db.execute(
        select(CampaignAffiliate.affiliate_id).where(CampaignAffiliate.campaign_id == c.id))]
    return {"id": str(c.id), "name": c.name, "banner_id": str(c.banner_id) if c.banner_id else None,
           "starts_at": c.starts_at.isoformat() if c.starts_at else None,
           "ends_at": c.ends_at.isoformat() if c.ends_at else None,
           "priority": c.priority, "active": c.active,
           "package_ids": package_ids, "coupon_ids": coupon_ids, "affiliate_ids": affiliate_ids}


def create_campaign(db: Session, admin: User, data: schemas.CampaignRequest, ip) -> dict:
    c = Campaign(name=data.name, banner_id=uuid.UUID(data.banner_id) if data.banner_id else None,
                starts_at=data.starts_at, ends_at=data.ends_at, priority=data.priority, active=data.active)
    db.add(c); db.flush()
    audit(db, admin, "campaign_create", "campaign", c.id, after={"name": c.name}, ip=ip)
    db.commit()
    return _campaign_out(db, c)


def patch_campaign(db: Session, admin: User, campaign_id: str, data: schemas.CampaignPatch, ip) -> dict:
    try:
        c = db.get(Campaign, uuid.UUID(campaign_id))
    except ValueError:
        c = None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada.")
    before = _campaign_out(db, c)
    if data.name is not None: c.name = data.name
    if data.banner_id is not None: c.banner_id = uuid.UUID(data.banner_id) if data.banner_id else None
    if data.starts_at is not None: c.starts_at = data.starts_at
    if data.ends_at is not None: c.ends_at = data.ends_at
    if data.priority is not None: c.priority = data.priority
    if data.active is not None: c.active = data.active
    audit(db, admin, "campaign_update", "campaign", c.id, before=before, after=_campaign_out(db, c), ip=ip)
    db.commit()
    return _campaign_out(db, c)


def delete_campaign(db: Session, admin: User, campaign_id: str, ip) -> None:
    try:
        c = db.get(Campaign, uuid.UUID(campaign_id))
    except ValueError:
        c = None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada.")
    audit(db, admin, "campaign_delete", "campaign", c.id, before={"name": c.name}, ip=ip)
    db.delete(c)
    db.commit()


def list_campaigns(db: Session) -> dict:
    rows = db.execute(select(Campaign).order_by(Campaign.priority.desc(), Campaign.created_at.desc())).scalars().all()
    return {"items": [_campaign_out(db, c) for c in rows]}


def _get_campaign(db: Session, campaign_id: str) -> Campaign:
    try:
        c = db.get(Campaign, uuid.UUID(campaign_id))
    except ValueError:
        c = None
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Campanha não encontrada.")
    return c


def add_campaign_package(db: Session, admin: User, campaign_id: str, package_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    pkg_uuid = uuid.UUID(package_id)
    if db.get(CampaignPackage, (c.id, pkg_uuid)) is None:
        db.add(CampaignPackage(campaign_id=c.id, package_id=pkg_uuid))
        audit(db, admin, "campaign_add_package", "campaign", c.id, after={"package_id": package_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def remove_campaign_package(db: Session, admin: User, campaign_id: str, package_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    row = db.get(CampaignPackage, (c.id, uuid.UUID(package_id)))
    if row is not None:
        db.delete(row)
        audit(db, admin, "campaign_remove_package", "campaign", c.id, before={"package_id": package_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def add_campaign_coupon(db: Session, admin: User, campaign_id: str, coupon_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    coupon_uuid = uuid.UUID(coupon_id)
    if db.get(CampaignCoupon, (c.id, coupon_uuid)) is None:
        db.add(CampaignCoupon(campaign_id=c.id, coupon_id=coupon_uuid))
        audit(db, admin, "campaign_add_coupon", "campaign", c.id, after={"coupon_id": coupon_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def remove_campaign_coupon(db: Session, admin: User, campaign_id: str, coupon_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    row = db.get(CampaignCoupon, (c.id, uuid.UUID(coupon_id)))
    if row is not None:
        db.delete(row)
        audit(db, admin, "campaign_remove_coupon", "campaign", c.id, before={"coupon_id": coupon_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def add_campaign_affiliate(db: Session, admin: User, campaign_id: str, affiliate_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    aff_uuid = uuid.UUID(affiliate_id)
    if db.get(CampaignAffiliate, (c.id, aff_uuid)) is None:
        db.add(CampaignAffiliate(campaign_id=c.id, affiliate_id=aff_uuid))
        audit(db, admin, "campaign_add_affiliate", "campaign", c.id, after={"affiliate_id": affiliate_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def remove_campaign_affiliate(db: Session, admin: User, campaign_id: str, affiliate_id: str, ip) -> dict:
    c = _get_campaign(db, campaign_id)
    row = db.get(CampaignAffiliate, (c.id, uuid.UUID(affiliate_id)))
    if row is not None:
        db.delete(row)
        audit(db, admin, "campaign_remove_affiliate", "campaign", c.id, before={"affiliate_id": affiliate_id}, ip=ip)
        db.commit()
    return _campaign_out(db, c)


def campaign_dashboard(db: Session, campaign_id: str) -> dict:
    """Receita/conversão/ROI atribuídos à campanha: pedidos pagos cujo pacote OU cupom
    esteja associado a ela. ROI = receita / (desconto concedido pelos cupons da campanha +
    comissões de afiliados da campanha) — proxy, sem holdout pra causalidade real."""
    c = _get_campaign(db, campaign_id)
    package_ids = [r[0] for r in db.execute(
        select(CampaignPackage.package_id).where(CampaignPackage.campaign_id == c.id))]
    coupon_ids = [r[0] for r in db.execute(
        select(CampaignCoupon.coupon_id).where(CampaignCoupon.campaign_id == c.id))]
    affiliate_ids = [r[0] for r in db.execute(
        select(CampaignAffiliate.affiliate_id).where(CampaignAffiliate.campaign_id == c.id))]

    from sqlalchemy import or_ as _or
    order_filters = []
    if package_ids: order_filters.append(PaymentOrder.package_id.in_(package_ids))
    if coupon_ids: order_filters.append(PaymentOrder.coupon_id.in_(coupon_ids))
    if not order_filters:
        return {"campaign": _campaign_out(db, c), "revenue_brl": "0", "orders": 0, "ticket_medio_brl": "0",
               "discount_given_brl": "0", "coupons_used": 0, "affiliate_commission_brl": "0",
               "roi": None, "new_users": 0}

    paid = db.execute(select(PaymentOrder).where(
        PaymentOrder.status == PaymentStatus.paid, _or(*order_filters))).scalars().all()
    revenue = sum((o.amount_brl for o in paid), Decimal("0"))
    discount = sum((o.discount_amount_brl for o in paid), Decimal("0"))
    coupons_used = sum(1 for o in paid if o.coupon_id in coupon_ids)

    commission = Decimal("0")
    if affiliate_ids:
        commission = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
            AffiliateCommission.affiliate_id.in_(affiliate_ids))).scalar_one()

    cost = discount + commission
    roi = float(revenue / cost) if cost > 0 else None

    new_users = 0
    if c.starts_at:
        end = c.ends_at or datetime.now(timezone.utc)
        new_users = db.execute(select(func.count(User.id)).where(
            User.created_at >= c.starts_at, User.created_at <= end)).scalar_one()

    return {
        "campaign": _campaign_out(db, c), "revenue_brl": str(revenue), "orders": len(paid),
        "ticket_medio_brl": str(revenue / len(paid)) if paid else "0",
        "discount_given_brl": str(discount), "coupons_used": coupons_used,
        "affiliate_commission_brl": str(commission), "roi": roi, "new_users": new_users,
    }


# --------------------------------------------------------------- pacotes de crédito
def _package_out(p: CreditPackage) -> dict:
    return {"id": str(p.id), "name": p.name, "credits": p.credits, "price_brl": str(p.price_brl),
           "bonus_credits": p.bonus_credits, "featured_badge": p.featured_badge.value if p.featured_badge else None,
           "sort_order": p.sort_order, "status": p.status.value}


def list_packages_admin(db: Session) -> dict:
    rows = db.execute(select(CreditPackage).order_by(CreditPackage.sort_order, CreditPackage.credits)).scalars().all()
    return {"items": [_package_out(p) for p in rows]}


def create_package(db: Session, admin: User, data: schemas.PackageRequest, ip) -> dict:
    from app.domains.enums import PackageBadge, PackageStatus
    p = CreditPackage(
        name=data.name, credits=data.credits, price_brl=data.price_brl, bonus_credits=data.bonus_credits,
        featured_badge=PackageBadge(data.featured_badge) if data.featured_badge else None,
        sort_order=data.sort_order, status=PackageStatus(data.status),
    )
    db.add(p); db.flush()
    audit(db, admin, "package_create", "credit_package", p.id, after={"name": p.name}, ip=ip)
    db.commit()
    return _package_out(p)


def patch_package(db: Session, admin: User, package_id: str, data: schemas.PackagePatch, ip) -> dict:
    from app.domains.enums import PackageBadge, PackageStatus
    try:
        p = db.get(CreditPackage, uuid.UUID(package_id))
    except ValueError:
        p = None
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Pacote não encontrado.")
    before = _package_out(p)
    if data.name is not None: p.name = data.name
    if data.credits is not None: p.credits = data.credits
    if data.price_brl is not None: p.price_brl = data.price_brl
    if data.bonus_credits is not None: p.bonus_credits = data.bonus_credits
    if "featured_badge" in data.model_fields_set:
        p.featured_badge = PackageBadge(data.featured_badge) if data.featured_badge else None
    if data.sort_order is not None: p.sort_order = data.sort_order
    if data.status is not None: p.status = PackageStatus(data.status)
    audit(db, admin, "package_update", "credit_package", p.id, before=before, after=_package_out(p), ip=ip)
    db.commit()
    return _package_out(p)


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
            "ticket_medio_brl": str(ticket_medio.quantize(Decimal("0.01"))),
        },
        "by_package": [{"name": n, "orders": c, "revenue_brl": str(r)} for n, c, r in by_package],
        "credits": {
            "vendidos": str(int(credit_totals.get(CreditTxType.purchase, 0))),
            "promocionais": str(int(credit_totals.get(CreditTxType.promo_credit, 0) + credit_totals.get(CreditTxType.bonus, 0))),
            "usados": str(int(abs(credit_totals.get(CreditTxType.consumption, 0)))),
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


def _banner_out(b: Banner) -> dict:
    return {"id": str(b.id), "title": b.title, "body": b.body, "image_url": b.image_url,
           "type": b.type, "active": b.active,
           "starts_at": b.starts_at.isoformat() if b.starts_at else None,
           "ends_at": b.ends_at.isoformat() if b.ends_at else None,
           "priority": b.priority, "sort_order": b.sort_order}


def create_banner(db: Session, admin: User, data: schemas.BannerRequest, ip) -> dict:
    b = Banner(title=data.title, body=data.body, image_url=data.image_url, type=data.type, active=data.active,
               starts_at=data.starts_at, ends_at=data.ends_at,
               priority=data.priority, sort_order=data.sort_order)
    db.add(b); db.flush()
    audit(db, admin, "banner_create", "banner", b.id, after={"title": data.title}, ip=ip)
    db.commit()
    return _banner_out(b)


def patch_banner(db: Session, admin: User, banner_id: str, data: schemas.BannerPatch, ip) -> dict:
    try:
        b = db.get(Banner, uuid.UUID(banner_id))
    except ValueError:
        b = None
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Banner não encontrado.")
    before = _banner_out(b)
    if data.title is not None: b.title = data.title
    if data.body is not None: b.body = data.body
    if data.image_url is not None: b.image_url = data.image_url
    if data.type is not None: b.type = data.type
    if data.active is not None: b.active = data.active
    if data.starts_at is not None: b.starts_at = data.starts_at
    if data.ends_at is not None: b.ends_at = data.ends_at
    if data.priority is not None: b.priority = data.priority
    if data.sort_order is not None: b.sort_order = data.sort_order
    audit(db, admin, "banner_update", "banner", b.id, before=before, after=_banner_out(b), ip=ip)
    db.commit()
    return _banner_out(b)


def delete_banner(db: Session, admin: User, banner_id: str, ip) -> None:
    try:
        b = db.get(Banner, uuid.UUID(banner_id))
    except ValueError:
        b = None
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Banner não encontrado.")
    audit(db, admin, "banner_delete", "banner", b.id, before={"title": b.title}, ip=ip)
    db.delete(b)
    db.commit()


def list_banners(db: Session) -> dict:
    rows = db.execute(select(Banner).order_by(
        Banner.priority.desc(), Banner.sort_order, Banner.created_at.desc())).scalars().all()
    return {"items": [_banner_out(b) for b in rows]}


# --------------------------------------------------------------- auditoria
def list_audit(db: Session, limit: int, offset: int) -> dict:
    total = db.execute(select(func.count(AdminAuditLog.id))).scalar_one()
    rows = db.execute(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
                      .limit(limit).offset(offset)).scalars().all()
    admin_ids = [a.admin_id for a in rows if a.admin_id]
    admins = {u.id: u for u in db.execute(select(User).where(User.id.in_(admin_ids)))
              .scalars()} if admin_ids else {}
    return {"items": [{"id": str(a.id), "admin_id": str(a.admin_id) if a.admin_id else None,
                       "admin_name": admins[a.admin_id].full_name if a.admin_id in admins else None,
                       "admin_email": admins[a.admin_id].email if a.admin_id in admins else None,
                       "action": a.action, "target_type": a.target_type,
                       "target_id": str(a.target_id) if a.target_id else None,
                       "before": a.before, "after": a.after, "created_at": a.created_at.isoformat()}
                      for a in rows], "total": total, "limit": limit, "offset": offset}
