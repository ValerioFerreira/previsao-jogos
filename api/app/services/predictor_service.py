from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from predictor import Predictor

from app.services.odds import enrich_with_odds


API_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = API_ROOT / "model_artifacts"


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
    return {
        **raw,
        "odds": enrich_with_odds(raw, predictor.meta.get("n_train", {})),
    }


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGIN") or ""
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]

