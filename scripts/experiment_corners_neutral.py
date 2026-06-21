#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_corners_neutral.py
=====================================
Item 2 / Fase A — verifica com PODER se o residuo de escanteios em campo neutro e
real ou ruido de amostra pequena. Usa predicoes OUT-OF-FOLD (5-fold CV) sobre TODOS
os jogos com escanteios, entao agrupa residuos (real - lambda) por contexto de mando,
com media +/- SE e significancia (|media|/SE). Diagnostico; nao toca producao.
"""
import sys
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import KFold

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FEATS = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))["full_feats"]


def gbr():
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100,
                                                       max_depth=3, learning_rate=0.05, random_state=42))])


def oof_lambda(X, y):
    """lambda out-of-fold (5-fold) para cada jogo."""
    lam = np.zeros(len(y))
    for tr, te in KFold(n_splits=5, shuffle=True, random_state=42).split(X):
        m = gbr(); m.fit(X.iloc[tr], y[tr])
        lam[te] = np.maximum(m.predict(X.iloc[te]), 0.05)
    return lam


def report(name, resid, neutral, friendly):
    print(f"\n## {name}")
    print(f"  {'grupo':16s} {'n':>5} {'res medio':>10} {'SE':>7} {'sigma':>6}")
    for lab, mask in [("Neutro", neutral == 1), ("Nao-neutro", neutral == 0),
                      ("Amistoso", friendly == 1), ("Competitivo", friendly == 0)]:
        r = resid[mask]
        se = r.std() / np.sqrt(len(r))
        print(f"  {lab:16s} {len(r):5d} {r.mean():+10.3f} {se:7.3f} {abs(r.mean())/se:6.2f}")
    # diferenca neutro vs nao-neutro com erro combinado
    rn, rnn = resid[neutral == 1], resid[neutral == 0]
    diff = rn.mean() - rnn.mean()
    se_d = np.sqrt(rn.var() / len(rn) + rnn.var() / len(rnn))
    print(f"  >> diferenca Neutro - NaoNeutro: {diff:+.3f} (SE {se_d:.3f}, {abs(diff)/se_d:.2f} sigma)")


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_corners", "away_cur_sb_corners"]).reset_index(drop=True)
    print(f"N jogos com escanteios: {len(adv)} | neutros: {int((adv['neutral']==1).sum())}")
    X = adv[FEATS]
    neutral = adv["neutral"].fillna(0).astype(int).values
    friendly = adv["is_friendly"].fillna(0).astype(int).values
    for side in ["home", "away"]:
        y = adv[f"{side}_cur_sb_corners"].astype(float).values
        lam = oof_lambda(X, y)
        report(f"Escanteios {side}", y - lam, neutral, friendly)


if __name__ == "__main__":
    main()
