"""Regras de negócio de autenticação. Toda operação sensível gera AuthEvent (auditoria).
Fluxo: cadastro -> OTP por e-mail -> verificação -> criação de senha -> ativação.
"""
from __future__ import annotations

import logging
import secrets
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.email import EmailSendError, send_otp_email
from app.domains.analytics import service as analytics_service
from app.domains.auth import schemas
from app.domains.enums import AuthEventType, CreditTxType, OtpPurpose, UserRole, UserStatus
from app.domains.users.models import AuthEvent, AuthSession, OtpCode, User
from app.domains.wallet.service import get_or_create_wallet, post_transaction

logger = logging.getLogger("app.auth")

_SETUP_SCOPE = "pw_setup"
_PARTNER_INVITE_SCOPE = "partner_invite"

# Bônus de boas-vindas. A partir de 2026-07-21 toda conta nova nasce com 0 crédito: o
# usuário passa a contar com o CRÉDITO DIÁRIO PROMOCIONAL (1/dia, cota FreeDailyUse) e com
# eventuais créditos de um código promocional de indicação (ver _grant_referral_bonus_if_pending).
# O bloco de concessão é guardado por `if WELCOME_CREDITS > 0`, então isto vira no-op.
WELCOME_CREDITS = Decimal("0")

# Config default do bônus de indicação, sobrescrita pelo PlatformSetting "referral_bonus"
# (chave configurável pelo painel admin — nenhum valor de negócio fica só hardcoded aqui).
_DEFAULT_REFERRAL_BONUS = {"referrer_credits": 5, "referred_credits": 5}

# Sem caracteres ambíguos (0/O, 1/I) pra ficar fácil de digitar/ler o código de indicação.
_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _referral_bonus_config(db: Session) -> dict:
    from app.domains.admin.models import PlatformSetting
    row = db.execute(select(PlatformSetting).where(PlatformSetting.key == "referral_bonus")).scalar_one_or_none()
    return {**_DEFAULT_REFERRAL_BONUS, **(row.value or {})} if row else dict(_DEFAULT_REFERRAL_BONUS)


def _generate_referral_code(db: Session, full_name: str) -> str:
    """Código curto e amigável, mas único por natureza (não sequencial a partir do nome:
    prefixo do primeiro nome + sufixo aleatório) — ex. VALERIO8F2, JOAOA31."""
    first_name = (full_name.split() or ["USER"])[0]
    ascii_name = unicodedata.normalize("NFKD", first_name).encode("ascii", "ignore").decode("ascii")
    prefix = "".join(ch for ch in ascii_name.upper() if ch.isalnum())[:6] or "USER"
    for _ in range(20):  # cinto-e-suspensório: colisão é praticamente impossível com o sufixo aleatório
        suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(3))
        code = f"{prefix}{suffix}"
        if db.execute(select(User.id).where(User.referral_code == code)).scalar_one_or_none() is None:
            return code
    raise RuntimeError("Não foi possível gerar um código de indicação único.")


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(db: Session, event: AuthEventType, user_id=None, ip=None, ua=None, meta=None) -> None:
    db.add(AuthEvent(user_id=user_id, event=event, ip=ip, user_agent=ua, meta=meta))


def _public(user: User) -> schemas.UserPublic:
    return schemas.UserPublic(
        id=str(user.id), full_name=user.full_name, email=user.email, cpf=user.cpf,
        phone=user.phone, status=user.status.value, role=user.role.value,
        referral_code=user.referral_code, is_demo=user.is_demo,
    )


def get_referral_info(db: Session, user: User) -> schemas.ReferralInfo:
    from app.domains.promotions.models import Referral

    completed = db.execute(select(Referral).where(
        Referral.referrer_user_id == user.id, Referral.status == "completed")).scalars().all()
    cfg = _referral_bonus_config(db)
    earned = Decimal(str(cfg.get("referrer_credits", 5))) * len(completed)
    return schemas.ReferralInfo(
        referral_code=user.referral_code,
        share_link=f"{settings.frontend_base_url}/convite/{user.referral_code}" if user.referral_code else None,
        completed_referrals=len(completed), credits_earned=str(earned),
    )


