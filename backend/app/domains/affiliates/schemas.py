from __future__ import annotations

from pydantic import BaseModel


class TrackClickRequest(BaseModel):
    code: str
    anon_id: str


class AttachSignupRequest(BaseModel):
    anon_id: str


class PortalStats(BaseModel):
    code: str
    link: str
    clicks: int
    signups: int
    buyers: int
    revenue_brl: str
    commission_due_brl: str
    commission_paid_brl: str
