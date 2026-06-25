#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/feat_importance_diag.py
===============================
Diagnóstico: as variáveis importantes para RESULTADO mudam entre o regime de
história completa (Braço A) e o de só 2016+ (Braço B)? Testa diretamente a
hipótese de que um modelo 2016-only escolheria features diferentes.

Importância por permutação (neg_log_loss) no test-fold temporal, RandomForest
multi-core. Mesmo split/test para os dois braços.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
BASE = META["base_feats"]
ARMS = {
    "A (completa)": "international_features_enriched_apifootball.csv",
    "B (so 2016+)": "scratch/experimento_historico/dataset_2016.csv",
}


def rank(csv):
    df = pd.read_csv(csv, parse_dates=["date"], low_memory=False).sort_values("date").reset_index(drop=True)
    cut = df.iloc[int(len(df) * 0.8)]["date"]
    tr, te = df[df["date"] <= cut], df[df["date"] > cut]
    pipe = Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("rf", RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42))])
    pipe.fit(tr[BASE], tr["result"])
    r = permutation_importance(pipe, te[BASE], te["result"], scoring="neg_log_loss",
                               n_repeats=8, random_state=42, n_jobs=-1)
    imp = pd.Series(r.importances_mean, index=BASE).sort_values(ascending=False)
    return imp


def main():
    ranks = {name: rank(csv) for name, csv in ARMS.items()}
    names = list(ranks.keys())
    print(f"\n{'#':>2}  {names[0]:<32}{names[1]:<32}")
    print("-" * 66)
    for i in range(15):
        a = ranks[names[0]].index[i]
        b = ranks[names[1]].index[i]
        print(f"{i+1:>2}  {a:<32}{b:<32}")

    # quanto o ranking muda no topo?
    topA = list(ranks[names[0]].index[:15])
    topB = list(ranks[names[1]].index[:15])
    overlap = len(set(topA) & set(topB))
    print(f"\nSobreposicao do top-15: {overlap}/15")
    print(f"Top-3 A: {topA[:3]}")
    print(f"Top-3 B: {topB[:3]}")


if __name__ == "__main__":
    main()
