"""
app/services/shots_prop_service.py
==================================
Serving do prop "JOGADOR A FINALIZAR": P(jogador dá >= N finalizações | joga) para as
linhas 0,5 / 1,5 / 2,5, calibrada. Usa shots_prop_model.joblib (3 classificadores + estado
por jogador + defesa-de-finalizações por time), de scripts/build_shots_prop_model.py.

Exposto por linha via `shots_probs_by_player(team_id, opp_id, is_home)` — o get_scorers
anexa essas probabilidades a cada jogador, formando o card unificado "Jogador".
"""
from __future__ import annotations
import os
from functools import lru_cache
import numpy as np

ART = os.path.join(os.path.dirname(__file__), "..", "..", "model_artifacts", "shots_prop_model.joblib")
LINE_LABEL = {1: "0.5", 2: "1.5", 3: "2.5"}  # >= N  ->  linha Over N-0.5


@lru_cache(maxsize=1)
def _load():
    import joblib
    if not os.path.exists(ART):
        return None
    return joblib.load(ART)


def available() -> bool:
    return _load() is not None


def shots_probs_by_player(team_id: int, opp_id: int, is_home: int) -> dict[int, dict[str, float]]:
    """player_id -> {"0.5": p, "1.5": p, "2.5": p} (probabilidades calibradas)."""
    art = _load()
    if art is None:
        return {}
    ps = art["player_state"]
    td = art["team_def"].set_index("team_id")["sa"].to_dict()
    feats = art["feats"]; glob_sa = art["glob_sa"]
    cand = ps[ps["team_id"] == team_id].copy()
    if cand.empty:
        return {}
    cand["is_home"] = is_home
    cand["opp_shots_allowed"] = td.get(opp_id, glob_sa)
    X = cand[feats].astype(float).values
    out: dict[int, dict[str, float]] = {}
    probs_by_line = {}
    for L, mm in art["models"].items():
        raw = mm["model"].predict_proba(X)[:, 1]
        probs_by_line[L] = np.clip(mm["calibrator"].predict(raw), 1e-4, 1 - 1e-4)
    for i, (_, r) in enumerate(cand.iterrows()):
        pid = r.player_id
        if pid != pid:  # NaN
            continue
        # monotonicidade: P(>=1) >= P(>=2) >= P(>=3)
        vals = {L: float(probs_by_line[L][i]) for L in art["lines"]}
        prev = 1.0
        for L in sorted(vals):
            vals[L] = min(vals[L], prev); prev = vals[L]
        out[int(pid)] = {LINE_LABEL[L]: round(vals[L], 4) for L in vals}
    return out
