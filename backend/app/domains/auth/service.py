"""Regras de negócio de autenticação. Toda operação sensível gera AuthEvent (auditoria).
Fluxo: cadastro -> OTP por e-mail -> verificação -> criação de senha -> ativação.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.email import send_otp_email
from app.domains.auth import schemas
from app.domains.enums import AuthEventType, OtpPurpose, UserRole, UserStatus
from app.domains.users.models import AuthEvent, AuthSession, OtpCode, User
from app.domains.wallet.service import get_or_create_wallet

_SETUP_SCOPE = "pw_setup"


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
    send_otp_email(user.email, code, purpose.value)


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
def register(db: Session, data: schemas.RegisterRequest, ip: str | None) -> None:
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

    _create_and_send_otp(db, user, OtpPurpose.email_verify, ip)
    db.commit()


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
    if payload.get("scope") != _SETUP_SCOPE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido para esta operação.")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.email_verified_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="E-mail não verificado.")
    user.password_hash = security.hash_password(password)
    user.status = UserStatus.active
    get_or_create_wallet(db, user.id)   # carteira criada na ativação
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
    tokens = _issue_tokens(db, user, ip, ua)
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
