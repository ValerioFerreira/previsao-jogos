#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_h2h_stats.py
==========================
Tabela compacta de estatísticas por jogo (placar + box-score) para as MÉDIAS DO
CONFRONTO DIRETO na UI. Extraída da base enriquecida; box-score fica NaN nos jogos
sem estatística avançada (a média ignora NaN). Salva api/model_artifacts/h2h_stats.csv
(junto dos artefatos, para o predictor carregar).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "international_features_enriched_apifootball.csv"
OUT = ROOT / "api" / "model_artifacts" / "h2h_stats.csv"

COLS = {
    "date": "date", "home_team": "home_team", "away_team": "away_team",
    "home_score": "home_score", "away_score": "away_score",
    "home_cur_sb_shots": "home_shots", "away_cur_sb_shots": "away_shots",
    "home_cur_sb_shots_on_target": "home_sot", "away_cur_sb_shots_on_target": "away_sot",
    "home_cur_sb_corners": "home_corners", "away_cur_sb_corners": "away_corners",
    "home_cur_sb_cards": "home_cards", "away_cur_sb_cards": "away_cards",
}


def main():
    df = pd.read_csv(CSV, usecols=list(COLS), low_memory=False)
    df = df.rename(columns=COLS)
    df = df.dropna(subset=["home_team", "away_team", "home_score", "away_score"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"h2h_stats: {len(df)} jogos -> {OUT}")
    print("com box-score (chutes):", int(df['home_shots'].notna().sum()))


if __name__ == "__main__":
    main()
