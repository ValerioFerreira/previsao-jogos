"""Primitivas de segurança: hash de senha (argon2), JWT de acesso, tokens opacos de
refresh (guardados só como hash) e geração/hash de OTP. Sem estado — só funções puras."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()


# --------------------------------------------------------------------- senha
def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:
        return False


# --------------------------------------------------------------------- JWT de acesso
def create_access_token(subject: str, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_min)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Levanta jwt.PyJWTError se inválido/expirado."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# --------------------------------------------------------------------- refresh (opaco)
def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Hash determinístico (HMAC-SHA256) — permite lookup por igualdade sem guardar o token."""
    return hmac.new(settings.jwt_secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)


# --------------------------------------------------------------------- OTP
def generate_otp(length: int | None = None) -> str:
    n = length or settings.otp_length
    return "".join(secrets.choice("0123456789") for _ in range(n))


def hash_otp(code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), ("otp:" + code).encode(), hashlib.sha256).hexdigest()


def verify_otp(code: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_otp(code), hashed)


def otp_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.otp_ttl_min)
