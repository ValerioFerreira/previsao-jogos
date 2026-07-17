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
from app.domains.enums import PartnerPaymentType

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


def suggest_code_prefix(db: Session, full_name: str, discount_pct: Decimal | int) -> str:
    """Sugestão de PREFIXO (sem o sufixo do desconto): primeiro nome; se colidir (prefixo +
    desconto já em uso), soma letra a letra do(s) sobrenome(s) até desempatar — ex.
    VALERIO15 -> VALERIOF15 -> VALERIOFE15... Esgotados os sobrenomes, cai num contador."""
    discount_str = str(int(discount_pct))
    parts = [_ascii_upper_alnum(p) for p in full_name.split() if _ascii_upper_alnum(p)]
    if not parts:
        parts = ["PARCEIRO"]

    def taken(prefix: str) -> bool:
        return code_in_use(db, f"{prefix}{discount_str}")

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


def resolve_partner_code(db: Session, full_name: str, discount_pct: Decimal | int,
                         requested_prefix: str | None) -> str:
    """O sufixo numérico (desconto) é SEMPRE anexado pelo servidor — o parceiro só edita o
    prefixo de texto, nunca o número (regra do pedido: o desconto não pode ser mudado
    editando o código)."""
    discount_str = str(int(discount_pct))
    if requested_prefix and requested_prefix.strip():
        prefix = _ascii_upper_alnum(requested_prefix)[:20]
        if not prefix:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código inválido.")
        code = f"{prefix}{discount_str}"
        if code_in_use(db, code):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Esse código já está em uso. Escolha outro.")
        return code
    return f"{suggest_code_prefix(db, full_name, discount_pct)}{discount_str}"


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
    code = resolve_partner_code(db, data.full_name, data.discount_pct, data.code_prefix)
    affiliate = Affiliate(
        name=data.full_name, code=code, status="pending",
        commission_pct=COMMISSION_BUDGET_PCT - data.discount_pct, discount_pct=data.discount_pct,
        payment_type=PartnerPaymentType(data.payment_type),
        cpf=data.cpf, contact_email=data.email.lower(), contact_phone=data.phone,
    )
    db.add(affiliate)
    db.flush()
    return affiliate


def track_click(db: Session, code: str, anon_id: str, user_id: uuid.UUID | None = None) -> AffiliateAttribution | None:
    affiliate = db.execute(select(Affiliate).where(
        func.upper(Affiliate.code) == code.strip().upper(), Affiliate.status == "active")).scalar_one_or_none()
    if affiliate is None:
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


def commission_for_order(db: Session, order) -> AffiliateCommission | None:
    """Chamado quando um PaymentOrder é confirmado — calcula e registra a comissão do
    afiliado (se houver atribuição válida dentro da janela), independentemente de o
    pedido ter usado cupom ou não."""
    existing = db.execute(select(AffiliateCommission).where(
        AffiliateCommission.order_id == order.id)).scalar_one_or_none()
    if existing is not None:
        return existing

    attr = _active_attribution_for_order(db, order.user_id, order.paid_at or datetime.now(timezone.utc))
    if attr is None:
        return None
    affiliate = db.get(Affiliate, attr.affiliate_id)
    if affiliate is None or affiliate.status != "active":
        return None

    amount = Decimal("0.00")
    if affiliate.commission_pct:
        amount += (Decimal(order.amount_brl) * Decimal(affiliate.commission_pct) / Decimal(100))
    if affiliate.commission_fixed_brl:
        amount += Decimal(affiliate.commission_fixed_brl)
    if amount <= 0:
        return None

    attr.converted_at = datetime.now(timezone.utc)
    order.affiliate_attribution_id = attr.id
    commission = AffiliateCommission(affiliate_id=affiliate.id, order_id=order.id,
                                     amount_brl=amount.quantize(Decimal("0.01")), status="devida")
    db.add(commission)
    return commission


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
    buyers = db.execute(select(func.count(AffiliateCommission.id)).where(
        AffiliateCommission.affiliate_id == affiliate.id)).scalar_one()
    revenue = db.execute(
        select(func.coalesce(func.sum(PaymentOrder.amount_brl), 0))
        .join(AffiliateCommission, AffiliateCommission.order_id == PaymentOrder.id)
        .where(AffiliateCommission.affiliate_id == affiliate.id)
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
