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


class SystemStatusResponse(BaseModel):
    last_successful_run: str


class RecentMatch(BaseModel):
    date: str
    opponent: str
    is_home: bool
    goals_scored: int
    goals_conceded: int
    sb_shots: float
    sb_shots_on_target: float
    sb_corners: float
    sb_cards: float


class RecentMatchesResponse(BaseModel):
    team: str
    matches: list[RecentMatch]
    total_matches: int = 0


class Anomaly(BaseModel):
    stat: str
    z_score: float
    window_size: int
    message: str
    type: str  # "alert" (negativo/preocupante) ou "positive" (positivo/bom)


class AnomaliesResponse(BaseModel):
    team: str
    anomalies: list[Anomaly]


class EloHistoryPoint(BaseModel):
    date: str
    elo: float


class FrequencyPoint(BaseModel):
    label: str
    frequency: int


class TeamHistoryResponse(BaseModel):
    team: str
    elo_history: list[EloHistoryPoint]
    attack_avg: float
    defense_avg: float
    corners_freq: list[FrequencyPoint]
    cards_freq: list[FrequencyPoint]