# --------------------------------------------------------------------- OTP
def _create_and_send_otp(db: Session, user: User, purpose: OtpPurpose, ip: str | None) -> None:
    # cooldown de reenvio: último OTP do mesmo propósito
    last = db.execute(
        select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.purpose == purpose)
        .order_by(OtpCode.created_at.desc())
    ).scalars().first()
    if last is not None and _utc(last.created_at):
        elapsed = (_now() - _utc(last.created_at)).total_seconds()
        if elapsed < settings.otp_resend_cooldown_sec:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                detail=f"Aguarde {int(settings.otp_resend_cooldown_sec - elapsed)}s para reenviar.")
    code = security.generate_otp()
    db.add(OtpCode(
        user_id=user.id, purpose=purpose, code_hash=security.hash_otp(code),
        expires_at=security.otp_expiry(), max_attempts=settings.otp_max_attempts, created_ip=ip,
    ))
    _log(db, AuthEventType.otp_sent, user.id, ip, meta={"purpose": purpose.value})
    try:
        send_otp_email(user.email, code, purpose.value)
    except EmailSendError as e:
        # Levanta ANTES do db.commit() do chamador: a sessão fecha sem persistir o OtpCode,
        # então o usuário não fica preso no cooldown de reenvio por um código que nunca chegou.
        # HTTPException (e não exceção crua) porque um 500 não carrega header CORS e o browser
        # mascara o erro real como falha de CORS.
        logger.error("Falha ao enviar OTP (%s) para user=%s: %s", purpose.value, user.id, e)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Não foi possível enviar o e-mail de verificação. Tente novamente em instantes.",
        ) from e


def _consume_otp(db: Session, user: User, purpose: OtpPurpose, code: str, ip: str | None) -> None:
    otp = db.execute(
        select(OtpCode).where(
            OtpCode.user_id == user.id, OtpCode.purpose == purpose, OtpCode.consumed_at.is_(None)
        ).order_by(OtpCode.created_at.desc())
    ).scalars().first()
    if otp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código não encontrado. Solicite um novo.")
    if _utc(otp.expires_at) < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código expirado. Solicite um novo.")
    if otp.attempts >= otp.max_attempts:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Tentativas esgotadas. Solicite um novo código.")
    if not security.verify_otp(code, otp.code_hash):
        otp.attempts += 1
        _log(db, AuthEventType.otp_failed, user.id, ip, meta={"purpose": purpose.value})
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Código incorreto.")
    otp.consumed_at = _now()
    _log(db, AuthEventType.otp_verified, user.id, ip, meta={"purpose": purpose.value})


# --------------------------------------------------------------------- cadastro
def register(db: Session, data: schemas.RegisterRequest, ip: str | None, ua: str | None = None) -> None:
    email = data.email.lower()
    # unicidade: e-mail / CPF / telefone não podem colidir com conta já existente
    existing_email = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    dup = db.execute(
        select(User).where((User.cpf == data.cpf) | (User.phone == data.phone))
    ).scalars().all()
    for u in dup:
        if u.status == UserStatus.active:
            campo = "CPF" if u.cpf == data.cpf else "telefone"
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"{campo} já cadastrado.")

    if existing_email is not None:
        if existing_email.status == UserStatus.active:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="E-mail já cadastrado.")
        # conta pendente: reaproveita e reenvia OTP (atualiza dados básicos)
        user = existing_email
        user.full_name, user.cpf, user.phone = data.full_name, data.cpf, data.phone
    else:
        user = User(
            full_name=data.full_name, email=email, cpf=data.cpf, phone=data.phone,
            status=UserStatus.pending_verification, role=UserRole.user, signup_ip=ip,
        )
        db.add(user)
        db.flush()
        _log(db, AuthEventType.register, user.id, ip)
        analytics_service.track(db, "signup", user_id=user.id)

        if data.referral_code:
            _create_pending_referral(db, user, data.referral_code, data.referral_source, ip, ua)

    _create_and_send_otp(db, user, OtpPurpose.email_verify, ip)
    db.commit()


def _create_pending_referral(db: Session, new_user: User, code: str, source: str | None,
                             ip: str | None, ua: str | None) -> None:
    """Indicação entre usuários — independente do programa de afiliados (?ref=). Só cria a
    linha 'pending'; os créditos são concedidos na ativação (set_password), junto do bônus
    de boas-vindas, para não conceder nada a uma conta que nunca chega a existir de fato."""
    from app.domains.promotions.models import Referral

    referrer = db.execute(select(User).where(User.referral_code == code.strip().upper())).scalar_one_or_none()
    if referrer is None or referrer.id == new_user.id:
        return
    db.add(Referral(
        referrer_user_id=referrer.id, referred_user_id=new_user.id, status="pending",
        reward_config=_referral_bonus_config(db), signup_ip=ip, user_agent=ua,
        signup_source=source or "manual",
    ))


