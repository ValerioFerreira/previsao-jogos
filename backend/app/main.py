from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Precisa vir antes de allowed_origins() (usado no add_middleware abaixo): é este import
# que carrega backend/.env (app/db/connection.py::_load_local_dotenv), então CORS_ORIGINS
# só existe em os.environ se isso rodar primeiro. Sem essa ordem, um CORS_ORIGINS só
# definido no .env (não como env var real do processo) é lido como ausente e a origem
# configurada localmente cai silenciosamente no default http://localhost:3000.
import app.db.connection  # noqa: F401,E402

from app.schemas import (
    H2HResponse,
    HealthResponse,
    PredictRequest,
    TeamResponse,
    TeamsResponse,
    SystemStatusResponse,
    RecentMatchesResponse,
    AnomaliesResponse,
    TeamHistoryResponse,
    GoalTimingResponse,
    RefereeStatsResponse,
    InjuriesResponse,
    PmfPreviewResponse,
    CompetitionBenchmarkResponse,
)
from app.services.predictor_service import (
    allowed_origins,
    get_predictor,
    predict_match,
    get_system_status,
    get_recent_matches,
    get_team_anomalies,
    get_team_history,
    get_goal_timing,
    get_referee_stats,
    get_injuries,
    get_pmf_preview,
    get_competition_benchmark,
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
from app.domains.security.router import router as security_router  # noqa: E402
from app.domains.promotions.router import router as promotions_router  # noqa: E402
from app.domains.promotions.router import banners_router  # noqa: E402
from app.domains.analytics.router import router as analytics_router  # noqa: E402
from app.domains.affiliates.router import router as affiliates_router  # noqa: E402
from app.domains.campaigns.router import router as campaigns_router  # noqa: E402
from app.domains.notifications.router import router as notifications_router  # noqa: E402
from app.domains.support.router import router as support_router  # noqa: E402

app.include_router(auth_router)
app.include_router(wallet_router)
app.include_router(payments_router)
app.include_router(legal_router)
app.include_router(analysis_router)
app.include_router(bets_router)
app.include_router(admin_router)
app.include_router(security_router)
app.include_router(promotions_router)
app.include_router(banners_router)
app.include_router(analytics_router)
app.include_router(affiliates_router)
app.include_router(campaigns_router)
app.include_router(notifications_router)
app.include_router(support_router)

# Cadastro depende de e-mail entregável + JWT com segredo real. Em APP_ENV=production,
# uma configuração que quebraria o cadastro derruba o boot aqui, em vez de virar um 502
# (ou, pior, um 201 silencioso com o OTP no log) na primeira tentativa de um usuário real.
from app.core.startup import validate_startup_config  # noqa: E402

validate_startup_config()


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


@app.post("/api/cron/poll-invoices")
def cron_poll_invoices(token: str = Query(default="")) -> dict:
    """Reconsulta no provedor de nota fiscal (ex.: NFE.io) os documentos ainda
    'pending' (emissão assíncrona) e persiste a transição de status. Feito para um
    cron periódico. Protegido por CRON_TOKEN (se a env var estiver setada)."""
    import os
    expected = os.getenv("CRON_TOKEN")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Token inválido.")
    from app.db.base import SessionLocal
    from app.domains.payments.service import poll_pending_invoices
    db = SessionLocal()
    try:
        return poll_pending_invoices(db)
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


@app.get("/api/referees/{name:path}/stats", response_model=RefereeStatsResponse)
def referee_stats(name: str) -> RefereeStatsResponse:
    return RefereeStatsResponse(**get_referee_stats(name))


@app.get("/api/team-ids")
def team_ids() -> dict:
    return get_team_ids()


@app.get("/api/competition-benchmark", response_model=CompetitionBenchmarkResponse)
def competition_benchmark(tournament: str = Query("")) -> CompetitionBenchmarkResponse:
    return CompetitionBenchmarkResponse(**get_competition_benchmark(tournament))


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


@app.get("/api/pmf-preview", response_model=PmfPreviewResponse)
def pmf_preview(home: str = Query(...), away: str = Query(...),
                neutral: bool = Query(False), tournament: str = Query("Copa do Mundo")) -> PmfPreviewResponse:
    """Prévia reduzida (grátis) da distribuição de gols + O/U 2.5 + 1X2."""
    return PmfPreviewResponse(**get_pmf_preview(home, away, neutral=neutral, tournament=tournament))


@app.get("/api/scorers")
def scorers(home: str = Query(...), away: str = Query(...)) -> dict:
    """Prováveis goleadores (prop "jogador a marcar") de um confronto."""
    from app.services.scorer_service import get_scorers
    predictor = get_predictor()
    return get_scorers(predictor.norm_team(home), predictor.norm_team(away))


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


@app.get("/api/teams/{team_name:path}/goal-timing", response_model=GoalTimingResponse)
def goal_timing(team_name: str) -> GoalTimingResponse:
    predictor = get_predictor()
    team_match = None
    for t in predictor.teams():
        if t.lower() == team_name.lower():
            team_match = t
            break
    if not team_match:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")

    return GoalTimingResponse(**get_goal_timing(team_match))


@app.get("/api/teams/{team_name:path}/injuries", response_model=InjuriesResponse)
def injuries(team_name: str) -> InjuriesResponse:
    predictor = get_predictor()
    team_match = None
    for t in predictor.teams():
        if t.lower() == team_name.lower():
            team_match = t
            break
    if not team_match:
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")

    return InjuriesResponse(**get_injuries(team_match))
