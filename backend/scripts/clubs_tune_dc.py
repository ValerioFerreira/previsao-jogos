#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_tune_dc.py
=========================
Fase 2.5 do plano de pesquisa de clubes: grid de hiperparâmetros do GBM que estima
λ/μ no DixonColesNBRegressor (a mesma classe de produção, dixon_coles_model.py),
agora sobre os 158 base_feats do dataset de CLUBES. Responde: "clubes têm 5-9× mais
dados — um GBM mais profundo/com mais árvores passa a valer, ou o grid atual
(n_estimators=100, depth=3, lr=0.05) já está no ponto certo mesmo com mais dados?"

Sob o protocolo único (5 folds temporais). Resumível (grava incrementalmente).

Uso: python scripts/clubs_tune_dc.py [--folds -2]   # -2 = só os 2 últimos folds (mais rápido)
"""
import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy)
import json

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_CSV = ROOT / "data" / "reports" / "clubs_dc_tuning.csv"
META = ROOT / "model_artifacts" / "meta.json"

GRID = {
    "n_estimators": [100, 200, 300],
    "max_depth": [3, 4, 5],
    "learning_rate": [0.05, 0.03],
}
# produção = (100, 3, 0.05) — inclusa no grid para comparação direta


def result_probs(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]  # [A,D,H] -> [H,D,A]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=0, help="0=todos; N negativo=só os últimos N")
    a = ap.parse_args()

    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    df = df.reset_index(drop=True)
    print(f"dataset: {len(df)} jogos")

    folds = list(temporal_folds(df))
    if a.folds < 0:
        folds = folds[a.folds:]
    y_map = {"H": 0, "D": 1, "A": 2}

    done = set()
    if OUT_CSV.exists():
        prev = pd.read_csv(OUT_CSV)
        done = set(zip(prev["n_estimators"], prev["max_depth"], prev["learning_rate"], prev["fold"]))
        rows = prev.to_dict("records")
    else:
        rows = []

    combos = list(itertools.product(GRID["n_estimators"], GRID["max_depth"], GRID["learning_rate"]))
    print(f"{len(combos)} combos x {len(folds)} folds = {len(combos)*len(folds)} fits")

    for n_est, depth, lr in combos:
        for fold, tr_idx, te_idx in folds:
            key = (n_est, depth, lr, fold)
            if key in done:
                continue
            tr, te = df.loc[tr_idx], df.loc[te_idx]
            X_tr = tr[bf].fillna(tr[bf].median(numeric_only=True))
            X_te = te[bf].fillna(tr[bf].median(numeric_only=True))
            t0 = time.time()
            m = DixonColesNBRegressor(n_estimators=n_est, max_depth=depth,
                                      learning_rate=lr, max_goals=12, random_state=42)
            m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
            probs = result_probs(m, X_te)
            y_idx = te["result"].map(y_map).to_numpy()
            row = {
                "n_estimators": n_est, "max_depth": depth, "learning_rate": lr, "fold": fold,
                "n": len(te), "logloss": multiclass_logloss(y_idx, probs),
                "rps": rps_hda(y_idx, probs), "ece": ece_multiclass(y_idx, probs),
                "accuracy": accuracy(y_idx, probs), "fit_s": time.time() - t0,
            }
            rows.append(row)
            pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
            print(f"  n_est={n_est} depth={depth} lr={lr} {fold}: "
                  f"ll={row['logloss']:.4f} rps={row['rps']:.4f} ({row['fit_s']:.0f}s)", flush=True)

    res = pd.read_csv(OUT_CSV)
    summ = res.groupby(["n_estimators", "max_depth", "learning_rate"])[
        ["logloss", "rps", "ece", "accuracy"]].mean().sort_values("logloss")
    print("\n===== RANKING (média dos folds disponíveis) =====")
    print(summ.to_string())
    print(f"\nProdução atual = n_estimators=100, max_depth=3, learning_rate=0.05")


if __name__ == "__main__":
    main()
