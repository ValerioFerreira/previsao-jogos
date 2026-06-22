#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_corners_nb.py
===========================
Treina o modelo de produção DynamicCornersNB (Binomial Negativa com Dispersão Dinâmica)
sobre a BASE INTEIRA (todos os jogos com estatísticas avançadas válidas).
Usa as predições de chutes OOF para simular incerteza realista e os resíduos de estilo.
Persiste em api/model_artifacts/dynamic_corners_nb.joblib.
"""
import sys
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, str(Path("api").resolve()))
from corners_dynamic_nb import DynamicCornersNB
from corner_interactions import add_corner_interactions
from ortho_sinais import apply_ortho_residuals

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META_PATH = Path("api/model_artifacts/meta.json")
OUT_PATH = Path("api/model_artifacts/dynamic_corners_nb.joblib")


def main():
    print("=" * 80)
    print(" TREINO DE PRODUÇÃO — DynamicCornersNB (Dispersão Dinâmica)")
    print("=" * 80)

    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df_adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]
    ).copy()
    df_adv = add_corner_interactions(df_adv)
    
    # 1. Aplicar ortogonalizacao de estilo
    weights = joblib.load("api/model_artifacts/style_ortho_weights.joblib")
    df_adv = apply_ortho_residuals(df_adv, weights)
    
    # 2. Carregar predições Out-of-Fold de chutes para simular cenário real
    oof_shots = pd.read_csv("data/built/oof_shots.csv")
    df_adv = df_adv.merge(oof_shots, on="match_id", how="left")
    df_adv["pred_home_shots"] = df_adv["pred_home_shots_oof"]
    df_adv["pred_away_shots"] = df_adv["pred_away_shots_oof"]
    
    print(f"Jogos com escanteios válidos (base de treino cheia): {len(df_adv)}")

    y_h = df_adv["home_cur_sb_corners"].astype(int).values
    y_a = df_adv["away_cur_sb_corners"].astype(int).values

    # 3. Instanciar e treinar DynamicCornersNB (inicia a partir dos r_estáticos do GridSearch: Home=10.0, Away=8.5)
    model = DynamicCornersNB(max_corners=25, init_r_home=10.0, init_r_away=8.5)
    model.fit(df_adv, y_h, y_a)

    # ----------------------------------------------------------------- viés global e estatísticas de r
    print("\n>> Validação de viés global (in-sample, sanidade)")
    dists = model.predict_distributions(df_adv)
    k_side = np.arange(model.max_corners + 1)
    k_total = np.arange(2 * model.max_corners + 1)

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

    print("\n>> Estatísticas de Dispersão Dinâmica (r):")
    print(f"  r_H (Mandante):  média {np.mean(dists['r_home']):.4f} | mín {np.min(dists['r_home']):.4f} | máx {np.max(dists['r_home']):.4f}")
    print(f"  r_A (Visitante): média {np.mean(dists['r_away']):.4f} | mín {np.min(dists['r_away']):.4f} | máx {np.max(dists['r_away']):.4f}")

    # ----------------------------------------------------------------- Coeficientes de log(r)
    # Z_i: intercepto, pred_total_shots, abs_elo_diff
    print("\n>> Coeficientes da Equação de log(r) [Z: Intercepto, pred_total_shots, abs_elo_diff]:")
    print(f"  Mandante  (gamma): {['{:.4f}'.format(x) for x in model.gamma_home_]}")
    print(f"  Visitante (gamma): {['{:.4f}'.format(x) for x in model.gamma_away_]}")

    # ----------------------------------------------------------------- persistir
    model.save(str(OUT_PATH))
    print(f"\nOK. Artefato salvo: {OUT_PATH} (nada mais foi tocado).")


if __name__ == "__main__":
    main()
