"""
app/services/assist_service.py
===============================
Serving do prop "JOGADOR A DAR ASSISTÊNCIA": P(jogador assiste | joga), calibrada.
Usa assist_model.joblib (scripts/build_assist_model.py), mesmo padrão de
shots_prop_service.py -- anexado a cada jogador pelo get_scorers, formando o card
unificado "Jogador".
"""
from __future__ import annotations
import os
from functools import lru_cache
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _art_path(scope: str) -> str:
    d = "model_artifacts_clubes" if scope == "clube" else "model_artifacts"
    return os.path.join(ROOT, d, "assist_model.joblib")


@lru_cache(maxsize=2)
def _load(scope: str = "selecao"):
    import joblib
    path = _art_path(scope)
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def available(scope: str = "selecao") -> bool:
    return _load(scope) is not None


def assist_probs_by_player(team_id: int, opp_id: int, is_home: int, scope: str = "selecao") -> dict[int, float]:
    """player_id -> P(assiste | joga), calibrada."""
    art = _load(scope)
    if art is None:
        return {}
    ps = art["player_state"]
    td = art["team_def"].set_index("team_id")["gc"].to_dict()
    model, iso, feats = art["model"], art["calibrator"], art["feats"]
    glob_gc = art["glob_gc"]
    cand = ps[ps["team_id"] == team_id].copy()
    if cand.empty:
        return {}
    cand["is_home"] = is_home
    cand["opp_gc"] = td.get(opp_id, glob_gc)
    X = cand[feats].astype(float).values
    raw = model.predict_proba(X)[:, 1]
    cal = np.clip(iso.predict(raw), 1e-4, 1 - 1e-4)
    out: dict[int, float] = {}
    for pid, p in zip(cand["player_id"], cal):
        if pid == pid:  # not NaN
            out[int(pid)] = float(p)
    return out
