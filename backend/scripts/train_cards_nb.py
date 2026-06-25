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
from cards_gp_model import CardsGP
from shots_nb_model import ShotsNB
from ortho_sinais import apply_ortho_residuals
import joblib

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META_PATH = Path("api/model_artifacts/meta.json")
OUT_PATH = Path("api/model_artifacts/cards_gp.joblib")


def main():
    print("=" * 78)
    print(" TREINO DE PRODUCAO — CardsGP (Poisson Generalizada) base inteira")
    print("=" * 78)

    meta = json.load(open(META_PATH, encoding="utf-8"))
    STYLE_RAW = [c for c in meta["full_feats"] if c.startswith("home_style_") or c.startswith("away_style_") or c.startswith("diff_style_")]
    feats = [f for f in meta["full_feats"] if f not in STYLE_RAW]
    print(f"Features: {len(feats)} (full_feats sem raw_style + cascade)")

    df = pd.read_csv(CSV_PATH, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_cards", "away_cur_sb_cards"]).copy()
    
    # 1. Aplicar ortogonalizacao de estilo
    weights = joblib.load("api/model_artifacts/style_ortho_weights.joblib")
    adv = apply_ortho_residuals(adv, weights)
    
    # 2. Carregar modelo de chutes e prever expectativas (cascade)
    shots_model = ShotsNB.load("api/model_artifacts/shots_nb.joblib")
    shots_dists = shots_model.predict_distributions(adv)
    adv["pred_home_shots"] = shots_dists["lambdas"]
    adv["pred_away_shots"] = shots_dists["mus"]
    
    print(f"Jogos com cartoes validos: {len(adv)}")

    X = adv[feats]
    y_h = adv["home_cur_sb_cards"].astype(int).values
    y_a = adv["away_cur_sb_cards"].astype(int).values

    model = CardsGP(max_corners=15, feats=feats)
    model.fit(X, y_h, y_a)
    print(f"  gp_lambda_H={model.gp_lambda_H_:.4f} gp_lambda_A={model.gp_lambda_A_:.4f}")

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
