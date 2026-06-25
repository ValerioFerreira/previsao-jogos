#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_h2h_results.py
============================
Base de resultados para o CARD DE CONFRONTO DIRETO com histórico profundo:
martj42 (pré-2016, desde 1872) + api-football (2016+, o que ja usamos). Nomes
canonizados (mesmo alias do predictor) p/ casar as duas fontes e o nome consultado.
Salva api/model_artifacts/h2h_results.csv (date, home_team, away_team, home_score,
away_score). Só placar — as médias de box-score continuam vindo de h2h_stats (api).
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from predictor import TEAM_ALIASES  # mesmo mapa de alias do backend

MARTJ42 = ROOT / "cache_apifootball" / "results_martj42.csv"
API = ROOT / "api" / "model_artifacts" / "results_slim.csv"
OUT = ROOT / "api" / "model_artifacts" / "h2h_results.csv"
COLS = ["date", "home_team", "away_team", "home_score", "away_score"]


def norm(s):
    return TEAM_ALIASES.get(s, s)


def main():
    api = pd.read_csv(API, parse_dates=["date"])[COLS]
    cut = api["date"].min()  # 2016-01-03
    mj = pd.read_csv(MARTJ42, parse_dates=["date"])[COLS].dropna(subset=["home_score", "away_score"])
    mj_old = mj[mj["date"] < cut]
    combined = pd.concat([mj_old, api], ignore_index=True)
    combined["home_team"] = combined["home_team"].map(norm)
    combined["away_team"] = combined["away_team"].map(norm)
    combined = combined.drop_duplicates(subset=["date", "home_team", "away_team"]).sort_values("date")
    combined.to_csv(OUT, index=False)
    print(f"h2h_results: {len(combined)} jogos ({combined['date'].min().date()} a {combined['date'].max().date()}) -> {OUT}")
    print(f"  martj42 pre-{cut.date()}: {len(mj_old)} | api: {len(api)}")


if __name__ == "__main__":
    main()
