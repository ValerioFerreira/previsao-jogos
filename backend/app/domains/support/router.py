from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.domains.auth.deps import get_current_user, get_db
from app.domains.support import schemas, service
from app.domains.users.models import User

router = APIRouter(prefix="/support", tags=["support"])


def _out(t) -> schemas.TicketItem:
    return schemas.TicketItem(id=str(t.id), category=t.category, subject=t.subject, message=t.message,
                              status=t.status, order_id=str(t.order_id) if t.order_id else None,
                              admin_notes=t.admin_notes, created_at=t.created_at, resolved_at=t.resolved_at)


@router.post("/tickets", response_model=schemas.TicketItem, status_code=201)
def create_ticket(data: schemas.TicketRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = service.create_ticket(db, user.id, data)
    db.commit()
    return _out(t)


@router.get("/tickets", response_model=list[schemas.TicketItem])
def my_tickets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_out(t) for t in service.list_for_user(db, user.id)]
