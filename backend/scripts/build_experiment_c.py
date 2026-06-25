#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_experiment_c.py
=============================
BRAÇO C — dataset 2016+ construído DE PROPÓSITO para cold-start: Elo com K
provisional (mais alto nos primeiros N jogos de cada seleção, decaindo), para
convergir rápido a partir do 1500. Tudo o mais idêntico ao Braço B.

Objetivo: separar a "penalidade de design" (corrigível) da "penalidade de dados"
(irredutível). Se C fecha o gap até o Braço A, o problema era design; se C fica
perto do B, o problema é falta de dado histórico.

Parâmetros do provisional escolhidos A PRIORI (não tunados no teste):
    N_PROV=25 jogos, MULT=3.0 (K inicial 3x, decai linear até 1x no jogo 25).

Saída: scratch/experimento_historico/dataset_2016_c.csv
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import build_final_dataset as bfd

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT = Path("scratch/experimento_historico/dataset_2016_c.csv")
WARMUP_FROM = 2016
N_PROV = 25
MULT = 3.0


def compute_elo_provisional(df, n_prov=N_PROV, mult=MULT):
    """Igual ao compute_elo de produção, mas com K provisional por contagem de jogos."""
    ratings, games = {}, {}
    home_elos, away_elos = [], []
    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        ra = ratings.get(ht, bfd.ELO_START)
        rb = ratings.get(at, bfd.ELO_START)
        home_elos.append(ra)
        away_elos.append(rb)

        base_k = bfd.get_base_k(row["tournament"])
        neutral = bool(row.get("neutral", 0))
        h = 0.0 if neutral else bfd.HOME_ADV_ELO
        we_home = 1.0 / (1.0 + 10.0 ** ((rb - (ra + h)) / 400.0))
        hs, ag = row["home_score"], row["away_score"]
        s_home = 1.0 if hs > ag else (0.0 if hs < ag else 0.5)
        gd = abs(hs - ag)
        mg = 1.0 if gd <= 1 else (1.5 if gd == 2 else (1.75 if gd == 3 else 1.75 + (gd - 3) / 8.0))

        gh, ga_ = games.get(ht, 0), games.get(at, 0)
        kh = base_k * (1.0 + (mult - 1.0) * max(0.0, (n_prov - gh) / n_prov))
        ka = base_k * (1.0 + (mult - 1.0) * max(0.0, (n_prov - ga_) / n_prov))

        ratings[ht] = ra + kh * mg * (s_home - we_home)
        ratings[at] = rb + ka * mg * ((1.0 - s_home) - (1.0 - we_home))
        games[ht] = gh + 1
        games[at] = ga_ + 1
    return home_elos, away_elos


