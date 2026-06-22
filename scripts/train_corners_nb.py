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


from sklearn.model_selection import KFold
from scipy.stats import nbinom

def grid_search_r(df_adv, feats):
    print("\n>> Executing K-Fold Grid Search to optimize dispersion parameter r...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    r_vals = np.arange(2.0, 30.1, 0.5)
    
    val_losses_h = {r: [] for r in r_vals}
    val_losses_a = {r: [] for r in r_vals}
    
    X = df_adv[feats]
    y_h = df_adv["home_cur_sb_corners"].astype(int).values
    y_a = df_adv["away_cur_sb_corners"].astype(int).values
    
    for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_h_tr, y_h_val = y_h[train_idx], y_h[val_idx]
        y_a_tr, y_a_val = y_a[train_idx], y_a[val_idx]
        
        # Fit expectation model on training fold
        m = CornersNB(feats=feats)
        m.model_home_ = m._create_base_regressor()
        m.model_away_ = m._create_base_regressor()
        m.model_home_.fit(X_tr, y_h_tr)
        m.model_away_.fit(X_tr, y_a_tr)
        
        # Predict on validation fold
        lambdas = np.maximum(m.model_home_.predict(X_val), 0.1)
        mus = np.maximum(m.model_away_.predict(X_val), 0.1)
        
        for r in r_vals:
            p_h = r / (r + lambdas)
            nll_h = -np.mean(np.log(nbinom.pmf(y_h_val, n=r, p=p_h) + 1e-15))
            val_losses_h[r].append(nll_h)
            
            p_a = r / (r + mus)
            nll_a = -np.mean(np.log(nbinom.pmf(y_a_val, n=r, p=p_a) + 1e-15))
            val_losses_a[r].append(nll_a)
            
    avg_h = {r: np.mean(losses) for r, losses in val_losses_h.items()}
    avg_a = {r: np.mean(losses) for r, losses in val_losses_a.items()}
    
    best_r_h = min(avg_h, key=avg_h.get)
    best_r_a = min(avg_a, key=avg_a.get)
    
    print(f"  Optimal Grid Search r_H: {best_r_h:.2f} (NLL: {avg_h[best_r_h]:.4f})")
    print(f"  Optimal Grid Search r_A: {best_r_a:.2f} (NLL: {avg_a[best_r_a]:.4f})")
    return best_r_h, best_r_a

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
    
    # 2. Carregar predições Out-of-Fold de chutes para simular cenário real (sem leakage)
    oof_shots = pd.read_csv("data/built/oof_shots.csv")
    df_adv = df_adv.merge(oof_shots, on="match_id", how="left")
    df_adv["pred_home_shots"] = df_adv["pred_home_shots_oof"]
    df_adv["pred_away_shots"] = df_adv["pred_away_shots_oof"]
    
    print(f"Jogos com escanteios válidos (base de treino cheia): {len(df_adv)}")

    # 3. Grid Search para r nos folds de validação (leakage-free)
    best_r_h, best_r_a = grid_search_r(df_adv, feats)

    X = df_adv[feats]
    y_h = df_adv["home_cur_sb_corners"].astype(int).values
    y_a = df_adv["away_cur_sb_corners"].astype(int).values

    # 4. Treinar modelo final com os regressores na base inteira
    model = CornersNB(n_estimators=100, max_depth=3, learning_rate=0.05,
                      max_corners=25, random_state=42, feats=feats)
    model.fit(X, y_h, y_a)
    
    print(f"\n>> Parâmetros de Dispersão MLE Finais (Base Inteira): r_H={model.r_H_:.4f}, r_A={model.r_A_:.4f}")
    
    # Sobrescrever r com os valores ótimos de CV (GridSearch)
    model.r_H_ = best_r_h
    model.r_A_ = best_r_a
    print(f">> Aplicados parâmetros de dispersão otimizados via Grid Search: r_H={model.r_H_:.2f}, r_A={model.r_A_:.2f}")

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
