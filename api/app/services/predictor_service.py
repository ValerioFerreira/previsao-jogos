from __future__ import annotations

import os
import json
import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
import pandas as pd

from predictor import Predictor
from app.services.odds import enrich_with_odds
from anomaly_detector import detect_anomalies


API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parent
ARTIFACT_DIR = API_ROOT / "model_artifacts"
PARQUET_PATH = REPO_ROOT / "data" / "built" / "matches.parquet"
LAST_UPDATE_PATH = REPO_ROOT / "data" / "state" / "last_update.json"
LOG_FILE_PATH = REPO_ROOT / "data" / "state" / "predictions_log.jsonl"


@lru_cache(maxsize=1)
def get_predictor() -> Predictor:
    return Predictor(art_dir=str(ARTIFACT_DIR))


def clean_values(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {key: value for key, value in values.items() if value is not None}


def predict_match(payload: Any) -> dict[str, Any]:
    predictor = get_predictor()
    raw = predictor.predict(
        payload.home_team,
        payload.away_team,
        neutral=payload.neutral,
        tournament=payload.tournament,
        home_vals=clean_values(payload.home_vals),
        away_vals=clean_values(payload.away_vals),
        context_overrides=clean_values(payload.context_overrides),
        h2h_overrides=clean_values(payload.h2h_overrides),
    )
    res = {
        **raw,
        "odds": enrich_with_odds(raw, predictor.meta.get("n_train", {})),
    }

    # Módulo 4.1: Registro de Logs em JSON Lines
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_payload = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "home_team": payload.home_team,
            "away_team": payload.away_team,
            "neutral": payload.neutral,
            "tournament": payload.tournament,
            "home_vals": clean_values(payload.home_vals),
            "away_vals": clean_values(payload.away_vals),
            "prediction": res
        }
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_payload, default=str) + "\n")
    except Exception as e:
        # Registrar o erro sem travar a resposta da requisição do usuário
        print(f"[LOG ERROR] Falha ao gravar log de previsão: {e}")

    return res


def get_system_status() -> dict[str, str]:
    """Retorna o timestamp da última atualização bem-sucedida do pipeline."""
    if LAST_UPDATE_PATH.exists():
        try:
            with open(LAST_UPDATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback se o arquivo de timestamp ainda não foi criado
    return {"last_successful_run": "2026-06-22 00:00:00"}


def get_recent_matches(team_name: str) -> list[dict[str, Any]]:
    """Carrega matches.parquet e extrai as últimas 5 partidas reais da equipe."""
    if not PARQUET_PATH.exists():
        return []
    
    df = pd.read_parquet(PARQUET_PATH)
    
    # Filtrar jogos do time correspondente
    df_team = df[df["team"] == team_name].copy()
    if len(df_team) == 0:
        return []
        
    # Ordenar por data decrescente
    df_team = df_team.sort_values(by="date", ascending=False).reset_index(drop=True)
    
    # Obter os últimos 5 jogos
    df_recent = df_team.head(5)
    
    matches = []
    for _, row in df_recent.iterrows():
        matches.append({
            "date": str(row["date"]),
            "opponent": str(row["opponent"]),
            "is_home": bool(row["is_home"] == 1),
            "goals_scored": int(row["goals_scored"]),
            "goals_conceded": int(row["goals_conceded"]),
            "sb_shots": float(row["sb_shots"]) if pd.notna(row["sb_shots"]) else 0.0,
            "sb_shots_on_target": float(row["sb_shots_on_target"]) if pd.notna(row["sb_shots_on_target"]) else 0.0,
            "sb_corners": float(row["sb_corners"]) if pd.notna(row["sb_corners"]) else 0.0,
            "sb_cards": float(row["sb_cards"]) if pd.notna(row["sb_cards"]) else 0.0
        })
        
    return matches


def get_team_anomalies(team_name: str) -> list[dict[str, Any]]:
    """Detecta anomalias estatísticas recentes baseadas no Z-Score da equipe."""
    # Obter o torneio padrão para determinar a classe competitivo/amistoso
    return detect_anomalies(PARQUET_PATH, team_name, target_competition="World Cup")


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGIN") or ""
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]