def main():
    print("=" * 78)
    print(f" BRAÇO C — 2016+ com Elo provisional (N_PROV={N_PROV}, MULT={MULT})")
    print("=" * 78)
    df, shootouts = bfd.load_base_data()
    df = df[df["date"].dt.year >= WARMUP_FROM].reset_index(drop=True)
    shootouts = shootouts[shootouts["date"].dt.year >= WARMUP_FROM].reset_index(drop=True)
    print(f"[1/7] martj42 >=2016: {len(df)} partidas")

    ti = df["tournament"].apply(bfd.classify_tournament)
    df["tournament_weight"] = [t["weight"] for t in ti]
    df["is_friendly"] = [t["is_friendly"] for t in ti]
    df["is_qualification"] = [t["is_qualification"] for t in ti]
    df["is_major_final"] = [t["is_major_final"] for t in ti]
    df["is_competitive"] = [t["is_competitive"] for t in ti]
    df["real_home_advantage"] = (1 - df["neutral"].fillna(0).astype(int))
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["decade"] = (df["year"] // 10) * 10
    df["goal_diff"] = df["home_score"] - df["away_score"]
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["result"] = df["goal_diff"].apply(lambda x: "H" if x > 0 else ("A" if x < 0 else "D"))
    df["home_win"] = (df["goal_diff"] > 0).astype(int)
    df["away_win"] = (df["goal_diff"] < 0).astype(int)
    df["draw"] = (df["goal_diff"] == 0).astype(int)
    df["btts"] = ((df["home_score"] > 0) & (df["away_score"] > 0)).astype(int)
    df["over_2_5"] = (df["total_goals"] >= 3).astype(int)
    print("[2/7] contexto + alvos OK")

    he, ae = compute_elo_provisional(df)
    df["home_elo_pre"] = he
    df["away_elo_pre"] = ae
    df["elo_diff"] = df["home_elo_pre"] - df["away_elo_pre"]
    neutral_arr = df["neutral"].fillna(0).astype(bool).values
    h_arr = np.where(neutral_arr, 0.0, bfd.HOME_ADV_ELO)
    df["elo_home_winprob"] = 1.0 / (1.0 + 10.0 ** (
        (df["away_elo_pre"].values - (df["home_elo_pre"].values + h_arr)) / 400.0))
    print("[3/7] Elo PROVISIONAL OK")

    gamelog = bfd.build_gamelog(df, shootouts)
    form_df = bfd.compute_form_features(gamelog)
    feat_cols = [c for c in form_df.columns if c not in ["team", "match_idx"]]
    home_form = (form_df.merge(df[["match_id", "home_team"]],
                               left_on=["match_idx", "team"], right_on=["match_id", "home_team"],
                               how="inner")[feat_cols + ["match_id"]]
                 .rename(columns={c: f"home_{c}" for c in feat_cols}))
    away_form = (form_df.merge(df[["match_id", "away_team"]],
                               left_on=["match_idx", "team"], right_on=["match_id", "away_team"],
                               how="inner")[feat_cols + ["match_id"]]
                 .rename(columns={c: f"away_{c}" for c in feat_cols}))
    df = df.merge(home_form, on="match_id", how="left").merge(away_form, on="match_id", how="left")
    print("[4/7] forma OK")

    h2h_played, h2h_home_wr, h2h_home_gd, days_h2h = bfd.compute_h2h(df)
    df["h2h_played"] = h2h_played
    df["h2h_home_winrate"] = h2h_home_wr
    df["h2h_home_gd_mean"] = h2h_home_gd
    df["days_since_last_h2h"] = days_h2h
    print("[5/7] H2H OK")

    DIFF_BASES = ["matches_played_before", "days_rest"] + \
        [f"{m}_l{w}" for m in ["gf", "ga", "gd", "ppg", "winrate", "drawrate",
                               "lossrate", "csrate", "ftsrate", "bttsrate", "pensfor"]
         for w in bfd.WINDOWS] + \
        ["win_streak", "unbeaten_streak", "winless_streak", "scoring_streak", "shootout_winrate_pre"]
    for b in DIFF_BASES:
        hc, ac = f"home_{b}", f"away_{b}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{b}"] = df[hc] - df[ac]
    print("[6/7] diff OK")

    sb_df = bfd.compute_sb_features(bfd.STATS_CSV, df)
    if sb_df is not None:
        df = df.join(sb_df, how="left")
    else:
        df["has_advanced_stats"] = 0
    SB_FEAT_COLS = [f"{col}_{sfx}" for col in bfd.SB_COLS
                    for sfx in ["l3", "l5", "against_l3", "against_l5"]]
    for col in SB_FEAT_COLS:
        hc, ac = f"home_{col}", f"away_{col}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{col}"] = df[hc] - df[ac]
    n_adv = int(df.get("has_advanced_stats", pd.Series(0)).fillna(0).sum())
    print(f"[7/7] SB OK | stats avancadas: {n_adv}")

    df_out = df[df["year"] >= bfd.CUTOFF_YEAR].copy().reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(OUT, index=False)
    print(f"\n>> Braço C salvo: {OUT} | {len(df_out)} linhas | {df_out.shape[1]} colunas")


if __name__ == "__main__":
    main()
