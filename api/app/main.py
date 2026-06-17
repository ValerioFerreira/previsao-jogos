from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import H2HResponse, HealthResponse, PredictRequest, TeamResponse, TeamsResponse
from app.services.predictor_service import allowed_origins, get_predictor, predict_match


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


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="previsao-jogos-api")


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
    if payload.home_team == payload.away_team:
        raise HTTPException(status_code=400, detail="Escolha duas selecoes diferentes.")
    if payload.home_team not in predictor.teams() or payload.away_team not in predictor.teams():
        raise HTTPException(status_code=404, detail="Selecao nao encontrada.")
    if payload.tournament not in predictor.meta["tournament_weights"]:
        raise HTTPException(status_code=400, detail="Competicao invalida.")
    return predict_match(payload)