def _grant_referral_bonus_if_pending(db: Session, user: User) -> None:
    """Concede os créditos dos dois lados na ativação da conta indicada — idempotente por
    `idempotency_key` única por referral.id (post_transaction), então mesmo se set_password
    for reprocessado o bônus nunca duplica."""
    from app.domains.promotions.models import Referral

    referral = db.execute(select(Referral).where(
        Referral.referred_user_id == user.id, Referral.status == "pending",
    )).scalar_one_or_none()
    if referral is None:
        return
    referrer = db.get(User, referral.referrer_user_id)
    if referrer is None:
        referral.status = "completed"
        referral.completed_at = _now()
        return

    cfg = referral.reward_config or _DEFAULT_REFERRAL_BONUS
    referred_credits = Decimal(str(cfg.get("referred_credits", 5)))
    referrer_credits = Decimal(str(cfg.get("referrer_credits", 5)))

    if referred_credits > 0:
        wallet = get_or_create_wallet(db, user.id)
        post_transaction(
            db, wallet=wallet, tx_type=CreditTxType.bonus, amount=referred_credits,
            idempotency_key=f"referral-bonus:{referral.id}",
            reference_type="referral", reference_id=referral.id,
            description=f"Indicação concluída — indicado por {referrer.full_name}",
        )
    if referrer_credits > 0:
        referrer_wallet = get_or_create_wallet(db, referrer.id)
        post_transaction(
            db, wallet=referrer_wallet, tx_type=CreditTxType.bonus, amount=referrer_credits,
            idempotency_key=f"referral-bonus-referrer:{referral.id}",
            reference_type="referral", reference_id=referral.id,
            description=f"Indicação concluída — amigo indicado: {user.full_name}",
        )
    referral.status = "completed"
    referral.completed_at = _now()


def resend_otp(db: Session, email: str, purpose_str: str, ip: str | None) -> None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None:
        return  # não revela existência
    purpose = OtpPurpose.email_verify if purpose_str == "email_verify" else OtpPurpose.password_reset
    _create_and_send_otp(db, user, purpose, ip)
    db.commit()


def verify_email(db: Session, email: str, code: str, ip: str | None) -> str:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or user.status == UserStatus.blocked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Não foi possível verificar.")
    _consume_otp(db, user, OtpPurpose.email_verify, code, ip)
    user.email_verified_at = _now()
    db.commit()
    # token curto que autoriza APENAS a criação de senha
    return security.create_access_token(str(user.id), extra={"scope": _SETUP_SCOPE})


def set_password(db: Session, setup_token: str, password: str, ip: str | None) -> schemas.TokenResponse:
    try:
        payload = security.decode_access_token(setup_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    scope = payload.get("scope")
    if scope not in (_SETUP_SCOPE, _PARTNER_INVITE_SCOPE):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido para esta operação.")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Não foi possível ativar a conta.")
    if scope == _SETUP_SCOPE and user.email_verified_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="E-mail não verificado.")

    user.password_hash = security.hash_password(password)
    user.status = UserStatus.active

    if scope == _SETUP_SCOPE:
        wallet = get_or_create_wallet(db, user.id)   # carteira criada na ativação
        # Bônus de boas-vindas (8 créditos grátis) — idempotente por conta.
        if WELCOME_CREDITS > 0:
            post_transaction(
                db, wallet=wallet, tx_type=CreditTxType.bonus, amount=WELCOME_CREDITS,
                idempotency_key=f"welcome-bonus:{user.id}",
                description="Bônus de boas-vindas (créditos grátis)",
            )
        if user.referral_code is None:
            user.referral_code = _generate_referral_code(db, user.full_name)
        _grant_referral_bonus_if_pending(db, user)
    # scope partner_invite: só ativa a conta e define a senha — o parceiro não passa
    # pelo cadastro comum (sem OTP/bônus de boas-vindas/indicação).

    _log(db, AuthEventType.password_set, user.id, ip)
    tokens = _issue_tokens(db, user, ip, None)
    db.commit()
    return tokens


