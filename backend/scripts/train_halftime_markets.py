#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_halftime_markets.py
=================================
Treina os modelos de MERCADOS POR TEMPO (1º/2º) — gols e cartões — reusando o
CornersNB (NB independente mandante/visitante, total por convolução), sobre
base_feats (mesmo conjunto seguro do modelo de gols, sem box-score do próprio jogo).

Alvos vêm de data/built/halftime_targets.parquet (build_halftime_targets.py),
casados com a base enriquecida por (date, home_team, away_team).

Persiste:
  api/model_artifacts/gols_1t_nb.joblib, gols_2t_nb.joblib,
  api/model_artifacts/cartoes_1t_nb.joblib, cartoes_2t_nb.joblib
NÃO toca outros artefatos.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
from corners_nb_model import CornersNB

warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = Path(".")
CSV = ROOT / "international_features_enriched_apifootball.csv"
TARGETS = ROOT / "data" / "built" / "halftime_targets.parquet"
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
ART = Path("api/model_artifacts")

# (nome, alvo_home, alvo_away, exige_evento_cartao, max_grade)
MARKETS = [
    ("gols_1t", "home_goals_1t", "away_goals_1t", False, 12),
    ("gols_2t", "home_goals_2t", "away_goals_2t", False, 12),
    ("cartoes_1t", "home_cards_1t", "away_cards_1t", True, 15),
    ("cartoes_2t", "home_cards_2t", "away_cards_2t", True, 15),
]


def main():
    csv = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    csv["dkey"] = csv["date"].astype(str).str[:10]
    tgt = pd.read_parquet(TARGETS)
    df = csv.merge(tgt, left_on=["dkey", "home_team", "away_team"],
                   right_on=["date", "home_team", "away_team"], how="inner", suffixes=("", "_t"))
    print(f"Base casada: {len(df)} jogos")

    for name, th, ta, need_cards, grade in MARKETS:
        d = df.dropna(subset=[th, ta]).copy()
        if need_cards:
            d = d[d["has_card_events"] == 1]
        yh = d[th].astype(int).values
        ya = d[ta].astype(int).values
        print(f"\n>> {name}: N={len(d)} | média real mand {yh.mean():.2f} vis {ya.mean():.2f} total {(yh+ya).mean():.2f}")
        m = CornersNB(feats=BASE_FEATS, max_corners=grade)
        m.fit(d[BASE_FEATS], yh, ya)
        dist = m.predict_distributions(d[BASE_FEATS])
        ks = np.arange(m.max_corners + 1); kt = np.arange(2 * m.max_corners + 1)
        print(f"   E[PMF] mand {(dist['home']@ks).mean():.2f} vis {(dist['away']@ks).mean():.2f} "
              f"total {(dist['total']@kt).mean():.2f} (sanidade in-sample)")
        out = ART / f"{name}_nb.joblib"
        m.save(str(out))
        print(f"   salvo: {out}")


if __name__ == "__main__":
    main()
