#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_corners_nb.py
===========================
Treina o modelo de produção CornersNB (Binomial Negativa independente) sobre a
BASE INTEIRA (todos os jogos com estatísticas avançadas válidas), com as mesmas
243 features de meta["full_feats"], e persiste api/model_artifacts/corners_nb.joblib.

Não toca em nenhum artefato existente: apenas cria corners_nb.joblib.
Imprime a validação de viés global (média prevista vs real) como sanidade.

Rodar da raiz do projeto:
  ./.venv/Scripts/python.exe scripts/train_corners_nb.py
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
from corners_nb_model import CornersNB
from corner_interactions import add_corner_interactions, CORNER_INTERACTIONS
from shots_nb_model import ShotsNB
from ortho_sinais import apply_ortho_residuals
import joblib

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")  # console cp1252 não encoda λ/acentos
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META_PATH = Path("api/model_artifacts/meta.json")
OUT_PATH = Path("api/model_artifacts/corners_nb.joblib")


def main():
    print("=" * 80)
    print(" TREINO DE PRODUÇÃO — CornersNB (NB independente) sobre a base inteira")
    print("=" * 80)

    meta = json.load(open(META_PATH, encoding="utf-8"))
    STYLE_RAW = [c for c in meta["full_feats"] if c.startswith("home_style_") or c.startswith("away_style_") or c.startswith("diff_style_")]
    feats = [f for f in meta["full_feats"] if f not in STYLE_RAW] + CORNER_INTERACTIONS
    print(f"Features: {len(feats)} (full_feats sem raw_style + cascade + interacoes mando)")

    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df_adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]
    ).copy()
    df_adv = add_corner_interactions(df_adv)
    
    # 1. Aplicar ortogonalizacao de estilo
    weights = joblib.load("api/model_artifacts/style_ortho_weights.joblib")
    df_adv = apply_ortho_residuals(df_adv, weights)
    
    # 2. Carregar modelo de chutes e prever expectativas (cascade)
    shots_model = ShotsNB.load("api/model_artifacts/shots_nb.joblib")
    shots_dists = shots_model.predict_distributions(df_adv)
    df_adv["pred_home_shots"] = shots_dists["lambdas"]
    df_adv["pred_away_shots"] = shots_dists["mus"]
    
    print(f"Jogos com escanteios válidos (base de treino cheia): {len(df_adv)}")

    X = df_adv[feats]
    y_h = df_adv["home_cur_sb_corners"].astype(int).values
    y_a = df_adv["away_cur_sb_corners"].astype(int).values

    model = CornersNB(n_estimators=100, max_depth=3, learning_rate=0.05,
                      max_corners=25, random_state=42, feats=feats)
    model.fit(X, y_h, y_a)

    # ----------------------------------------------------------------- viés global
    print("\n>> Validação de viés global (in-sample, sanidade)")
    dists = model.predict_distributions(X)
    k_side = np.arange(model.max_corners + 1)
    k_total = np.arange(2 * model.max_corners + 1)

    # média prevista = expectativa pontual (lambda) e também E[X] da PMF
    mean_lambda_h = float(np.mean(dists["lambdas"]))
    mean_lambda_a = float(np.mean(dists["mus"]))
    epmf_h = float(np.mean(dists["home"] @ k_side))
    epmf_a = float(np.mean(dists["away"] @ k_side))
    epmf_t = float(np.mean(dists["total"] @ k_total))

    real_h, real_a, real_t = float(y_h.mean()), float(y_a.mean()), float((y_h + y_a).mean())

    print(f"  {'Mercado':10s} {'Média Real':>12s} {'Média λ':>12s} {'E[PMF]':>12s}")
    print(f"  {'Mandante':10s} {real_h:12.4f} {mean_lambda_h:12.4f} {epmf_h:12.4f}")
    print(f"  {'Visitante':10s} {real_a:12.4f} {mean_lambda_a:12.4f} {epmf_a:12.4f}")
    print(f"  {'Total':10s} {real_t:12.4f} {'-':>12s} {epmf_t:12.4f}")

    # ----------------------------------------------------------------- persistir
    model.save(str(OUT_PATH))
    print(f"\nOK. Artefato salvo: {OUT_PATH} (nada mais foi tocado).")


if __name__ == "__main__":
    main()
