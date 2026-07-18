from typing import Any

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    home_team: str = Field(..., examples=["Brazil"])
    away_team: str = Field(..., examples=["Argentina"])
    neutral: bool = False
    tournament: str = "Copa do Mundo"
    scope: str = "selecao"  # 'selecao' | 'clube' -- seleciona qual Predictor/artefatos usar
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
    competition: str = ""
    is_home: bool
    goals_scored: int
    goals_conceded: int
    sb_shots: float
    sb_shots_on_target: float
    sb_corners: float
    sb_cards: float
    sb_offsides: float = 0.0
    sb_fouls: float = 0.0
    sb_possession: float = 0.0
    sb_passes: float = 0.0


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


class GoalTrendPoint(BaseModel):
    label: str
    scored: int
    conceded: int


class TeamHistoryResponse(BaseModel):
    team: str
    elo_history: list[EloHistoryPoint]
    goal_trend: list[GoalTrendPoint] = []
    attack_avg: float
    defense_avg: float
    corners_freq: list[FrequencyPoint]
    cards_freq: list[FrequencyPoint]


class GoalTimingBlock(BaseModel):
    label: str
    scored: int
    conceded: int


class GoalTimingResponse(BaseModel):
    team: str
    n_matches: int
    total_scored: int
    total_conceded: int
    blocks: list[GoalTimingBlock]


class RefereeStatsResponse(BaseModel):
    referee: str
    n_matches: int
    n_card_matches: int
    n_foul_matches: int
    avg_yellow: float
    avg_red: float
    avg_cards: float
    avg_fouls: float
    bench_cards: float
    bench_fouls: float


class InjuryPlayer(BaseModel):
    player_id: int | None = None
    name: str | None = None
    reason: str | None = None
    type: str | None = None


class InjuriesResponse(BaseModel):
    team: str
    season: int | None = None
    players: list[InjuryPlayer]


class CompetitionBenchmarkResponse(BaseModel):
    attack_mean: float
    attack_std: float
    defense_mean: float
    defense_std: float
    n_teams: int
    scope: str
    team_stats: dict[str, dict[str, float]] | None = None


class PmfPreviewResponse(BaseModel):
    home: str
    away: str
    expected_goals: float | None = None
    interval: list[float] = []
    confidence: str | None = None
    distribution: list[float] = []
    prob_over_2_5: float | None = None
    odd_over_2_5: float | None = None
    odd_under_2_5: float | None = None
    prob_home: float | None = None
    prob_draw: float | None = None
    prob_away: float | None = None
