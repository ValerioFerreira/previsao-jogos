"""Dependências de autenticação/autorização para os routers."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.db.base import get_session
from app.domains.enums import UserRole, UserStatus
from app.domains.users.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Session:  # type: ignore[misc]
    yield from get_session()


def client_ip(request: Request) -> str | None:
    """IP real considerando proxy (Render/Vercel) via X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    try:
        payload = security.decode_access_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.")
    if payload.get("type") != "access" or payload.get("scope"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido para esta operação.")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status != UserStatus.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.admin, UserRole.superadmin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Acesso restrito.")
    return user
