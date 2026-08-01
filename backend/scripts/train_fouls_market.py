#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_fouls_market.py
==============================
Mercado novo: FALTAS (mandante/visitante/total) -- Grupo 1 custo A do
docs/PLANO_EXPANSAO_MERCADOS.md (`home/away_cur_sb_fouls` ja e coluna pronta,
sem custo de coleta). Mesma arquitetura da cascata de escanteios/cartoes
(CornersNB sobre base_feats), alvo = home_cur_sb_fouls/away_cur_sb_fouls.

Cru ate passar por gate_count_market.py --market faltas -- este script so
treina e salva, nao promove.

Uso: python -m scripts.train_fouls_market --scope clube
     python -m scripts.train_fouls_market --scope selecao
"""
import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB  # noqa: E402
from scripts.battery_dataset import load_clubs_df  # noqa: E402

CONFIG = {
    "selecao": {
        "csv": ROOT / "international_features_enriched_apifootball.csv",
        "art": ROOT / "model_artifacts",
    },
    "clube": {
        "csv": ROOT / "data" / "built" / "club_features_enriched.parquet",
        "art": ROOT / "model_artifacts_clubes",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    meta = json.load(open(cfg["art"] / "meta.json", encoding="utf-8"))
    base_feats = meta["base_feats"]

    if a.scope == "clube":
        df = load_clubs_df(min_matches=0)
    else:
        df = pd.read_csv(cfg["csv"], low_memory=False)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    base_feats = [f for f in base_feats if f in df.columns]

    d = df.dropna(subset=["home_cur_sb_fouls", "away_cur_sb_fouls"]).copy()
    yh = d["home_cur_sb_fouls"].astype(int).clip(0, 22).values
    ya = d["away_cur_sb_fouls"].astype(int).clip(0, 22).values
    print(f"[{a.scope}] N={len(d)} | media real mand {yh.mean():.3f} vis {ya.mean():.3f} total {(yh+ya).mean():.3f}", flush=True)

    m = CornersNB(feats=base_feats, max_corners=22)
    X = d[base_feats].fillna(d[base_feats].median(numeric_only=True))
    m.fit(X, yh, ya)
    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.3f} vis {(dist['away']@ks).mean():.3f} "
          f"total {(dist['total']@kt).mean():.3f} (sanidade in-sample)", flush=True)

    out = cfg["art"] / "fouls_nb.joblib"
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
