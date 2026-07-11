from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.notifications import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationItem])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = service.list_for_user(db, user.id)
    return [schemas.NotificationItem(id=str(n.id), type=n.type, title=n.title, body=n.body,
                                     read_at=n.read_at, created_at=n.created_at) for n in rows]


@router.post("/{notification_id}/read")
def read_notification(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.mark_read(db, user.id, uuid.UUID(notification_id))
    db.commit()
    return {"ok": True}
