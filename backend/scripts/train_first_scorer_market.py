#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_first_scorer_market.py
=====================================
Mercado novo: TIME A MARCAR PRIMEIRO -- P(mandante marca primeiro / visitante marca
primeiro / nenhum gol). Classificador multinomial simples (HistGradientBoosting)
sobre base_feats + alvo de build_first_scorer_targets.py. Salvo como sklearn Pipeline
puro (imputer+classificador) -- predictor.py chama .predict_proba diretamente.

Uso: python scripts/train_first_scorer_market.py --scope selecao
     python scripts/train_first_scorer_market.py --scope clube
"""
import sys
import json
import argparse
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONFIG = {
    "selecao": {
        "csv": ROOT / "international_features_enriched_apifootball.csv",
        "targets": ROOT / "data" / "built" / "first_scorer_targets.parquet",
        "art": ROOT / "model_artifacts",
    },
    "clube": {
        "csv": ROOT / "data" / "built" / "club_features_enriched.parquet",
        "targets": ROOT / "data" / "built" / "club_first_scorer_targets.parquet",
        "art": ROOT / "model_artifacts_clubes",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    if cfg["csv"].suffix == ".csv":
        df = pd.read_csv(cfg["csv"], low_memory=False)
    else:
        df = pd.read_parquet(cfg["csv"])
    tgt = pd.read_parquet(cfg["targets"])
    meta = json.load(open(cfg["art"] / "meta.json", encoding="utf-8"))
    base_feats = meta["base_feats"]

    if "fixture_id" in df.columns:
        d = df.merge(tgt, on="fixture_id", how="inner")
    else:
        df["dkey"] = df["date"].astype(str).str[:10]
        d = df.merge(tgt, left_on=["dkey", "home_team", "away_team"],
                    right_on=["date", "home_team", "away_team"], how="inner", suffixes=("", "_t"))
    print(f"[{a.scope}] base casada: {len(d)} jogos", flush=True)
    print(d["first_scorer"].value_counts(), flush=True)

    X = d[base_feats]
    y = d["first_scorer"].to_numpy()

    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05,
                                               max_iter=200, random_state=42)),
    ])
    pipe.fit(X, y)
    print(f"  classes: {pipe.named_steps['clf'].classes_}", flush=True)
    p = pipe.predict_proba(X)
    print(f"  media in-sample: {dict(zip(pipe.named_steps['clf'].classes_, p.mean(axis=0).round(3)))}", flush=True)

    out = cfg["art"] / "first_scorer_clf.joblib"
    joblib.dump({"pipe": pipe, "feats": base_feats}, out)
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
