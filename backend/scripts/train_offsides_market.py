#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_offsides_market.py
=================================
Fecha a assimetria do Grupo 5 (docs/PLANO_EXPANSAO_MERCADOS.md): impedimentos ja
esta em producao pra selecao mas `offsides_nb.joblib` NUNCA foi treinado pra
clube (predictor.py ja tolera ausencia via os.path.exists). Mesma arquitetura
da cascata de escanteios/cartoes (CornersNB sobre base_feats), alvo =
home_cur_sb_offsides/away_cur_sb_offsides.

NAO sobrescreve o artefato de selecao ja em producao sem passar pelo gate
primeiro -- rode --scope clube por padrao; --scope selecao existe só para
auditoria futura via gate_count_market.py, nao para promover cru.

Uso: python -m scripts.train_offsides_market --scope clube
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
        # load_clubs_df ja desambigua colisao de nome de time e anexa GAP
        # ratings (§17) -- compute_gap_ratings e keyed por nome de time, entao
        # sem desambiguar dois times homonimos de ligas diferentes
        # contaminariam o rating um do outro.
        df = load_clubs_df(min_matches=0)
    else:
        df = pd.read_csv(cfg["csv"], low_memory=False)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    base_feats = [f for f in base_feats if f in df.columns]

    d = df.dropna(subset=["home_cur_sb_offsides", "away_cur_sb_offsides"]).copy()
    yh = d["home_cur_sb_offsides"].astype(int).clip(0, 10).values
    ya = d["away_cur_sb_offsides"].astype(int).clip(0, 10).values
    print(f"[{a.scope}] N={len(d)} | media real mand {yh.mean():.3f} vis {ya.mean():.3f} total {(yh+ya).mean():.3f}", flush=True)

    m = CornersNB(feats=base_feats, max_corners=10)
    X = d[base_feats].fillna(d[base_feats].median(numeric_only=True))
    m.fit(X, yh, ya)
    dist = m.predict_distributions(X)
    ks = np.arange(m.max_corners + 1)
    kt = np.arange(2 * m.max_corners + 1)
    print(f"  E[PMF] mand {(dist['home']@ks).mean():.3f} vis {(dist['away']@ks).mean():.3f} "
          f"total {(dist['total']@kt).mean():.3f} (sanidade in-sample)", flush=True)

    out = cfg["art"] / "offsides_nb.joblib"
    if out.exists():
        print(f"  AVISO: {out} ja existe -- sobrescrevendo (rode gate_count_market.py depois pra validar antes de considerar promovido)", flush=True)
    m.save(str(out))
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
