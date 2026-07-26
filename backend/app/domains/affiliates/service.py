"""Rastreamento de clique/atribuição + cálculo de comissão. Comissão só é calculada
quando o pedido é confirmado (chamado a partir de payments/service._credit_if_paid),
e só uma vez por PaymentOrder (unique em AffiliateCommission.order_id)."""
from __future__ import annotations

import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.affiliates import schemas
from app.domains.affiliates.models import Affiliate, AffiliateAttribution, AffiliateCommission
from app.domains.enums import CommissionKind, PartnerPaymentType

_DEFAULT_ATTRIBUTION_DAYS = 30
_CODE_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
COMMISSION_BUDGET_PCT = Decimal(30)
# CPF do administrador (valerioeducfin@gmail.com) — acesso à conta demo sempre liberado
# para ele, independentemente do status/demo_access_enabled de qualquer Affiliate no banco
# (não pode ser revogado sem querer pelo próprio painel admin).
_ADMIN_ALWAYS_ON_CPF = "10341953440"


def _attribution_window_days(db: Session) -> int:
    from app.domains.admin.models import PlatformSetting
    s = db.execute(select(PlatformSetting).where(
        PlatformSetting.key == "affiliate_attribution_days")).scalar_one_or_none()
    if s and s.value and isinstance(s.value, dict) and "days" in s.value:
        try:
            return int(s.value["days"])
        except (TypeError, ValueError):
            pass
    return _DEFAULT_ATTRIBUTION_DAYS


def _generate_affiliate_code(db: Session, full_name: str) -> str:
    """Código curto derivado do nome + sufixo aleatório (mesmo padrão de
    auth/service.py::_generate_referral_code) — nunca colide por natureza."""
    first_name = (full_name.split() or ["parceiro"])[0]
    ascii_name = unicodedata.normalize("NFKD", first_name).encode("ascii", "ignore").decode("ascii")
    prefix = "".join(ch for ch in ascii_name.lower() if ch.isalnum())[:10] or "parceiro"
    for _ in range(20):
        suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        code = f"{prefix}{suffix}"
        if db.execute(select(Affiliate.id).where(Affiliate.code == code)).scalar_one_or_none() is None:
            return code
    raise RuntimeError("Não foi possível gerar um código de parceiro único.")


def _ascii_upper_alnum(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in ascii_text.upper() if ch.isalnum())


def code_in_use(db: Session, code: str, exclude_affiliate_id: uuid.UUID | None = None) -> bool:
    """Um código de parceiro vira o code do Coupon vinculado (ver _create_partner_invite em
    admin/service.py) — então a unicidade precisa valer nas duas tabelas."""
    from app.domains.promotions.models import Coupon

    code = code.strip().upper()
    aff_stmt = select(Affiliate.id).where(func.upper(Affiliate.code) == code)
    if exclude_affiliate_id is not None:
        aff_stmt = aff_stmt.where(Affiliate.id != exclude_affiliate_id)
    if db.execute(aff_stmt).scalar_one_or_none() is not None:
        return True
    if db.execute(select(Coupon.id).where(func.upper(Coupon.code) == code)).scalar_one_or_none() is not None:
        return True
    return False


def suggest_code_prefix(db: Session, full_name: str) -> str:
    """Sugestão de PREFIXO: primeiro nome; se colidir, soma letra a letra do(s) sobrenome(s)."""
    parts = [_ascii_upper_alnum(p) for p in full_name.split() if _ascii_upper_alnum(p)]
    if not parts:
        parts = ["PARCEIRO"]

    def taken(prefix: str) -> bool:
        return code_in_use(db, prefix)

    base = parts[0]
    if not taken(base):
        return base

    prefix = base
    for part in parts[1:]:
        for i in range(1, len(part) + 1):
            candidate = prefix + part[:i]
            if not taken(candidate):
                return candidate
        prefix += part

    for n in range(2, 1000):
        candidate = f"{base}{n}"
        if not taken(candidate):
            return candidate
    raise RuntimeError("Não foi possível sugerir um código de parceiro único.")


