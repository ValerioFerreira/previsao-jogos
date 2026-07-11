from __future__ import annotations

from pydantic import BaseModel


class TrackRequest(BaseModel):
    event_type: str
    session_id: str | None = None
    metadata: dict | None = None
