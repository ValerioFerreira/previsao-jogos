"""Schemas da Análise (previsão) — geração, snapshot imutável e histórico."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    home_team: str
    away_team: str
    tournament: str = "Amistoso"
    neutral: bool = False
    type: str = Field(default="independent")   # independent | future_match
    fixture_id: int | None = None              # obrigatório p/ future_match

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in ("independent", "future_match"):
            raise ValueError("type deve ser 'independent' ou 'future_match'.")
        return v


class AnalysisResponse(BaseModel):
    id: str
    type: str
    status: str
    home_team: str
    away_team: str
    tournament: str
    fixture_id: int | None
    algo_version: str
    data_version: str | None
    model_hash: str | None
    created_at: datetime
    credits_consumed: int
    credits_reserved: int
    available_balance: Decimal
    snapshot: dict


class AnalysisSummary(BaseModel):
    id: str
    type: str
    status: str
    home_team: str
    away_team: str
    tournament: str
    fixture_id: int | None
    algo_version: str
    created_at: datetime


class AnalysisPage(BaseModel):
    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int
