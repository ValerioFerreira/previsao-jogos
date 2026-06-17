from typing import Any

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    home_team: str = Field(..., examples=["Brazil"])
    away_team: str = Field(..., examples=["Argentina"])
    neutral: bool = False
    tournament: str = "Copa do Mundo"
    home_vals: dict[str, float | int | None] | None = None
    away_vals: dict[str, float | int | None] | None = None
    context_overrides: dict[str, float | int | None] | None = None
    h2h_overrides: dict[str, float | int | None] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str


class TeamsResponse(BaseModel):
    teams: list[str]
    tournaments: list[str]


class TeamResponse(BaseModel):
    team: str
    defaults: dict[str, Any]
    bases: list[str]


class H2HResponse(BaseModel):
    home: str
    away: str
    summary: str
    metrics: dict[str, Any]

