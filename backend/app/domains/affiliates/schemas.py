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


class AffiliateLoginRequest(BaseModel):
    email: str
    cpf: str


class AffiliateTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TimeseriesPoint(BaseModel):
    bucket: str  # "2026-07-16" (day) ou "2026-07" (month)
    clicks: int
    conversions: int
    revenue_brl: str
    commission_brl: str


class TimeseriesResponse(BaseModel):
    granularity: str
    items: list[TimeseriesPoint]
