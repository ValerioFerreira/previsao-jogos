"""Registro e listagem de incidentes de anti-compartilhamento (sem punição automática —
o admin revisa manualmente em /admin/security/incidents e decide as penalidades)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.security import schemas
from app.domains.security.models import ScreenshotIncident
from app.domains.users.models import User


def log_incident(
    db: Session, user_id: uuid.UUID, data: schemas.IncidentCreate, ip: str | None, user_agent: str | None
) -> ScreenshotIncident:
    if data.incident_type not in schemas.INCIDENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de incidente inválido.")
    incident = ScreenshotIncident(
        user_id=user_id, incident_type=data.incident_type, page=data.page,
        context=data.context, ip=ip, user_agent=(user_agent or "")[:400],
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def recent_count(db: Session, user_id: uuid.UUID, hours: int = 24) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return db.execute(
        select(func.count()).select_from(ScreenshotIncident)
        .where(ScreenshotIncident.user_id == user_id, ScreenshotIncident.created_at >= since)
    ).scalar_one()


def list_incidents(db: Session, user_id: uuid.UUID | None, limit: int, offset: int) -> schemas.IncidentsPage:
    base = select(ScreenshotIncident, User.email).join(User, User.id == ScreenshotIncident.user_id)
    if user_id:
        base = base.where(ScreenshotIncident.user_id == user_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(ScreenshotIncident.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        schemas.IncidentOut(
            id=str(inc.id), user_id=str(inc.user_id), user_email=email,
            incident_type=inc.incident_type, page=inc.page, context=inc.context,
            ip=inc.ip, created_at=inc.created_at,
        )
        for inc, email in rows
    ]
    return schemas.IncidentsPage(items=items, total=total)
