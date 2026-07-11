from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

INCIDENT_TYPES = {"printscreen", "copy_blocked", "context_menu_blocked", "print_blocked", "devtools_suspected"}


class IncidentCreate(BaseModel):
    incident_type: str = Field(..., max_length=40)
    page: str | None = Field(None, max_length=200)
    context: dict | None = None


class IncidentAck(BaseModel):
    detail: str
    incident_count_24h: int


class IncidentOut(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    incident_type: str
    page: str | None
    context: dict | None
    ip: str | None
    created_at: datetime


class IncidentsPage(BaseModel):
    items: list[IncidentOut]
    total: int
