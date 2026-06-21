#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_cards_nb.py
=========================
Treina o modelo de producao CardsNB (NB independente, na pratica Poisson) sobre a
BASE INTEIRA (jogos com cartoes validos), com as 243 features de meta["full_feats"],
e persiste api/model_artifacts/cards_nb.joblib.

Nao toca em nenhum artefato existente: apenas cria cards_nb.joblib.
Imprime r (esperado alto -> Poisson) e o vies global (sanidade).
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
from cards_nb_model import CardsNB

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META_PATH = Path("api/model_artifacts/meta.json")
OUT_PATH = Path("api/model_artifacts/cards_nb.joblib")


def main():
    print("=" * 78)
    print(" TREINO DE PRODUCAO — CardsNB (NB independente / ~Poisson) base inteira")
    print("=" * 78)

    meta = json.load(open(META_PATH, encoding="utf-8"))
    feats = meta["full_feats"]
    print(f"Features (meta.full_feats): {len(feats)}")

    df = pd.read_csv(CSV_PATH, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_cards", "away_cur_sb_cards"]).copy()
    print(f"Jogos com cartoes validos: {len(adv)}")

    X = adv[feats]
    y_h = adv["home_cur_sb_cards"].astype(int).values
    y_a = adv["away_cur_sb_cards"].astype(int).values

    model = CardsNB(max_corners=15, feats=feats)
    model.fit(X, y_h, y_a)
    print(f"  r_H={model.r_H_:.2f} r_A={model.r_A_:.2f}  (alto = colapso em Poisson, esperado)")

    # vies global (in-sample, sanidade)
    d = model.predict_distributions(X)
    k_side = np.arange(model.max_corners + 1)
    k_tot = np.arange(2 * model.max_corners + 1)
    real_h, real_a, real_t = float(y_h.mean()), float(y_a.mean()), float((y_h + y_a).mean())
    epmf_h = float(np.mean(d["home"] @ k_side))
    epmf_a = float(np.mean(d["away"] @ k_side))
    epmf_t = float(np.mean(d["total"] @ k_tot))
    print("\n>> Vies global (in-sample):")
    print(f"  {'Mercado':10s} {'Real':>8s} {'E[PMF]':>8s}")
    print(f"  {'Mandante':10s} {real_h:8.3f} {epmf_h:8.3f}")
    print(f"  {'Visitante':10s} {real_a:8.3f} {epmf_a:8.3f}")
    print(f"  {'Total':10s} {real_t:8.3f} {epmf_t:8.3f}")

    model.save(str(OUT_PATH))
    print(f"\nOK. Artefato salvo: {OUT_PATH} (nada mais foi tocado).")


if __name__ == "__main__":
    main()
