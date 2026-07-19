#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp_gap_ratings_only.py
=======================================
Reroda SÓ o grupo gap_ratings (Fase 5.6) da bateria de ablação de
clubs_features_v2_ablation.py, isolado, contra o cache já construído
(data/built/club_features_v2.parquet) -- evita esperar a sequência completa
dos outros 6 grupos + combo do script monolítico rodando em paralelo.
Prioridade: gap_ratings passou 5/5 folds (delta -0,0022) no dataset de 13
competições/54k jogos (Fase 5, 2026-07-15) -- candidato mais forte a mudar
de veredito (pra melhor ou pior) com 3,4x mais dados (60 ligas/191k jogos).
"""
import sys
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)

FEATURES_V2 = ROOT / "data" / "built" / "club_features_v2.parquet"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "clubs_features_v2"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def result_probs(model, X):
    return model.predict_proba_markets(X)["result"][:, ::-1]


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
    df = pd.read_parquet(FEATURES_V2)
    df["date"] = pd.to_datetime(df["date"])
    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].reset_index(drop=True)
    print(f"dataset pos burn-in: {len(df2)} jogos", flush=True)

    gap_feats = [c for c in df2.columns if c.startswith("gap_shots_") or c.startswith("gap_corners_")]
    print(f"gap_ratings: {len(gap_feats)} features -> {gap_feats}", flush=True)

    base_feats = bf()
    print("\n=== baseline (158 base_feats) ===", flush=True)
    baseline = run_dc(df2, base_feats, "baseline")
    print("\n=== ablacao: gap_ratings ===", flush=True)
    cand = run_dc(df2, base_feats + gap_feats, "gap_ratings")
    comp = compare(baseline, cand, metric="logloss")
    comp.to_csv(OUT_DIR / "gap_ratings_solo.csv", index=False)
    wins = comp.iloc[:-1]["melhora"].sum()
    delta = comp.iloc[-1]["delta"]
    veredito = "PASSA" if wins >= 4 and delta < -0.001 else ("misto" if wins >= 2 else "REPROVADO")
    print(f"\ngap_ratings: {wins}/5 folds melhoram | delta {delta:+.4f} -> {veredito}")
    print(comp.to_string(index=False))


if __name__ == "__main__":
    main()
