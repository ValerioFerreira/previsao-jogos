#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_features_v2_ablation.py
=======================================
Fase 5 (final): monta o dataset v2 (club_features_enriched.parquet + os 7 grupos
de research_clubs/club_features.py) e testa cada grupo em ABLAÇÃO — sozinho sobre
o baseline vencedor da Fase 1 (DC-NB, 158 base_feats) — e depois a combinação de
todos os grupos que passarem.

Gate: log-loss melhora em >=4/5 folds sob o protocolo único = grupo promovido para
a combinação final.

Uso: python scripts/clubs_features_v2_ablation.py
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)
from research_clubs.club_features import build_all_groups

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
FEATURES_V2 = ROOT / "data" / "built" / "club_features_v2.parquet"
LINEUPS = ROOT / "data" / "built" / "club_lineups.parquet"
MATCHES_LONG = ROOT / "data" / "built" / "club_matches.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_features_v2"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def result_probs(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def run_dc(df, feats, name):
    out = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        y_idx = te["result"].map(Y_MAP).to_numpy()
        met = metrics(y_idx, result_probs(m, X_te))
        out.append(FoldResult(fold, len(te), met))
        print(f"  [{name}] {fold}: ll={met['logloss']:.4f} rps={met['rps']:.4f}", flush=True)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if FEATURES_V2.exists():
        print(f"[skip build] {FEATURES_V2} já existe — usando cache")
        df = pd.read_parquet(FEATURES_V2)
        df["date"] = pd.to_datetime(df["date"])
    else:
        df = pd.read_parquet(FEATURES)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        lineups = pd.read_parquet(LINEUPS)
        matches_long = pd.read_parquet(MATCHES_LONG)
        print(f"construindo grupos v2 sobre {len(df)} jogos...")
        groups = build_all_groups(df, lineups, matches_long)
        for name, g in groups.items():
            overlap = [c for c in g.columns if c in df.columns]
            if overlap:
                df = df.drop(columns=overlap)
            df = df.join(g)
        df.to_parquet(FEATURES_V2, index=False)
        print(f"salvo {FEATURES_V2}: {df.shape}")

    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].reset_index(drop=True)
    print(f"dataset pós burn-in: {len(df2)} jogos")

    GROUP_FEATS = {
        "congestion": ["home_games_l7", "away_games_l7", "diff_games_l7",
                      "home_games_l14", "away_games_l14", "diff_games_l14",
                      "home_games_l30", "away_games_l30", "diff_games_l30"],
        "altitude_travel": ["venue_altitude_m", "is_high_altitude",
                           "home_just_traveled", "away_just_traveled", "diff_just_traveled"],
        "phase": ["is_second_leg", "is_first_leg", "is_decision_game"],
        "squad_rotation": ["home_squad_rotation", "away_squad_rotation", "diff_squad_rotation"],
        "xg_overperf": ["home_g_minus_xg_l5", "away_g_minus_xg_l5", "diff_g_minus_xg_l5",
                        "home_g_minus_xg_l10", "away_g_minus_xg_l10", "diff_g_minus_xg_l10"],
        "gap_ratings": [c for c in df2.columns if c.startswith("gap_shots_") or c.startswith("gap_corners_")],
        "match_importance": ["home_table_pos", "home_pts_to_top4", "home_pts_to_relegation",
                            "away_table_pos", "away_pts_to_top4", "away_pts_to_relegation",
                            "diff_table_pos"],
    }

    base_feats = bf()
    print("\n=== baseline (158 base_feats) ===")
    baseline = run_dc(df2, base_feats, "baseline")

    passed = []
    for name, extra in GROUP_FEATS.items():
        extra = [f for f in extra if f in df2.columns]
        print(f"\n=== ablação: {name} ({len(extra)} features) ===")
        cand = run_dc(df2, base_feats + extra, name)
        comp = compare(baseline, cand, metric="logloss")
        comp.to_csv(OUT_DIR / f"{name}.csv", index=False)
        wins = comp.iloc[:-1]["melhora"].sum()
        delta = comp.iloc[-1]["delta"]
        veredito = "PASSA" if wins >= 4 and delta < -0.001 else ("misto" if wins >= 2 else "REPROVADO")
        print(f"  {name}: {wins}/5 folds melhoram | delta {delta:+.4f} -> {veredito}")
        if veredito == "PASSA":
            passed.append(name)

    print(f"\n===== grupos que PASSAM: {passed} =====")
    if passed:
        combo_feats = base_feats + [f for name in passed for f in GROUP_FEATS[name] if f in df2.columns]
        print(f"\n=== combinação final ({len(combo_feats)} features) ===")
        combo = run_dc(df2, combo_feats, "combo_v2")
        comp = compare(baseline, combo, metric="logloss")
        comp.to_csv(OUT_DIR / "_combo_final.csv", index=False)
        wins = comp.iloc[:-1]["melhora"].sum()
        delta = comp.iloc[-1]["delta"]
        print(f"  combo: {wins}/5 folds melhoram | delta {delta:+.4f}")
    else:
        print("nenhum grupo passou isoladamente — sem combinação a testar")


if __name__ == "__main__":
    main()
