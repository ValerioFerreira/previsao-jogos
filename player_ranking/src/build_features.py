#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/build_features.py
====================================
PASSO 5 — Agrega a forma de clube dos jogadores do elenco-base em features da
selecao (home/away/diff), com peso de liga, e calcula a COBERTURA por jogo
(fracao do elenco-base com forma de clube valida). Junta com o CSV de producao
(Elo/resultado). Saida: dataset_player_ranking.parquet.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "player_ranking" / "data" / "interim"
PROC = ROOT / "player_ranking" / "data" / "processed"
CSV = ROOT / "international_features_enriched_apifootball.csv"

# Peso de liga (placeholder simples, por substring do nome; default 0.5). Spec §6:
# comecar simples; so "aprender" o peso depois que o sinal bruto provar valor.
LEAGUE_WEIGHT = [
    (("premier league", "la liga", "serie a", "bundesliga", "ligue 1"), 1.0),  # top-5 (cuidado: Serie A tem homônimos)
    (("eredivisie", "primeira liga", "liga portugal", "championship", "jupiler", "pro league",
      "super lig", "süper lig", "premiership", "bundesliga 2", "serie b", "ligue 2", "2. bundesliga",
      "saudi", "mls", "major league"), 0.8),
    (("liga mx", "brasileiro", "brazil serie", "argentina", "eqtisat", "j1", "j-league", "k league",
      "ekstraklasa", "superliga", "allsvenskan", "eliteserien", "super league"), 0.65),
]
DEFAULT_W = 0.5


def league_weight(name):
    n = (name or "").lower()
    for pats, w in LEAGUE_WEIGHT:
        if any(p in n for p in pats):
            return w
    return DEFAULT_W


def team_features(pids, form_map):
    """Agrega os jogadores com forma de clube valida. Retorna dict de features +
    cobertura (fracao do elenco com forma valida e minutos>0)."""
    recs = [form_map[p] for p in pids if p in form_map]
    active = [r for r in recs if (r.get("minutes") or 0) > 0]
    n_base = len(pids)
    cov = len(active) / n_base if n_base else 0.0
    if not active:
        return {"pr_cov": cov, "pr_n": 0}
    mins = np.array([r["minutes"] for r in active])
    w = mins / mins.sum()
    rating = np.array([r["rating"] if r["rating"] is not None else np.nan for r in active])
    lw = np.array([league_weight(r["league_name"]) for r in active])
    # rating ponderado por minutos (ignora NaN); rating*peso_liga = "rating ajustado"
    valid = ~np.isnan(rating)
    rating_w = float(np.average(rating[valid], weights=mins[valid])) if valid.any() else np.nan
    rating_adj = float(np.average((rating * lw)[valid], weights=mins[valid])) if valid.any() else np.nan
    p90 = mins / 90.0
    goals90 = np.where(p90 > 0, np.array([r["goals"] for r in active]) / np.maximum(p90, 1), 0)
    shots90 = np.where(p90 > 0, np.array([r["shots"] for r in active]) / np.maximum(p90, 1), 0)
    kp90 = np.where(p90 > 0, np.array([r["key_passes"] for r in active]) / np.maximum(p90, 1), 0)
    return {
        "pr_cov": cov, "pr_n": len(active),
        "pr_rating": rating_w,
        "pr_rating_adj": rating_adj,
        "pr_minutes_mean": float(mins.mean()),
        "pr_topleague_share": float(w[lw >= 0.9].sum()),
        "pr_leagueweight_mean": float(np.average(lw, weights=mins)),
        "pr_depth": int((mins >= 900).sum()),
        "pr_goals90": float(np.average(goals90, weights=mins)),
        "pr_shots90": float(np.average(shots90, weights=mins)),
        "pr_keypass90": float(np.average(kp90, weights=mins)),
    }


def main():
    t = pd.read_parquet(INTERIM / "target_matches.parquet")
    form = pd.read_parquet(INTERIM / "player_club_form.parquet")
    form_map = {int(r.player_id): r._asdict() if hasattr(r, "_asdict") else dict(r)
                for r in form.to_dict("records")} if False else {}
    # mapa player_id -> registro de forma (a season ja casa por janela; 1 registro/jogador)
    form_map = {int(rec["player_id"]): rec for rec in form.to_dict("records")}

    rows = []
    for _, m in t.iterrows():
        hf = team_features([int(p) for p in m["home_pids"]], form_map)
        af = team_features([int(p) for p in m["away_pids"]], form_map)
        row = {"match_id": m["match_id"], "date": m["date"], "result": m["result"],
               "home_team": m["home_team"], "away_team": m["away_team"],
               "season_club": m["season_club"]}
        for k, v in hf.items():
            row[f"home_{k}"] = v
        for k, v in af.items():
            row[f"away_{k}"] = v
        rows.append(row)
    feat = pd.DataFrame(rows)

    # diffs (home - away) das features numericas de player-ranking
    for c in ["pr_rating", "pr_rating_adj", "pr_minutes_mean", "pr_topleague_share",
              "pr_leagueweight_mean", "pr_depth", "pr_goals90", "pr_shots90", "pr_keypass90"]:
        feat[f"diff_{c}"] = feat[f"home_{c}"] - feat[f"away_{c}"]
    feat["min_cov"] = feat[["home_pr_cov", "away_pr_cov"]].min(axis=1)

    # junta Elo/baseline do CSV por match_id
    csv = pd.read_csv(CSV, parse_dates=["date"])
    base_cols = [c for c in ["match_id", "elo_diff", "home_elo_pre", "away_elo_pre", "neutral",
                             "real_home_advantage", "tournament_weight", "diff_gd_l5",
                             "h2h_home_gd_mean"] if c in csv.columns]
    feat = feat.merge(csv[base_cols], on="match_id", how="left")

    PROC.mkdir(parents=True, exist_ok=True)
    feat.to_parquet(PROC / "dataset_player_ranking.parquet")
    print(f"dataset: {len(feat)} jogos")
    print(f"cobertura min(2 lados): media {feat.min_cov.mean():.2f} | "
          f">=0.5: {(feat.min_cov>=0.5).sum()} | >=0.7: {(feat.min_cov>=0.7).sum()}")
    print(f"rating disponivel (home): {feat.home_pr_rating.notna().sum()}/{len(feat)}")
    print(f"salvo: {PROC / 'dataset_player_ranking.parquet'}")


if __name__ == "__main__":
    main()
