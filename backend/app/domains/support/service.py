from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.support.models import SupportTicket

_CATEGORIES = {"refund", "payment_issue", "credit_question", "other"}


def create_ticket(db: Session, user_id: uuid.UUID, data) -> SupportTicket:
    if data.category not in _CATEGORIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Categoria inválida.")
    t = SupportTicket(
        user_id=user_id, category=data.category, subject=data.subject, message=data.message,
        order_id=uuid.UUID(data.order_id) if data.order_id else None,
    )
    db.add(t)
    db.flush()
    return t


def list_for_user(db: Session, user_id: uuid.UUID) -> list[SupportTicket]:
    return db.execute(select(SupportTicket).where(SupportTicket.user_id == user_id)
                      .order_by(SupportTicket.created_at.desc())).scalars().all()


def list_all(db: Session, status_filter: str | None = None) -> list[SupportTicket]:
    stmt = select(SupportTicket)
    if status_filter:
        stmt = stmt.where(SupportTicket.status == status_filter)
    return db.execute(stmt.order_by(SupportTicket.created_at.desc())).scalars().all()


def patch_ticket(db: Session, ticket_id: uuid.UUID, data) -> SupportTicket:
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket não encontrado.")
    if data.status is not None:
        t.status = data.status
        if data.status == "resolved":
            t.resolved_at = datetime.now(timezone.utc)
    if data.admin_notes is not None:
        t.admin_notes = data.admin_notes
    return t