def resolve_partner_code(db: Session, full_name: str, requested_prefix: str | None) -> str:
    """O código base do parceiro agora é apenas o prefixo (o sufixo do desconto será anexado
    nos Coupons gerados na aprovação)."""
    if requested_prefix and requested_prefix.strip():
        prefix = _ascii_upper_alnum(requested_prefix)[:20]
        if not prefix:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código inválido.")
        code = prefix
        if code_in_use(db, code):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Esse código já está em uso. Escolha outro.")
        return code
    return suggest_code_prefix(db, full_name)


def set_affiliate_code(db: Session, affiliate: Affiliate, code: str) -> None:
    """Admin pode sobrescrever o código livremente (sem a restrição de sufixo que vale só
    para a autoedição do parceiro) — mantém o Coupon vinculado em sincronia."""
    from app.domains.promotions.models import Coupon

    normalized = _ascii_upper_alnum(code)[:60]
    if not normalized:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código inválido.")
    if normalized != affiliate.code.upper() and code_in_use(db, normalized, exclude_affiliate_id=affiliate.id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esse código já está em uso.")
    affiliate.code = normalized
    coupon = db.execute(select(Coupon).where(Coupon.affiliate_id == affiliate.id)).scalar_one_or_none()
    if coupon is not None:
        coupon.code = normalized


def apply_for_partnership(db: Session, data: "schemas.PartnerApplicationRequest") -> Affiliate:
    """Solicitação pública de parceria — nasce `pending`, sem User/Coupon (só criados na
    aprovação, ver admin/service.py::approve_affiliate)."""
    dup = db.execute(select(Affiliate).where(
        (Affiliate.cpf == data.cpf) | (func.lower(Affiliate.contact_email) == data.email.lower())
    )).scalars().all()
    for a in dup:
        if a.status in ("pending", "active", "paused"):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                detail="Já existe uma solicitação ou parceria com este CPF/e-mail.")
    code = resolve_partner_code(db, data.full_name, data.code_prefix)
    pcts_str = ",".join(str(int(p)) for p in data.discount_pcts)
    # A comissão base (para o primeiro/principal cupom) será usada caso necessário,
    # mas o real cálculo acontece por pedido/cupom no sistema de pagamento.
    main_pct = data.discount_pcts[0]
    # Indicação de parceiros: se veio via link de indicação (ref_partner), atrela ao
    # indicador (parent_affiliate_id, um nível). O indicado não vê o vínculo.
    parent_id = None
    if getattr(data, "ref_partner", None):
        parent = db.execute(select(Affiliate).where(
            func.upper(Affiliate.code) == data.ref_partner.strip().upper(),
            Affiliate.status == "active")).scalar_one_or_none()
        parent_id = parent.id if parent else None
    affiliate = Affiliate(
        name=data.full_name, code=code, status="pending",
        commission_pct=COMMISSION_BUDGET_PCT - main_pct, discount_pcts=pcts_str,
        payment_type=PartnerPaymentType(data.payment_type),
        cpf=data.cpf, contact_email=data.email.lower(), contact_phone=data.phone,
        parent_affiliate_id=parent_id,
    )
    db.add(affiliate)
    db.flush()
    return affiliate


def track_click(db: Session, code: str, anon_id: str, user_id: uuid.UUID | None = None) -> AffiliateAttribution | None:
    from app.domains.promotions.models import Coupon
    # Primeiro tenta achar o afiliado pelo código exato do cupom gerado (ex: VALERIO15)
    coupon = db.execute(select(Coupon).where(func.upper(Coupon.code) == code.strip().upper())).scalar_one_or_none()
    if coupon and coupon.affiliate_id:
        affiliate = db.get(Affiliate, coupon.affiliate_id)
    else:
        # Fallback: busca pelo código base do afiliado
        affiliate = db.execute(select(Affiliate).where(
            func.upper(Affiliate.code) == code.strip().upper(), Affiliate.status == "active")).scalar_one_or_none()
            
    if affiliate is None or affiliate.status != "active":
        return None
        
    now = datetime.now(timezone.utc)
    days = _attribution_window_days(db)
    attr = AffiliateAttribution(
        affiliate_id=affiliate.id, user_id=user_id, anon_id=anon_id,
        attributed_at=now, expires_at=now + timedelta(days=days),
    )
    db.add(attr)
    return attr


