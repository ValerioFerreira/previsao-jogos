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

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _art_path(scope: str) -> str:
    d = "model_artifacts_clubes" if scope == "clube" else "model_artifacts"
    return os.path.join(ROOT, d, "scorer_model.joblib")


@lru_cache(maxsize=2)
def _load(scope: str = "selecao"):
    import joblib
    path = _art_path(scope)
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def _fair_odd(p: float) -> float:
    p = min(0.999, max(0.001, float(p)))
    return max(1.0, round(1.0 / p, 2))


def get_scorers(home: str, away: str, top: int = 12, min_recent_year: int = 2023,
                scope: str = "selecao") -> dict[str, Any]:
    art = _load(scope)
    other_scope = "clube" if scope != "clube" else "selecao"
    art_other = _load(other_scope)
    if art is None and art_other is None:
        return {"disponivel": False, "motivo": "modelo de goleador ainda não construído"}

    active_art = art or art_other
    from app.services.predictor_service import get_team_id, _norm
    hid = get_team_id(home, scope)
    aid = get_team_id(away, scope)
    if not hid or not aid:
        return {"disponivel": False, "motivo": "sem team_id para uma das equipes"}

    # Prop de finalizações e de assistência do jogador (mesmo elenco), anexadas a cada jogador.
    from app.services import shots_prop_service, assist_service
    shots_ok = shots_prop_service.available(scope) or shots_prop_service.available(other_scope)
    assist_ok = assist_service.available(scope) or assist_service.available(other_scope)

    def side(team_id: int, opp_id: int, is_home: int):
        cand = None
        target_art = None

        if art is not None and "player_state" in art:
            ps = art["player_state"]
            sub = ps[ps["team_id"] == team_id]
            if not sub.empty:
                cand = sub.copy()
                target_art = art

        if cand is None and art_other is not None and "player_state" in art_other:
            ps_o = art_other["player_state"]
            sub_o = ps_o[ps_o["team_id"] == team_id]
            if not sub_o.empty:
                cand = sub_o.copy()
                target_art = art_other

        if cand is None or cand.empty or target_art is None:
            return []

        td = target_art["team_def"].set_index("team_id")["gc"].to_dict()
        model, iso, feats = target_art["model"], target_art["calibrator"], target_art["feats"]
        glob_gc = target_art["glob_gc"]

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
        shots_map = shots_prop_service.shots_probs_by_player(team_id, opp_id, is_home, scope) if shots_ok else {}
        if not shots_map and shots_ok:
            shots_map = shots_prop_service.shots_probs_by_player(team_id, opp_id, is_home, other_scope)
        assist_map = assist_service.assist_probs_by_player(team_id, opp_id, is_home, scope) if assist_ok else {}
        if not assist_map and assist_ok:
            assist_map = assist_service.assist_probs_by_player(team_id, opp_id, is_home, other_scope)
        rows = []
        for _, r in cand.iterrows():
            pid = int(r.player_id) if r.player_id == r.player_id else None
            item = {"player_id": pid, "nome": r["name"], "pos": r.get("pos"),
                    "prob": round(100 * float(r.prob), 1), "odd_justa": _fair_odd(float(r.prob))}
            sp = shots_map.get(pid) if pid is not None else None
            if sp:
                item["finalizar"] = {line: {"prob": round(100 * p, 1), "odd_justa": _fair_odd(p)}
                                     for line, p in sp.items()}
            ap = assist_map.get(pid) if pid is not None else None
            if ap is not None:
                item["assistir"] = {"prob": round(100 * ap, 1), "odd_justa": _fair_odd(ap)}
            rows.append(item)
        return rows

    return {"disponivel": True,
            "info": "P(marca a qualquer momento | joga), P(finalizações ≥ linha | joga) e "
                    "P(dá assistência | joga), calibradas. Candidatos = elenco recente.",
            "finalizar_disponivel": shots_ok,
            "assistir_disponivel": assist_ok,
            home: side(hid, aid, 1), away: side(aid, hid, 0)}
