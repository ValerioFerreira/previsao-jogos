"""Schemas da 'Aposta Escolhida'."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarketOption(BaseModel):
    market_key: str
    group: str
    label: str
    selection: str
    odd: float


class MarketsResponse(BaseModel):
    analysis_id: str
    home_team: str
    away_team: str
    max_combined_odd: float
    options: list[MarketOption]


class PreviewRequest(BaseModel):
    market_keys: list[str] = Field(default_factory=list)


class SelectionOut(BaseModel):
    market_key: str
    label: str
    selection: str
    odd: float


class PreviewResponse(BaseModel):
    selections: list[SelectionOut]
    combined_odd: float
    valid: bool
    exceeds_cap: bool
    auto: bool
    max_combined_odd: float


class CreateBetRequest(BaseModel):
    # se vazio, o sistema AUTO-SELECIONA uma aposta com odd próxima de 2,00
    market_keys: list[str] = Field(default_factory=list)


class BetResponse(BaseModel):
    id: str
    analysis_id: str
    status: str
    combined_odd: Decimal
    auto_selected: bool
    fixture_id: int | None
    match_datetime: datetime | None
    created_at: datetime
    selections: list[SelectionOut]


class BetsPage(BaseModel):
    items: list[BetResponse]
    total: int
    limit: int
    offset: int
