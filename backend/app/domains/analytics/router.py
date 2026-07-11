"""Rotas de analytics: track (client-side) + dashboard executivo (admin)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.analytics import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/track", status_code=201)
def track_event(data: schemas.TrackRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.track(db, data.event_type, user_id=user.id, session_id=data.session_id, **(data.metadata or {}))
    db.commit()
    return {"ok": True}
