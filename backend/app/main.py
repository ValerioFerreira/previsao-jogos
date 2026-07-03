from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    H2HResponse,
    HealthResponse,
    PredictRequest,
    TeamResponse,
    TeamsResponse,
    SystemStatusResponse,
    RecentMatchesResponse,
    AnomaliesResponse,
    TeamHistoryResponse
)
from app.services.predictor_service import (
    allowed_origins,
    get_predictor,
    predict_match,
    get_system_status,
    get_recent_matches,
    get_team_anomalies,
    get_team_history,
    get_referees,
    get_team_ids,
    get_upcoming_fixtures,
    get_match_detail,
    get_past_fixtures,
)


app = FastAPI(
    title="Previsao de Jogos API",
    version="1.0.0",
    description="API REST para previsoes de partidas de selecoes com modelos scikit-learn.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Camada de usuários/monetização. Não afeta as rotas de previsão.
from app.domains.auth.router import router as auth_router  # noqa: E402
from app.domains.wallet.router import router as wallet_router  # noqa: E402
from app.domains.payments.router import router as payments_router  # noqa: E402
from app.domains.legal.router import router as legal_router  # noqa: E402
from app.domains.analysis.router import router as analysis_router  # noqa: E402
from app.domains.bets.router import router as bets_router  # noqa: E402
from app.domains.admin.router import router as admin_router  # noqa: E402

app.include_router(auth_router)
app.include_router(wallet_router)
app.include_router(payments_router)
app.include_router(legal_router)
app.include_router(analysis_router)
app.include_router(bets_router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict:
    """Raiz — usada por uptime pings (ex.: cron-job.org) para manter o Render acordado."""
    return {"status": "ok", "service": "previsao-jogos-api", "health": "/health", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="previsao-jogos-api")


@app.get("/api/cron/refresh-fixtures")
def cron_refresh_fixtures(token: str = Query(default="")) -> dict:
    """Atualiza a lista de partidas passadas (past_fixtures) com as últimas 24-72h,
    deixando-as selecionáveis no seletor. Feito para um cron diário (cron-job.org).
    Protegido por CRON_TOKEN (se a env var estiver setada)."""
    import os
    expected = os.getenv("CRON_TOKEN")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Token inválido.")
    from app.services.fixtures_refresh import refresh_past_fixtures
    res = refresh_past_fixtures(days_back=3)
    # invalida o cache de leitura para a lista nova aparecer já no mesmo processo
    from app.services.predictor_service import _READER_MEMO
    for k in ("get_past_fixtures", "get_team_ids", "_fixture_index", "_fixture_index_norm"):
        _READER_MEMO.pop(k, None)
    return res


@app.post("/api/cron/settle-bets")
def cron_settle_bets(token: str = Query(default="")) -> dict:
    """Liquida as apostas com partida encerrada (após o delay de segurança): consome o
    crédito das vencedoras e estorna o das não vencedoras. Feito para um cron periódico.
    Protegido por CRON_TOKEN (se a env var estiver setada)."""
    import os
    expected = os.getenv("CRON_TOKEN")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Token inválido.")
    from app.db.base import SessionLocal
    from app.domains.bets.results import get_result_provider
    from app.domains.bets.settlement import run_due_settlements
    db = SessionLocal()
    try:
        return run_due_settlements(db, get_result_provider())
    finally:
        db.close()


@app.get("/teams", response_model=TeamsResponse)
def teams() -> TeamsResponse:
    predictor = get_predictor()
    return TeamsResponse(
        teams=predictor.teams(),
        tournaments=list(predictor.meta["tournament_weights"].keys()),
    )


@app.get("/team/{nome:path}", response_model=TeamResponse)
def team(nome: str) -> TeamResponse:
    predictor = get_predictor()
    defaults = predictor.team_defaults(nome)
    if not defaults:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
    return TeamResponse(team=nome, defaults=defaults, bases=predictor.bases())


@app.get("/h2h", response_model=H2HResponse)
def h2h(home: str = Query(...), away: str = Query(...)) -> H2HResponse:
    predictor = get_predictor()
    home, away = predictor.norm_team(home), predictor.norm_team(away)
    if home == away:
        raise HTTPException(status_code=400, detail="Escolha duas selecoes diferentes.")
    if home not in predictor.teams() or away not in predictor.teams():
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
    metrics = predictor.head_to_head(home, away)
    summary = metrics.pop("_resumo")
    return H2HResponse(home=home, away=away, summary=summary, metrics=metrics)


@app.post("/predict")
def predict(payload: PredictRequest) -> dict:
    predictor = get_predictor()
    # canoniza nomes (jogos futuros podem vir como "Czechia", "Türkiye", etc.)
    payload.home_team = predictor.norm_team(payload.home_team)
    payload.away_team = predictor.norm_team(payload.away_team)
    if payload.home_team == payload.away_team:
        raise HTTPException(status_code=400, detail="Escolha duas selecoes diferentes.")
    if payload.home_team not in predictor.teams() or payload.away_team not in predictor.teams():
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
    if payload.tournament not in predictor.meta["tournament_weights"]:
        raise HTTPException(status_code=400, detail="Competicao invalida.")
    return predict_match(payload)


@app.get("/api/referees")
def referees() -> dict:
    return {"referees": get_referees()}


@app.get("/api/team-ids")
def team_ids() -> dict:
    return get_team_ids()


@app.get("/api/fixtures/upcoming")
def upcoming_fixtures() -> dict:
    return {"fixtures": get_upcoming_fixtures()}


@app.get("/api/fixtures/past")
def past_fixtures(limit: int = Query(100000)) -> dict:
    # devolve TODAS as partidas passadas (o seletor filtra/limita no cliente);
    # antes o corte em 1500 escondia jogos antigos de cada seleção.
    return {"fixtures": get_past_fixtures()[:limit]}


@app.get("/api/match-detail")
def match_detail(home: str = Query(...), away: str = Query(...), date: str = Query(...)) -> dict:
    return get_match_detail(home, away, date)


@app.get("/api/system/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    status = get_system_status()
    return SystemStatusResponse(**status)


@app.get("/api/teams/{team_name:path}/recent", response_model=RecentMatchesResponse)
def recent_matches(team_name: str) -> RecentMatchesResponse:
    predictor = get_predictor()
    # Case-insensitive check
    team_match = None
    for t in predictor.teams():
        if t.lower() == team_name.lower():
            team_match = t
            break
    if not team_match:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
        
    data = get_recent_matches(team_match)
    return RecentMatchesResponse(team=team_match, matches=data["matches"], total_matches=data["total_matches"])


@app.get("/api/teams/{team_name:path}/anomalies", response_model=AnomaliesResponse)
def team_anomalies(team_name: str) -> AnomaliesResponse:
    predictor = get_predictor()
    # Case-insensitive check
    team_match = None
    for t in predictor.teams():
        if t.lower() == team_name.lower():
            team_match = t
            break
    if not team_match:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
        
    anomalies = get_team_anomalies(team_match)
    return AnomaliesResponse(team=team_match, anomalies=anomalies)


@app.get("/api/teams/{team_name:path}/history", response_model=TeamHistoryResponse)
def team_history(team_name: str) -> TeamHistoryResponse:
    predictor = get_predictor()
    team_match = None
    for t in predictor.teams():
        if t.lower() == team_name.lower():
            team_match = t
            break
    if not team_match:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
        
    history = get_team_history(team_match)
    return TeamHistoryResponse(**history)
