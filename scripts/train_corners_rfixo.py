#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_corners_rfixo.py
==============================
Treina o modelo de produção de escanteios INTERMEDIÁRIO (cascata + estilo
ortogonalizado, Binomial Negativa com dispersão FIXA r_H=10.0 / r_A=8.5).

Motivação (rollback): o DynamicCornersNB (dispersão log-linear) foi REPROVADO no
gate honesto OOS — regrediu log-loss e MAE vs este intermediário e estourou a
calibração de cauda (Tail ECE Over 8.5 = 22.4% vs limite 4%). Ver
data/reports/POST_MORTEM_DYNAMIC_DISPERSION.md e comparacao_escanteios_dinamico.md.

Este script reproduz EXATAMENTE a construção do "Modelo Intermediário" validado em
scripts/compare_corners.py (mesmas features, mesmos r fixos do GridSearch), agora
treinado sobre a base inteira para servir em produção.
Persiste em api/model_artifacts/corners_cascade_rfixo.joblib.
"""
import sys
import json
import warnings
from pathlib import Path
import pandas as pd
import joblib

sys.path.insert(0, str(Path("api").resolve()))
from corners_nb_model import CornersNB
from corner_interactions import add_corner_interactions, CORNER_INTERACTIONS
from ortho_sinais import apply_ortho_residuals

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META_PATH = Path("api/model_artifacts/meta.json")
WEIGHTS_PATH = Path("api/model_artifacts/style_ortho_weights.joblib")
OOF_SHOTS_PATH = Path("data/built/oof_shots.csv")
OUT_PATH = Path("api/model_artifacts/corners_cascade_rfixo.joblib")

# Dispersão fixa do GridSearch (modelo intermediário validado)
R_H_FIXO = 10.0
R_A_FIXO = 8.5


def main():
    print("=" * 80)
    print(" TREINO DE PRODUÇÃO — Escanteios INTERMEDIÁRIO (cascata + estilo, r-fixo)")
    print("=" * 80)

    meta = json.load(open(META_PATH, encoding="utf-8"))
    style_raw = [c for c in meta["full_feats"]
                 if c.startswith("home_style_") or c.startswith("away_style_")
                 or c.startswith("diff_style_")]
    feats_new = [f for f in meta["full_feats"] if f not in style_raw] + CORNER_INTERACTIONS

    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df_adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]
    ).copy()
    df_adv = add_corner_interactions(df_adv)

    # 1. Ortogonalização de estilo (pesos salvos, mesmos da inferência)
    weights = joblib.load(WEIGHTS_PATH)
    df_adv = apply_ortho_residuals(df_adv, weights)

    # 2. Predições OOF de chutes (cascata, anti-leakage), idêntico ao treino dinâmico
    oof_shots = pd.read_csv(OOF_SHOTS_PATH)
    df_adv = df_adv.merge(oof_shots, on="match_id", how="left")
    df_adv["pred_home_shots"] = df_adv["pred_home_shots_oof"]
    df_adv["pred_away_shots"] = df_adv["pred_away_shots_oof"]

    print(f"Jogos com escanteios válidos (base de treino cheia): {len(df_adv)}")
    y_h = df_adv["home_cur_sb_corners"].astype(int).values
    y_a = df_adv["away_cur_sb_corners"].astype(int).values

    # 3. Construção do intermediário: regressores de expectativa + r FIXO (sem MLE)
    model = CornersNB(feats=feats_new)
    model.model_home_ = model._create_base_regressor()
    model.model_away_ = model._create_base_regressor()
    model.model_home_.fit(df_adv[feats_new], y_h)
    model.model_away_.fit(df_adv[feats_new], y_a)
    model.r_H_ = R_H_FIXO
    model.r_A_ = R_A_FIXO
    print(f"  r_H (fixo, GridSearch): {model.r_H_}")
    print(f"  r_A (fixo, GridSearch): {model.r_A_}")

    # 4. Sanidade de viés global in-sample
    dists = model.predict_distributions(df_adv[feats_new])
    import numpy as np
    k_side = np.arange(model.max_corners + 1)
    k_total = np.arange(2 * model.max_corners + 1)
    epmf_h = float(np.mean(dists["home"] @ k_side))
    epmf_a = float(np.mean(dists["away"] @ k_side))
    epmf_t = float(np.mean(dists["total"] @ k_total))
    print("\n>> Viés global (in-sample, sanidade)")
    print(f"  {'Mercado':10s} {'Média Real':>12s} {'E[PMF]':>12s}")
    print(f"  {'Mandante':10s} {float(y_h.mean()):12.4f} {epmf_h:12.4f}")
    print(f"  {'Visitante':10s} {float(y_a.mean()):12.4f} {epmf_a:12.4f}")
    print(f"  {'Total':10s} {float((y_h + y_a).mean()):12.4f} {epmf_t:12.4f}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(OUT_PATH))
    print(f"\nOK. Artefato salvo: {OUT_PATH} (nada mais foi tocado).")


if __name__ == "__main__":
    main()
