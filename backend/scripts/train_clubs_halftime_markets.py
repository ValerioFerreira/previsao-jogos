#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_clubs_halftime_markets.py
========================================
Equivalente a train_halftime_markets.py, pra CLUBES -- fecha o gap documentado em
build_clubs_production_artifacts.py ("por-tempo precisam virar opcionais... antes
de rodar este script" -- na verdade predictor.py JÁ tolera ausência via
`os.path.exists`, então só falta treinar e salvar os 4 artefatos).

Junta club_features_enriched.parquet (base_feats) com club_halftime_targets.parquet
por fixture_id (build_clubs_halftime_targets.py), treina CornersNB (mesma classe/
arquitetura da cascata de escanteios) pros 4 mercados por tempo, salva em
model_artifacts_clubes/. NÃO toca os artefatos de seleção.

Uso: python scripts/train_clubs_halftime_markets.py
"""
import sys
import json
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

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
TARGETS = ROOT / "data" / "built" / "club_halftime_targets.parquet"
ART = ROOT / "model_artifacts_clubes"
META = json.load(open(ART / "meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]

MARKETS = [
    ("gols_1t", "home_goals_1t", "away_goals_1t", False, 12),
    ("gols_2t", "home_goals_2t", "away_goals_2t", False, 12),
    ("cartoes_1t", "home_cards_1t", "away_cards_1t", True, 15),
    ("cartoes_2t", "home_cards_2t", "away_cards_2t", True, 15),
]


def main():
    df = pd.read_parquet(FEATURES)
    tgt = pd.read_parquet(TARGETS)
    d0 = df.merge(tgt, on="fixture_id", how="inner")
    print(f"Base casada: {len(d0)} jogos (de {len(df)} no dataset / {len(tgt)} com alvo por tempo)")

    for name, th, ta, need_cards, grade in MARKETS:
        d = d0.dropna(subset=[th, ta]).copy()
        if need_cards:
            d = d[d["has_card_events"] == 1]
        yh = d[th].astype(int).values
        ya = d[ta].astype(int).values
        print(f"\n>> {name}: N={len(d)} | media real mand {yh.mean():.2f} vis {ya.mean():.2f} total {(yh+ya).mean():.2f}")
        m = CornersNB(feats=BASE_FEATS, max_corners=grade)
        m.fit(d[BASE_FEATS].fillna(d[BASE_FEATS].median(numeric_only=True)), yh, ya)
        dist = m.predict_distributions(d[BASE_FEATS].fillna(d[BASE_FEATS].median(numeric_only=True)))
        ks = np.arange(m.max_corners + 1)
        kt = np.arange(2 * m.max_corners + 1)
        print(f"   E[PMF] mand {(dist['home']@ks).mean():.2f} vis {(dist['away']@ks).mean():.2f} "
              f"total {(dist['total']@kt).mean():.2f} (sanidade in-sample)")
        out = ART / f"{name}_nb.joblib"
        m.save(str(out))
        print(f"   salvo: {out}")


if __name__ == "__main__":
    main()
