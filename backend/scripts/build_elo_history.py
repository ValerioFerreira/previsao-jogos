#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_elo_history.py
=============================
Extrai o histórico de Elo (rating pré-jogo) por time a partir dos datasets de
treino que JÁ calculam `home_elo_pre`/`away_elo_pre` linha-a-linha
(international_features_enriched_apifootball.csv p/ seleção,
data/built/club_features_enriched.parquet p/ clube) -- não recalcula nada,
só "derrete" home/away em formato longo (team, date, elo) e resample mensal
(último valor do mês) para uma série compacta e legível no gráfico "Evolução
de Elo" de /estatisticas.

Grava:
  model_artifacts/elo_history.csv        (seleção)
  model_artifacts_clubes/elo_history.csv (clube)

Uso: python scripts/build_elo_history.py [--scope selecao|clube|all]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SELECAO_CSV = ROOT / "international_features_enriched_apifootball.csv"
CLUBE_PARQUET = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_SELECAO = ROOT / "model_artifacts" / "elo_history.csv"
OUT_CLUBE = ROOT / "model_artifacts_clubes" / "elo_history.csv"


def _monthly_long(df: pd.DataFrame) -> pd.DataFrame:
    """home/away -> long (team, date, elo), resample mensal (último valor)."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    long = pd.concat([
        df[["date", "home_team", "home_elo_pre"]].rename(columns={"home_team": "team", "home_elo_pre": "elo"}),
        df[["date", "away_team", "away_elo_pre"]].rename(columns={"away_team": "team", "away_elo_pre": "elo"}),
    ], ignore_index=True)
    long = long.dropna(subset=["team", "elo"]).sort_values("date")
    long["month"] = long["date"].dt.to_period("M")
    monthly = long.groupby(["team", "month"], as_index=False).last()
    monthly["date"] = monthly["month"].dt.to_timestamp().dt.strftime("%Y-%m")
    return monthly[["team", "date", "elo"]].sort_values(["team", "date"])


def build_selecao() -> None:
    if not SELECAO_CSV.exists():
        print(f"[AVISO] {SELECAO_CSV} não encontrado -- pulando seleção.")
        return
    df = pd.read_csv(SELECAO_CSV, usecols=["date", "home_team", "away_team", "home_elo_pre", "away_elo_pre"])
    out = _monthly_long(df)
    OUT_SELECAO.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_SELECAO, index=False)
    print(f"[selecao] {len(out)} pontos ({out['team'].nunique()} times) -> {OUT_SELECAO}")


def build_clube() -> None:
    if not CLUBE_PARQUET.exists():
        print(f"[AVISO] {CLUBE_PARQUET} não encontrado -- pulando clube.")
        return
    # build_clubs_dataset.py grava times como "Nome#id" (chave interna de coleta) --
    # reaproveita a MESMA desambiguação de build_clubs_production_artifacts.py pra
    # que os nomes batam exatamente com os servidos pelo predictor de clube.
    from scripts.build_clubs_production_artifacts import disambiguate_collisions

    cols = ["date", "home_team", "away_team", "home_team_id", "away_team_id", "tournament", "home_elo_pre", "away_elo_pre"]
    df = pd.read_parquet(CLUBE_PARQUET, columns=cols)
    _, df = disambiguate_collisions(df)
    out = _monthly_long(df)
    OUT_CLUBE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CLUBE, index=False)
    print(f"[clube] {len(out)} pontos ({out['team'].nunique()} times) -> {OUT_CLUBE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube", "all"], default="all")
    a = ap.parse_args()
    if a.scope in ("selecao", "all"):
        build_selecao()
    if a.scope in ("clube", "all"):
        build_clube()


if __name__ == "__main__":
    main()
