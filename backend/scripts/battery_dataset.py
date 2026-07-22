#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/battery_dataset.py
===========================
Dataset compartilhado da bateria de hipoteses 2026-07-21 (baseline/H1/H2/H4).
Reaproveita EXATAMENTE a pipeline de features de `build_clubs_production_artifacts.py`
(disambiguate_collisions + GAP ratings) para nao divergir da producao real.

GAP ratings sao causais/incrementais (o valor pre-jogo de uma linha so depende de
linhas ANTERIORES na mesma ordem cronologica) -- por isso e seguro computa-los UMA
VEZ sobre o dataset inteiro ordenado por data e so entao fatiar train/test por fold:
da o MESMO valor que recomputar por fold (nenhum vazamento), e evita recalcular a
cada seed/fold (custo materializado uma vez).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_clubs.ratings import compute_gap_ratings

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
SELECAO_META = ROOT / "model_artifacts" / "meta.json"

DC_PARAMS = dict(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)

GAP_RATINGS_FEATS = [
    "gap_shots_home_att", "gap_shots_home_def", "gap_shots_away_att", "gap_shots_away_def",
    "gap_shots_exp_home", "gap_shots_exp_away",
    "gap_corners_home_att", "gap_corners_home_def", "gap_corners_away_att", "gap_corners_away_def",
    "gap_corners_exp_home", "gap_corners_exp_away",
]

_HASH_ID_RE = re.compile(r"#\d+$")


def disambiguate_collisions(df):
    """Copia de build_clubs_production_artifacts.py::disambiguate_collisions
    (nao importada direto para nao depender de import pesado do script inteiro)."""
    clean_home = df["home_team"].str.replace(_HASH_ID_RE, "", regex=True)
    clean_away = df["away_team"].str.replace(_HASH_ID_RE, "", regex=True)
    long = pd.concat([
        pd.DataFrame({"team": clean_home, "team_id": df["home_team_id"], "tournament": df["tournament"]}),
        pd.DataFrame({"team": clean_away, "team_id": df["away_team_id"], "tournament": df["tournament"]}),
    ], ignore_index=True)
    n_ids = long.groupby("team")["team_id"].nunique()
    colliding = set(n_ids[n_ids > 1].index)
    tag = (long.groupby(["team", "team_id"])["tournament"]
           .agg(lambda s: s.value_counts().idxmax()))
    rename = {(team, tid): (f"{team} ({liga})" if team in colliding else team)
              for (team, tid), liga in tag.items()}
    df = df.copy()
    df["home_team"] = [rename.get((t, i), t) for t, i in zip(clean_home, df["home_team_id"])]
    df["away_team"] = [rename.get((t, i), t) for t, i in zip(clean_away, df["away_team_id"])]
    return df


_CACHE: dict[str, pd.DataFrame] = {}


def load_clubs_df(min_matches: int = 5) -> pd.DataFrame:
    """Base de clubes completa, ordenada por data, com colisoes desambiguadas e
    GAP ratings (158 feats de producao + 12 gap = 170) anexados. Filtra jogos com
    <5 jogos anteriores de cada time (mesmo corte de `clubs_value_backtest.py`
    -- exclui o "cold start" de times recem-entrados no dataset)."""
    key = f"m{min_matches}"
    if key in _CACHE:
        return _CACHE[key].copy()

    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = disambiguate_collisions(df)

    gap_shots_df, _ = compute_gap_ratings(
        df, "home_cur_sb_shots", "away_cur_sb_shots", prefix="gap_shots", return_state=True)
    gap_corners_df, _ = compute_gap_ratings(
        df, "home_cur_sb_corners", "away_cur_sb_corners", prefix="gap_corners", return_state=True)
    df = pd.concat([df, gap_shots_df, gap_corners_df], axis=1)

    df = df[(df["home_matches_played_before"] >= min_matches) &
            (df["away_matches_played_before"] >= min_matches)].reset_index(drop=True)

    _CACHE[key] = df
    return df.copy()


def base_feats_158() -> list[str]:
    return json.load(open(SELECAO_META, encoding="utf-8"))["base_feats"]


def base_feats_170() -> list[str]:
    return base_feats_158() + GAP_RATINGS_FEATS


def xg_feature_cols() -> list[str]:
    """Features de xG ja presentes no dataset enriquecido (rolling l5/l10 +
    diferenca), point-in-time (shift(1) ja aplicado na pipeline de build).
    Ver H4 -- usadas so como ablacao, nao entram no base_feats de producao."""
    return ["home_sb_xg_l5", "home_sb_xg_l10", "away_sb_xg_l5", "away_sb_xg_l10",
            "diff_sb_xg_l5", "diff_sb_xg_l10"]
