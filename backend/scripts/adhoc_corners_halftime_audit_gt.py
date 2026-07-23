#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_audit_gt.py
==============================================
Auditoria do gabarito StatsBomb (data/external/corners_halftime_ground_truth.parquet,
2068 linhas apos o rerun com fix de encoding/nome curto). Achado (Plan agent,
2026-07-23): boa parte das temporadas de La Liga/Bundesliga/Ligue1 fora de
2015/16 sao pacotes "todos os jogos de UM time" do StatsBomb open-data
(ex.: La Liga fora de 2015/16 = so jogos do Barcelona), nao amostra aleatoria
da liga inteira -- viesa qualquer estimativa de fracao 2T se usado sem cuidado.
Champions League = so a final de cada temporada (1 jogo/temporada, confirmado
via matches/16/*.json).

Marca cada partida como:
  - "clean": temporada com cobertura de liga inteira (multi-time, fracao de
    qualquer time isolado <=15% das partidas daquela temporada+torneio).
  - "single_team_biased": temporada onde 1 time aparece em >15% dos jogos
    (tipicamente pacotes tipo "todos os jogos do Barcelona/Leverkusen/PSG").

Uso: python scripts/adhoc_corners_halftime_audit_gt.py
Saida: data/external/corners_halftime_ground_truth_labeled.parquet
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "external" / "corners_halftime_ground_truth.parquet"
OUT_PATH = ROOT / "data" / "external" / "corners_halftime_ground_truth_labeled.parquet"

BIAS_THRESHOLD = 0.15


def main() -> None:
    gt = pd.read_parquet(IN_PATH)
    gt["date"] = pd.to_datetime(gt["date"])
    gt["season"] = gt["date"].dt.year.where(gt["date"].dt.month >= 7, gt["date"].dt.year - 1)
    gt["comp_season"] = gt["tournament"] + "_" + gt["season"].astype(str)

    sample_type = {}
    dominant_team = {}
    for cs, sub in gt.groupby("comp_season"):
        teams = pd.concat([sub["home_team"], sub["away_team"]])
        top_team, top_count = teams.value_counts().index[0], teams.value_counts().iloc[0]
        frac = top_count / len(sub)
        if frac > BIAS_THRESHOLD:
            sample_type[cs] = "single_team_biased"
            dominant_team[cs] = f"{top_team} ({frac:.0%})"
        else:
            sample_type[cs] = "clean"
            dominant_team[cs] = ""

    gt["sample_type"] = gt["comp_season"].map(sample_type)
    gt["dominant_team"] = gt["comp_season"].map(dominant_team)

    print("=== Resumo por comp_season ===")
    summary = gt.groupby(["comp_season", "sample_type"]).size().reset_index(name="n")
    print(summary.to_string(index=False))

    n_clean = (gt["sample_type"] == "clean").sum()
    n_biased = (gt["sample_type"] == "single_team_biased").sum()
    print(f"\nTotal: {len(gt)} | clean: {n_clean} | single_team_biased: {n_biased}")

    gt.to_parquet(OUT_PATH, index=False)
    print(f"Salvo: {OUT_PATH}")


if __name__ == "__main__":
    main()
