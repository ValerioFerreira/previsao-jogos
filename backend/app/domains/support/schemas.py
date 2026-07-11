from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TicketRequest(BaseModel):
    category: str
    subject: str
    message: str
    order_id: str | None = None


class TicketItem(BaseModel):
    id: str
    category: str
    subject: str
    message: str
    status: str
    order_id: str | None
    admin_notes: str | None = None
    created_at: datetime
    resolved_at: datetime | None


class TicketPatch(BaseModel):
    status: str | None = None
    admin_notes: str | None = None
