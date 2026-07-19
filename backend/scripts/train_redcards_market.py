#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_redcards_market.py
=================================
Mercado novo: cartões VERMELHOS isolados (hoje "cartoes" soma amarelo+vermelho).
Mesma arquitetura da cascata de escanteios/impedimentos (CornersNB sobre base_feats),
alvo = home_cur_sb_red/away_cur_sb_red (já extraído no box-score, ambos os escopos).
Raro (media ~0.10-0.13/time/jogo) -> grade pequena (max_corners=4).

Uso: python scripts/train_redcards_market.py --scope selecao
     python scripts/train_redcards_market.py --scope clube
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

    if cfg["csv"].suffix == ".csv":
        df = pd.read_csv(cfg["csv"], low_memory=False)
    else:
        df = pd.read_parquet(cfg["csv"])
    meta = json.load(open(cfg["art"] / "meta.json", encoding="utf-8"))
    base_feats = meta["base_feats"]

    d = df.dropna(subset=["home_cur_sb_red", "away_cur_sb_red"]).copy()
    yh = d["home_cur_sb_red"].astype(int).clip(0, 4).values
    ya = d["away_cur_sb_red"].astype(int).clip(0, 4).values
    print(f"[{a.scope}] N={len(d)} | media real mand {yh.mean():.3f} vis {ya.mean():.3f} total {(yh+ya).mean():.3f}", flush=True)

    m = CornersNB(feats=base_feats, max_corners=4)
    X = d[base_feats].fillna(d[base_feats].median(numeric_only=True))
    m.fit(X, yh, ya)
    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.3f} vis {(dist['away']@ks).mean():.3f} "
          f"total {(dist['total']@kt).mean():.3f} (sanidade in-sample)", flush=True)

    out = cfg["art"] / "cartoes_vermelhos_nb.joblib"
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
