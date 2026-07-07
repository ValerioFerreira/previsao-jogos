"""
app/services/scorer_service.py
==============================
Serving do modelo de GOLEADOR (prop "jogador a marcar"). Dado um confronto (home, away),
retorna, para cada lado, os jogadores mais prováveis de marcar — P(marca | joga) calibrada
+ odd justa. Usa o artefato scorer_model.joblib (modelo + calibrador + estado por jogador
+ defesa por time), construído por scripts/build_scorer_model.py.

Estratégia de candidatos: jogadores recentes daquela seleção (estado embutido), ordenados
por minutos recentes; quando houver escalação confirmada, o front pode filtrar ao XI.
"""
from __future__ import annotations
import os
from functools import lru_cache
from typing import Any, Optional
import numpy as np

ART = os.path.join(os.path.dirname(__file__), "..", "..", "model_artifacts", "scorer_model.joblib")


@lru_cache(maxsize=1)
def _load():
    import joblib
    if not os.path.exists(ART):
        return None
    return joblib.load(ART)


def _fair_odd(p: float) -> float:
    p = min(0.999, max(0.001, float(p)))
    return max(1.0, round(1.0 / p, 2))


def get_scorers(home: str, away: str, top: int = 12, min_recent_year: int = 2023) -> dict[str, Any]:
    art = _load()
    if art is None:
        return {"disponivel": False, "motivo": "modelo de goleador ainda não construído"}
    from app.services.predictor_service import get_team_ids, _norm
    name2id = get_team_ids()
    hid = name2id.get(_norm(home)) or name2id.get(home)
    aid = name2id.get(_norm(away)) or name2id.get(away)
    if not hid or not aid:
        return {"disponivel": False, "motivo": "sem team_id para uma das seleções"}

    ps = art["player_state"]; td = art["team_def"].set_index("team_id")["gc"].to_dict()
    model, iso, feats = art["model"], art["calibrator"], art["feats"]
    glob_gc = art["glob_gc"]

    def side(team_id: int, opp_id: int, is_home: int):
        cand = ps[ps["team_id"] == team_id].copy()
        if cand.empty:
            return []
        cand = cand[cand["last_date"].astype(str).str[:4].astype(int) >= min_recent_year]
        cand = cand.sort_values("minutes_base", ascending=False).head(max(top * 2, 20)).copy()
        if cand.empty:
            return []
        cand["is_home"] = is_home
        cand["opp_gc"] = td.get(opp_id, glob_gc)
        X = cand[feats].astype(float).values
        raw = model.predict_proba(X)[:, 1]
        cal = np.clip(iso.predict(raw), 1e-4, 1 - 1e-4)
        cand["prob"] = cal
        cand = cand.sort_values("prob", ascending=False).head(top)
        return [{"player_id": int(r.player_id) if r.player_id == r.player_id else None,
                 "nome": r["name"], "pos": r.get("pos"),
                 "prob": round(100 * float(r.prob), 1), "odd_justa": _fair_odd(float(r.prob))}
                for _, r in cand.iterrows()]

    return {"disponivel": True,
            "info": "P(marca a qualquer momento | joga), calibrada. Candidatos = elenco recente da seleção.",
            home: side(hid, aid, 1), away: side(aid, hid, 0)}
