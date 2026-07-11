from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.notifications.models import Notification


def notify(db: Session, user_id: uuid.UUID, type: str, title: str, body: str | None = None) -> None:
    try:
        db.add(Notification(user_id=user_id, type=type, title=title, body=body))
    except Exception as e:
        print(f"[AVISO] notifications.notify({type}): {e}")


def list_for_user(db: Session, user_id: uuid.UUID, limit: int = 30) -> list[Notification]:
    return db.execute(select(Notification).where(Notification.user_id == user_id)
                      .order_by(Notification.created_at.desc()).limit(limit)).scalars().all()


def mark_read(db: Session, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    from datetime import datetime, timezone
    n = db.get(Notification, notification_id)
    if n is not None and n.user_id == user_id and n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
