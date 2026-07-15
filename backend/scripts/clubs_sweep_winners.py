#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_sweep_winners.py
================================
Fase 6.1+6.2 do plano: sweep de hiperparâmetros dos MELHORES candidatos da Fase 1
(CatBoost+pi-ratings foi o melhor da Linha B) e dos parâmetros dos próprios ratings
(λ/γ do pi-rating, α/β/ω do Berrar). Resumível (grava incrementalmente).

Uso: python scripts/clubs_sweep_winners.py [--stage catboost|ratings|all]
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

from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy)
from research_clubs.ratings import compute_pi_ratings, compute_berrar_ratings

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_DIR = ROOT / "data" / "reports" / "clubs_sweep"
Y_MAP = {"H": 0, "D": 1, "A": 2}
ELO_FEATS = ["home_elo_pre", "away_elo_pre", "elo_diff", "elo_home_winprob"]
PI_FEATS = ["pi_home_h", "pi_home_a", "pi_away_h", "pi_away_a",
            "pi_home_mean", "pi_away_mean", "pi_exp_gd"]


def load_df():
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    return df.sort_values("date").reset_index(drop=True)


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def sweep_catboost(df):
    from catboost import CatBoostClassifier
    out_csv = OUT_DIR / "catboost_sweep.csv"
    done = set()
    rows = []
    if out_csv.exists():
        prev = pd.read_csv(out_csv)
        done = set(zip(prev["depth"], prev["iterations"], prev["l2_leaf_reg"], prev["fold"]))
        rows = prev.to_dict("records")

    df2 = df.sort_values("date").reset_index(drop=True)
    pi = compute_pi_ratings(df2)
    df2 = pd.concat([df2, pi], axis=1)
    feats = PI_FEATS + ELO_FEATS
    y_map = Y_MAP

    grid = list(itertools.product([4, 6, 8, 10], [400, 800, 1200], [1.0, 3.0, 8.0]))
    print(f"{len(grid)} combos x 5 folds = {len(grid)*5} fits")
    for depth, iters, l2 in grid:
        for fold, tr_idx, te_idx in temporal_folds(df2):
            key = (depth, iters, l2, fold)
            if key in done:
                continue
            tr, te = df2.loc[tr_idx], df2.loc[te_idx]
            X_tr = tr[feats].to_numpy(dtype=float)
            X_te = te[feats].to_numpy(dtype=float)
            y_tr = tr["result"].map(y_map).to_numpy()
            y_te = te["result"].map(y_map).to_numpy()
            t0 = time.time()
            m = CatBoostClassifier(loss_function="MultiClass", depth=depth, iterations=iters,
                                   learning_rate=0.03, l2_leaf_reg=l2, random_seed=42,
                                   verbose=0, allow_writing_files=False, thread_count=-1)
            m.fit(X_tr, y_tr)
            probs = m.predict_proba(X_te)
            met = metrics(y_te, probs)
            row = {"depth": depth, "iterations": iters, "l2_leaf_reg": l2, "fold": fold,
                  "n": len(te), "fit_s": time.time() - t0, **met}
            rows.append(row)
            pd.DataFrame(rows).to_csv(out_csv, index=False)
            print(f"  depth={depth} iters={iters} l2={l2} {fold}: ll={met['logloss']:.4f} "
                  f"({row['fit_s']:.0f}s)", flush=True)

    res = pd.read_csv(out_csv)
    summ = res.groupby(["depth", "iterations", "l2_leaf_reg"])[["logloss", "rps", "ece"]] \
        .mean().sort_values("logloss")
    print("\n===== TOP 10 CatBoost sweep =====")
    print(summ.head(10).to_string())
    print(f"\nreferência Fase 1 B1_cat_pi (depth=6,iter=800,lr=0.03,l2=3): ll=0.9985")


def sweep_ratings(df):
    out_csv = OUT_DIR / "ratings_sweep.csv"
    done = set()
    rows = []
    if out_csv.exists():
        prev = pd.read_csv(out_csv)
        done = set(zip(prev["lam"], prev["gamma"], prev["fold"]))
        rows = prev.to_dict("records")

    from sklearn.linear_model import LogisticRegression
    df2 = df.sort_values("date").reset_index(drop=True)
    grid = list(itertools.product([0.01, 0.02, 0.035, 0.05, 0.08], [0.3, 0.5, 0.7, 0.9]))
    print(f"{len(grid)} combos pi-rating x 5 folds = {len(grid)*5} fits (ordered-logit, rápido)")
    for lam, gamma in grid:
        pi = compute_pi_ratings(df2, lam=lam, gamma=gamma)
        d = pd.concat([df2, pi], axis=1)
        for fold, tr_idx, te_idx in temporal_folds(d):
            key = (lam, gamma, fold)
            if key in done:
                continue
            tr, te = d.loc[tr_idx], d.loc[te_idx]
            ord_map = {"A": 0, "D": 1, "H": 2}
            y_tr = tr["result"].map(ord_map).to_numpy()
            X_tr = tr[PI_FEATS].to_numpy(dtype=float)
            X_te = te[PI_FEATS].to_numpy(dtype=float)
            p1 = LogisticRegression(max_iter=500).fit(X_tr, (y_tr >= 1).astype(int)).predict_proba(X_te)[:, 1]
            p2 = LogisticRegression(max_iter=500).fit(X_tr, (y_tr >= 2).astype(int)).predict_proba(X_te)[:, 1]
            p2 = np.minimum(p1, p2)
            probs = np.stack([p2, p1 - p2, 1 - p1], axis=1)  # H,D,A
            probs = np.clip(probs, 1e-9, 1); probs /= probs.sum(axis=1, keepdims=True)
            y_te = te["result"].map(Y_MAP).to_numpy()
            met = metrics(y_te, probs)
            row = {"lam": lam, "gamma": gamma, "fold": fold, "n": len(te), **met}
            rows.append(row)
            pd.DataFrame(rows).to_csv(out_csv, index=False)
        print(f"  lam={lam} gamma={gamma} concluído", flush=True)

    res = pd.read_csv(out_csv)
    summ = res.groupby(["lam", "gamma"])[["logloss", "rps"]].mean().sort_values("logloss")
    print("\n===== TOP pi-rating params (via ordered-logit proxy) =====")
    print(summ.head(10).to_string())
    print("referência produção pi-ratings (lam=0.035, gamma=0.7)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["catboost", "ratings", "all"], default="all")
    a = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_df()
    print(f"dataset: {len(df)} jogos")
    if a.stage in ("catboost", "all"):
        sweep_catboost(df)
    if a.stage in ("ratings", "all"):
        sweep_ratings(df)


if __name__ == "__main__":
    main()