def attach_user_on_signup(db: Session, anon_id: str, user_id: uuid.UUID) -> None:
    """Liga a atribuição anônima (clique pré-cadastro) à conta recém-criada."""
    if not anon_id:
        return
    attrs = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.anon_id == anon_id, AffiliateAttribution.user_id.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().all()
    for a in attrs:
        a.user_id = user_id


def _utc(dt: datetime | None) -> datetime | None:
    """Normaliza para aware-UTC — no SQLite (dev/testes), DateTime(timezone=True) não
    preserva tzinfo na volta (ao contrário do Postgres em produção), então um
    `expires_at` gravado aware pode voltar naive e quebrar a comparação abaixo
    (mesmo padrão de auth/service.py::_utc)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _active_attribution_for_order(db: Session, user_id: uuid.UUID, paid_at: datetime) -> AffiliateAttribution | None:
    rows = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.user_id == user_id, AffiliateAttribution.converted_at.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().all()
    paid_at = _utc(paid_at)
    for a in rows:
        if a.expires_at is None or _utc(a.expires_at) >= paid_at:
            return a
    return None


def _order_commission_pct(db: Session, order, affiliate: Affiliate) -> Decimal | None:
    """% de comissão a aplicar na ordem. Se ela usou um CUPOM do próprio parceiro com
    commission_pct definido, usa o do cupom (permite splits diferentes por cupom — convite
    vs promocional, 30 − desconto); senão cai no commission_pct global do afiliado."""
    if order.coupon_id is not None:
        from app.domains.promotions.models import Coupon
        coupon = db.get(Coupon, order.coupon_id)
        if coupon is not None and coupon.affiliate_id == affiliate.id and coupon.commission_pct is not None:
            return Decimal(coupon.commission_pct)
    return Decimal(affiliate.commission_pct) if affiliate.commission_pct else None


def commission_for_order(db: Session, order) -> AffiliateCommission | None:
    """Chamado quando um PaymentOrder é confirmado — calcula e registra a comissão DIRETA
    do afiliado (se houver atribuição válida dentro da janela) e, se o afiliado tiver um
    parceiro indicador (parent_affiliate_id), o OVERRIDE de 5% para ele. Idempotente por
    (order_id, affiliate_id)."""
    direct = db.execute(select(AffiliateCommission).where(
        AffiliateCommission.order_id == order.id,
        AffiliateCommission.kind == CommissionKind.direct,
    )).scalar_one_or_none()
    if direct is not None:
        return direct

    attr = _active_attribution_for_order(db, order.user_id, order.paid_at or datetime.now(timezone.utc))
    if attr is None:
        return None
    affiliate = db.get(Affiliate, attr.affiliate_id)
    if affiliate is None or affiliate.status != "active":
        return None

    pct = _order_commission_pct(db, order, affiliate)
    amount = Decimal("0.00")
    if pct:
        amount += (Decimal(order.amount_brl) * pct / Decimal(100))
    if affiliate.commission_fixed_brl:
        amount += Decimal(affiliate.commission_fixed_brl)
    if amount <= 0:
        return None

    attr.converted_at = datetime.now(timezone.utc)
    order.affiliate_attribution_id = attr.id
    amount = amount.quantize(Decimal("0.01"))
    commission = AffiliateCommission(
        affiliate_id=affiliate.id, order_id=order.id, amount_brl=amount,
        status="devida", kind=CommissionKind.direct,
    )
    db.add(commission)
    db.flush()

    # Override de indicação de parceiros (5% da comissão do indicado ao indicador) — um
    # nível só, custo EXTRA do sistema (não descontado do indicado). Ver Fase 3.
    _override_commission_for_parent(db, order, affiliate, amount)
    return commission


def _partner_override_pct(db: Session) -> Decimal:
    """% do override de indicação de parceiros (default 5), sobrescrito pelo PlatformSetting
    'partner_override_pct'."""
    from app.domains.admin.models import PlatformSetting
    s = db.execute(select(PlatformSetting).where(
        PlatformSetting.key == "partner_override_pct")).scalar_one_or_none()
    if s and s.value and isinstance(s.value, dict) and "pct" in s.value:
        try:
            return Decimal(str(s.value["pct"]))
        except (TypeError, ValueError):
            pass
    return Decimal(5)


def _override_commission_for_parent(db: Session, order, child: Affiliate, direct_amount: Decimal) -> AffiliateCommission | None:
    """Se `child` foi indicado por outro parceiro (parent_affiliate_id) ativo, registra uma
    comissão de override (5% da comissão direta) para o indicador. NÃO desconta do indicado
    — é um valor a mais que o sistema paga pela indicação. Um nível só (não sobe ao avô).
    Idempotente por (order_id, parent_id)."""
    if not child.parent_affiliate_id:
        return None
    parent = db.get(Affiliate, child.parent_affiliate_id)
    if parent is None or parent.status != "active":
        return None
    existing = db.execute(select(AffiliateCommission).where(
        AffiliateCommission.order_id == order.id,
        AffiliateCommission.affiliate_id == parent.id,
        AffiliateCommission.kind == CommissionKind.override,
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    amount = (direct_amount * _partner_override_pct(db) / Decimal(100)).quantize(Decimal("0.01"))
    if amount <= 0:
        return None
    override = AffiliateCommission(
        affiliate_id=parent.id, order_id=order.id, amount_brl=amount, status="devida",
        kind=CommissionKind.override, source_affiliate_id=child.id,
    )
    db.add(override)
    db.flush()
    return override


def attach_checkout_attribution(db: Session, user_id: uuid.UUID, affiliate_id: uuid.UUID) -> AffiliateAttribution:
    """Chamado quando um cupom de parceiro (Coupon.affiliate_id) é usado no checkout —
    atribui a venda ao parceiro imediatamente, sem depender de clique prévio em
    `?ref=código` (reaproveita uma atribuição em aberto do mesmo usuário/parceiro, se
    houver, em vez de acumular atribuições redundantes)."""
    existing = db.execute(select(AffiliateAttribution).where(
        AffiliateAttribution.user_id == user_id, AffiliateAttribution.affiliate_id == affiliate_id,
        AffiliateAttribution.converted_at.is_(None),
    ).order_by(AffiliateAttribution.attributed_at.desc())).scalars().first()
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    days = _attribution_window_days(db)
    attr = AffiliateAttribution(
        affiliate_id=affiliate_id, user_id=user_id, anon_id=None,
        attributed_at=now, expires_at=now + timedelta(days=days),
    )
    db.add(attr)
    db.flush()
    return attr


def validate_demo_cpf(db: Session, cpf: str) -> Affiliate | None:
    """Allowlist da conta demo compartilhada — só parceiros ativos com acesso não
    revogado pelo admin (ver DemoAccessLog / auth/service.py::login_demo)."""
    digits = "".join(ch for ch in cpf if ch.isdigit())
    if digits == _ADMIN_ALWAYS_ON_CPF:
        return _get_or_create_admin_bypass_affiliate(db)
    return db.execute(select(Affiliate).where(
        Affiliate.cpf == digits, Affiliate.status == "active", Affiliate.demo_access_enabled.is_(True),
    )).scalar_one_or_none()


def _get_or_create_admin_bypass_affiliate(db: Session) -> Affiliate:
    """Registro (só para fins de log/rastreio em DemoAccessLog) do acesso sempre-ligado do
    administrador — criado sob demanda no primeiro login-demo dele."""
    affiliate = db.execute(select(Affiliate).where(Affiliate.cpf == _ADMIN_ALWAYS_ON_CPF)).scalar_one_or_none()
    if affiliate is not None:
        return affiliate
    affiliate = Affiliate(
        name="Admin (acesso sempre liberado)", code=_generate_affiliate_code(db, "admin"),
        status="active", cpf=_ADMIN_ALWAYS_ON_CPF, demo_access_enabled=True,
        contact_email="valerioeducfin@gmail.com",
    )
    db.add(affiliate)
    db.flush()
    return affiliate


def compute_portal_stats(db: Session, affiliate: Affiliate) -> dict:
    """Métricas agregadas do parceiro — reaproveitado pelo portal (`affiliates/router.py`)
    e pela página de detalhe do admin (`admin/service.py::get_affiliate_detail`)."""
    from app.domains.payments.models import PaymentOrder

    clicks = db.execute(select(func.count(AffiliateAttribution.id)).where(
        AffiliateAttribution.affiliate_id == affiliate.id)).scalar_one()
    signups = db.execute(select(func.count(func.distinct(AffiliateAttribution.user_id))).where(
        AffiliateAttribution.affiliate_id == affiliate.id, AffiliateAttribution.user_id.is_not(None),
    )).scalar_one()
    # buyers/revenue = desempenho de VENDAS DIRETAS do parceiro (exclui override recebido de
    # indicados); due/paid = total que o sistema deve a ele (inclui direta + override).
    buyers = db.execute(select(func.count(AffiliateCommission.id)).where(
        AffiliateCommission.affiliate_id == affiliate.id,
        AffiliateCommission.kind == CommissionKind.direct)).scalar_one()
    revenue = db.execute(
        select(func.coalesce(func.sum(PaymentOrder.amount_brl), 0))
        .join(AffiliateCommission, AffiliateCommission.order_id == PaymentOrder.id)
        .where(AffiliateCommission.affiliate_id == affiliate.id,
               AffiliateCommission.kind == CommissionKind.direct)
    ).scalar_one()
    due = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == affiliate.id, AffiliateCommission.status == "devida")).scalar_one()
    paid = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
        AffiliateCommission.affiliate_id == affiliate.id, AffiliateCommission.status == "paga")).scalar_one()

    return {
        "code": affiliate.code, "link": f"{settings.frontend_base_url}/?ref={affiliate.code}",
        "clicks": clicks, "signups": signups, "buyers": buyers,
        "revenue_brl": str(revenue), "commission_due_brl": str(due), "commission_paid_brl": str(paid),
    }


# --- Cupom promocional: solicitação pelo parceiro (aprovação/rejeição no admin) ---

def _coupon_request_item(db: Session, req) -> dict:
    from app.domains.promotions.models import Coupon
    coupon_code = None
    if req.coupon_id:
        c = db.get(Coupon, req.coupon_id)
        coupon_code = c.code if c else None
    return {
        "id": str(req.id), "requested_code": req.requested_code, "discount_pct": req.discount_pct,
        "status": req.status.value, "limit_type": req.limit_type.value if req.limit_type else None,
        "limit_days": req.limit_days, "limit_revenue_brl": req.limit_revenue_brl,
        "rejection_reason": req.rejection_reason, "coupon_code": coupon_code,
        "created_at": req.created_at, "decided_at": req.decided_at,
    }


def create_coupon_request(db: Session, affiliate: Affiliate, requested_code: str, discount_pct: int) -> dict:
    """Parceiro solicita um cupom promocional. Só um `pending` por vez; o código não pode
    colidir com cupom/afiliado já existente. Fica aguardando análise do admin."""
    from app.domains.promotions.models import PartnerCouponRequest
    from app.domains.enums import CouponRequestStatus

    if affiliate.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Apenas parceiros ativos podem solicitar cupons.")
    pending = db.execute(select(PartnerCouponRequest).where(
        PartnerCouponRequest.affiliate_id == affiliate.id,
        PartnerCouponRequest.status == CouponRequestStatus.pending,
    )).scalar_one_or_none()
    if pending is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Você já tem uma solicitação de cupom aguardando análise.")
    if code_in_use(db, requested_code):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Esse código já está em uso. Escolha outro nome.")
    req = PartnerCouponRequest(
        affiliate_id=affiliate.id, requested_code=requested_code, discount_pct=Decimal(discount_pct),
        status=CouponRequestStatus.pending,
    )
    db.add(req)
    db.flush()
    return _coupon_request_item(db, req)


def list_coupon_requests_for_partner(db: Session, affiliate: Affiliate) -> list[dict]:
    from app.domains.promotions.models import PartnerCouponRequest
    rows = db.execute(select(PartnerCouponRequest).where(
        PartnerCouponRequest.affiliate_id == affiliate.id,
    ).order_by(PartnerCouponRequest.created_at.desc())).scalars().all()
    return [_coupon_request_item(db, r) for r in rows]


# --- Indicação de parceiros: estatísticas dos parceiros indicados por este parceiro ---

def referred_partners_stats(db: Session, affiliate: Affiliate) -> dict:
    """Para cada parceiro indicado por `affiliate` (parent), retorna nº de usuários atrelados,
    cliques, faturamento gerado e quanto o sistema deve ao indicador (override) por ele."""
    children = db.execute(select(Affiliate).where(
        Affiliate.parent_affiliate_id == affiliate.id).order_by(Affiliate.created_at.desc())).scalars().all()
    items, total_override = [], Decimal("0")
    for child in children:
        s = compute_portal_stats(db, child)  # vendas DIRETAS do indicado
        override_due = db.execute(select(func.coalesce(func.sum(AffiliateCommission.amount_brl), 0)).where(
            AffiliateCommission.affiliate_id == affiliate.id,
            AffiliateCommission.source_affiliate_id == child.id,
            AffiliateCommission.kind == CommissionKind.override,
        )).scalar_one()
        total_override += Decimal(override_due)
        items.append({
            "id": str(child.id), "name": child.name, "code": child.code, "status": child.status,
            "clicks": s["clicks"], "users_count": s["buyers"], "revenue_brl": s["revenue_brl"],
            "override_due_brl": str(override_due),
        })
    return {
        "override_pct": _partner_override_pct(db),
        "total_override_due_brl": str(total_override), "items": items,
    }


def referred_users_stats(db: Session, affiliate: Affiliate) -> dict:
    """Retorna os usuários finais que utilizaram o link deste parceiro, com nome e valor gasto em compras."""
    from app.domains.users.models import User
    from app.domains.payments.models import PaymentOrder, PaymentStatus

    # Usuários atrelados ao afiliado via AffiliateAttribution
    rows = db.execute(
        select(User, func.coalesce(func.sum(PaymentOrder.amount_brl), 0).label("spent"))
        .join(AffiliateAttribution, AffiliateAttribution.user_id == User.id)
        .outerjoin(PaymentOrder, (PaymentOrder.user_id == User.id) & (PaymentOrder.status == PaymentStatus.paid))
        .where(AffiliateAttribution.affiliate_id == affiliate.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    ).all()

    items = []
    for user, spent in rows:
        items.append({
            "id": str(user.id),
            "name": user.full_name or user.email.split("@")[0],
            "email": user.email,
            "spent_brl": str(spent),
            "created_at": user.created_at.isoformat() if user.created_at else "",
        })

    return {
        "total_users": len(items),
        "items": items,
    }


def primary_invite_coupon_code(db: Session, ref_code: str | None) -> str | None:
    """Resolve o cupom de convite a pré-preencher no checkout a partir do ?ref=. Aceita tanto
    o código-base do parceiro quanto o código de um cupom dele; devolve None se não achar."""
    from app.domains.promotions.models import Coupon
    code = (ref_code or "").strip().upper()
    if not code:
        return None
    # ref já é um código de cupom ativo?
    direct = db.execute(select(Coupon).where(Coupon.code == code, Coupon.active.is_(True))).scalar_one_or_none()
    if direct is not None:
        return direct.code
    # senão, resolve o parceiro pelo código-base e pega o cupom de convite de menor desconto.
    aff = db.execute(select(Affiliate).where(
        Affiliate.code == code, Affiliate.status == "active")).scalar_one_or_none()
    if aff is None:
        return None
    coupon = db.execute(select(Coupon).where(
        Coupon.affiliate_id == aff.id, Coupon.active.is_(True), Coupon.first_purchase_only.is_(True),
    ).order_by(Coupon.discount_value.asc())).scalars().first()
    return coupon.code if coupon else None