# --------------------------------------------------------------------- login / tokens
def _issue_tokens(db: Session, user: User, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    access = security.create_access_token(str(user.id), extra={"role": user.role.value})
    refresh = security.generate_refresh_token()
    db.add(AuthSession(
        user_id=user.id, refresh_token_hash=security.hash_token(refresh),
        user_agent=ua, ip=ip, expires_at=security.refresh_expiry(),
    ))
    return schemas.TokenResponse(
        access_token=access, refresh_token=refresh,
        expires_in=settings.access_token_ttl_min * 60, user=_public(user),
    )


def login(db: Session, email: str, password: str, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos.")
    if user is None or user.password_hash is None:
        raise generic
    if user.status == UserStatus.blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Conta bloqueada.")
    if user.locked_until and _utc(user.locked_until) > _now():
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Conta temporariamente bloqueada por tentativas. Tente mais tarde.")
    if user.status != UserStatus.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Conta não ativada.")

    if user.role == UserRole.partner:
        from app.domains.affiliates.models import Affiliate
        affiliate = db.execute(select(Affiliate).where(Affiliate.user_id == user.id)).scalar_one_or_none()
        if affiliate and affiliate.status != "active":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Sua conta de Parceiro está desativada. Caso isso tenha sido um erro, envie uma mensagem para contato@safercode.com.br para analisarmos seu caso."
            )

    if not security.verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_attempts:
            user.locked_until = _now() + timedelta(minutes=settings.login_lockout_min)
            user.failed_login_count = 0
            _log(db, AuthEventType.account_locked, user.id, ip)
        _log(db, AuthEventType.login_failed, user.id, ip, ua)
        db.commit()
        raise generic

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    user.last_login_ip = ip
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    _log(db, AuthEventType.login_success, user.id, ip, ua)
    analytics_service.track(db, "login", user_id=user.id)
    tokens = _issue_tokens(db, user, ip, ua)
    db.commit()
    return tokens


def enter_demo_as_partner(db: Session, user: User, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    """Atalho pro parceiro JÁ logado na própria conta (role=partner) entrar direto na conta
    demo compartilhada, sem digitar de novo e-mail/senha/CPF — a identidade já veio do
    login normal, então só localizamos o Affiliate dele e emitimos tokens da conta demo
    (mesma auditoria de acesso do login-demo manual, ver `login_demo` abaixo)."""
    from app.domains.affiliates import service as affiliates_service
    from app.domains.affiliates.models import Affiliate, DemoAccessLog

    affiliate = db.execute(select(Affiliate).where(Affiliate.user_id == user.id)).scalar_one_or_none()
    if affiliate is None or affiliate.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Sua conta não tem acesso à conta demo.")
    if not affiliate.demo_access_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Seu acesso à conta demo foi revogado.")

    demo_user = db.execute(select(User).where(User.is_demo.is_(True))).scalars().first()
    if demo_user is None or demo_user.status != UserStatus.active:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Conta demo não está disponível no momento.")

    _log(db, AuthEventType.login_success, demo_user.id, ip, ua, meta={"via": "partner_enter_demo", "partner_user_id": str(user.id)})
    tokens = _issue_tokens(db, demo_user, ip, ua)
    db.add(DemoAccessLog(affiliate_id=affiliate.id, cpf_used=affiliate.cpf, ip=ip))
    db.commit()
    return tokens


def login_demo(db: Session, email: str, password: str, cpf: str, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    """Conta demo compartilhada — só autentica se o CPF informado estiver na allowlist de
    um parceiro ativo (`Affiliate.demo_access_enabled`), além do e-mail+senha da conta
    demo em si. Reaproveita `login()` inteiro para não duplicar sessão/lockout/auditoria."""
    from app.domains.affiliates import service as affiliates_service
    from app.domains.affiliates.models import DemoAccessLog

    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Acesso inválido.")
    affiliate = affiliates_service.validate_demo_cpf(db, cpf)
    if affiliate is None:
        raise generic
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or not user.is_demo:
        raise generic

    tokens = login(db, email, password, ip, ua)
    db.add(DemoAccessLog(affiliate_id=affiliate.id, cpf_used=affiliate.cpf, ip=ip))
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    th = security.hash_token(refresh_token)
    sess = db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == th)).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None or _utc(sess.expires_at) < _now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida ou expirada.")
    user = db.get(User, sess.user_id)
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sessão inválida.")
    sess.revoked_at = _now()   # rotação: revoga o antigo e emite um novo
    _log(db, AuthEventType.token_refreshed, user.id, ip, ua)
    tokens = _issue_tokens(db, user, ip, ua)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str, ip: str | None) -> None:
    th = security.hash_token(refresh_token)
    sess = db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == th)).scalar_one_or_none()
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = _now()
        _log(db, AuthEventType.logout, sess.user_id, ip)
        db.commit()


# --------------------------------------------------------------------- recuperação de senha
def forgot_password(db: Session, email: str, ip: str | None) -> None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is not None and user.status == UserStatus.active:
        _create_and_send_otp(db, user, OtpPurpose.password_reset, ip)
        db.commit()
    # resposta sempre genérica (não revela cadastro)


def reset_password(db: Session, email: str, code: str, password: str, ip: str | None) -> None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Não foi possível redefinir.")
    _consume_otp(db, user, OtpPurpose.password_reset, code, ip)
    user.password_hash = security.hash_password(password)
    user.locked_until = None
    user.failed_login_count = 0
    # invalida todas as sessões ativas por segurança
    for s in db.execute(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))).scalars():
        s.revoked_at = _now()
    _log(db, AuthEventType.password_reset, user.id, ip)
    db.commit()


def dev_owner_login(db: Session, ip: str | None, ua: str | None) -> schemas.TokenResponse:
    """Dev/local auto-login helper for owner account."""
    from app.domains.enums import UserRole
    user = db.execute(select(User).where(User.email == "valerioeducfin@gmail.com")).scalar_one_or_none()
    if not user:
        user = db.execute(select(User).where(User.role == UserRole.owner)).scalars().first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Usuário owner não encontrado.")
    user.last_login_at = _now()
    user.last_login_ip = ip
    tokens = _issue_tokens(db, user, ip, ua)
    db.commit()
    return tokens
