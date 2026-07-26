"""Rotas de anti-compartilhamento: usuário autenticado reporta incidentes (captura de
tela, cópia, impressão); admin revisa a lista para decidir penalidades manualmente."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.domains.auth.deps import client_ip, get_current_user, get_db, require_owner
from app.domains.security import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/security", tags=["security"])


@router.post("/incident", response_model=schemas.IncidentAck)
def report_incident(
    data: schemas.IncidentCreate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    rate_limit.hit(f"security-incident:{user.id}", max_events=20, window_sec=60)
    service.log_incident(db, user.id, data, client_ip(request), request.headers.get("user-agent"))
    count = service.recent_count(db, user.id, hours=24)
    return schemas.IncidentAck(detail="Incidente registrado.", incident_count_24h=count)


@router.get("/incidents", response_model=schemas.IncidentsPage)
def list_incidents(
    user_id: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _: User = Depends(require_owner), db: Session = Depends(get_db),
):
    uid = uuid.UUID(user_id) if user_id else None
    return service.list_incidents(db, uid, limit, offset)
