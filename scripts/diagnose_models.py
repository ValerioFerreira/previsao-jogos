#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/diagnose_models.py
==========================
Executa a Fase 1 — Diagnóstico dos Modelos de Gols e Escanteios:
  - Divisão Temporal justa (80% treino <= cutoff_date, 20% teste no futuro).
  - Baselines ingênuas (Média Global e Média Condicional com anti-leakage).
  - Medição de calibração (Brier Score, ECE, Reliability Diagrams).
  - Análise de cobertura e largura média dos intervalos de 80% quantílicos.
  - Testes quantitativos de aderência (Qui-Quadrado) de Poisson vs Binomial Negativa vs Distribuição Implícita.
  - Salvamento de gráficos em plots/ na pasta de artefatos.
  - Gravação de dados de saída para o relatório final.
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.metrics import log_loss, accuracy_score, mean_absolute_error, mean_squared_error
from sklearn.calibration import calibration_curve
from scipy.stats import chisquare, poisson, nbinom, norm

warnings.filterwarnings("ignore")

# Configuração de Caminhos
CSV_PATH = Path("international_features_enriched_apifootball.csv")
ARTIFACTS_DIR = Path(r"C:\Users\10341953440\.gemini\antigravity\brain\38bd63cd-c1e9-4756-9d77-8346dce6bac3")
PLOTS_DIR = ARTIFACTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DATA_PATH = ARTIFACTS_DIR / "diagnostics_data.json"

RS = 42
QUANTILES = [0.1, 0.5, 0.9]

LEAK_OR_ID = {
    "match_id", "date", "home_team", "away_team", "city", "country", "tournament",
    "home_score", "away_score", "goal_diff", "total_goals", "result",
    "home_win", "away_win", "draw", "btts", "over_2_5",
    "has_advanced_stats", "year", "month", "decade",
}

def numeric_features(df):
    cols = []
    for c in df.columns:
        if c in LEAK_OR_ID: continue
        if c.startswith(("home_cur_", "away_cur_")): continue
        if pd.api.types.is_numeric_dtype(df[c]): cols.append(c)
    return cols

def split_feature_sets(all_feats):
    base = [c for c in all_feats if "sb_" not in c]
    return base, list(all_feats)

def fit_rf_classifier(df, feats, target_col):
    sub = df.dropna(subset=[target_col]).copy()
    X, y = sub[feats], sub[target_col].astype(str)
    pipe = Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(n_estimators=300, max_depth=10, min_samples_leaf=5,
                                       class_weight="balanced", random_state=RS, n_jobs=-1)),
    ])
    pipe.fit(X, y)
    return pipe

def fit_quantile_models(df, feats, target_series, leaf=10):
    sub = df.copy()
    sub["_y"] = target_series
    sub = sub.dropna(subset=["_y"])
    X, y = sub[feats], sub["_y"].astype(float)
    models = {}
    for q in QUANTILES:
        pipe = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(loss="quantile", alpha=q,
                                              n_estimators=300, max_depth=3,
                                              learning_rate=0.05, min_samples_leaf=leaf,
                                              random_state=RS)),
        ])
        pipe.fit(X, y)
        models[q] = pipe
    return models

def expected_calibration_error(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        # Encontrar amostras no bin
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
            
    return ece

def multiclass_ece(y_true, y_prob_matrix, classes, n_bins=10):
    ece_vals = []
    for c_idx, c in enumerate(classes):
        y_true_binary = (y_true == c).astype(int)
        y_prob_binary = y_prob_matrix[:, c_idx]
        ece_vals.append(expected_calibration_error(y_true_binary, y_prob_binary, n_bins))
    return np.mean(ece_vals)

def multiclass_brier_score(y_true_encoded, y_prob_matrix):
    n_samples, n_classes = y_prob_matrix.shape
    y_true_onehot = np.zeros((n_samples, n_classes))
    y_true_onehot[np.arange(n_samples), y_true_encoded] = 1.0
    return np.mean(np.sum((y_prob_matrix - y_true_onehot) ** 2, axis=1))

def run_chi2_test(actual, expected_probs):
    max_val = int(max(actual))
    observed = np.zeros(max_val + 1)
    for v in actual:
        observed[int(v)] += 1
        
    n_samples = len(actual)
    expected = np.array(expected_probs[:max_val + 1]) * n_samples
    
    # Ajuste de normalização por truncamento
    expected_sum = expected.sum()
    if expected_sum < n_samples:
        expected[-1] += (n_samples - expected_sum)
        
    # Agrupar bins para que o esperado seja >= 5 (Regra de Cochran)
    obs_binned = []
    exp_binned = []
    
    running_obs = 0
    running_exp = 0
    for o, e in zip(observed, expected):
        running_obs += o
        running_exp += e
        if running_exp >= 5:
            obs_binned.append(running_obs)
            exp_binned.append(running_exp)
            running_obs = 0
            running_exp = 0
            
    if running_exp > 0 or running_obs > 0:
        if obs_binned:
            obs_binned[-1] += running_obs
            exp_binned[-1] += running_exp
        else:
            obs_binned.append(running_obs)
            exp_binned.append(running_exp)
            
    stat, pval = chisquare(f_obs=obs_binned, f_exp=exp_binned)
    return float(stat), float(pval)

def main():
    print("================================================================================")
    print("FASE 1 - DIAGNÓSTICO DOS MODELOS DE GOLS E ESCANTEIOS")
    print("================================================================================")
    
    if not CSV_PATH.exists():
        print(f"[ERRO] {CSV_PATH} não encontrado.")
        return
        
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # Obter lista de features
    all_feats = numeric_features(df)
    base_feats, full_feats = split_feature_sets(all_feats)
    
    # Filtrar jogos com stats avançadas para ordenar temporalmente
    df_adv = df[df["has_advanced_stats"] == 1].copy()
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff_date = df_adv.iloc[n_train_idx]["date"]
    print(f"Data de corte temporal (80% treino): {cutoff_date.strftime('%Y-%m-%d')}")
    
    # Divisão temporal estrita (Sem Leakage)
    df_train = df[df["date"] <= cutoff_date].reset_index(drop=True)
    df_test = df[(df["date"] > cutoff_date) & (df["has_advanced_stats"] == 1)].reset_index(drop=True)
    
    print(f"Treino: {len(df_train)} jogos (com stats: {len(df_train[df_train['has_advanced_stats'] == 1])})")
    print(f"Teste:  {len(df_test)} jogos (todos com stats avançadas)")
    
    # 1. Ajustar Modelos Temporais de Desenvolvimento
    print("\n>> Ajustando modelos de desenvolvimento no treino...")
    clf_res = fit_rf_classifier(df_train, base_feats, "result")
    clf_btts = fit_rf_classifier(df_train, base_feats, "btts")
    clf_ov = fit_rf_classifier(df_train, base_feats, "over_2_5")
    
    # Regressores quantílicos
    y_train_goals = df_train["home_score"] + df_train["away_score"]
    qm_goals = fit_quantile_models(df_train, base_feats, y_train_goals, leaf=10)
    
    df_train_adv = df_train[df_train["has_advanced_stats"] == 1].copy()
    qm_hc = fit_quantile_models(df_train_adv, full_feats, df_train_adv["home_cur_sb_corners"], leaf=10)
    qm_ac = fit_quantile_models(df_train_adv, full_feats, df_train_adv["away_cur_sb_corners"], leaf=10)
    
    # Opcionais (shots, cards)
    train_shots = df_train_adv["home_cur_sb_shots"] + df_train_adv["away_cur_sb_shots"]
    qm_shots = fit_quantile_models(df_train_adv, full_feats, train_shots, leaf=10)
    train_cards = df_train_adv["home_cur_sb_cards"] + df_train_adv["away_cur_sb_cards"]
    qm_cards = fit_quantile_models(df_train_adv, full_feats, train_cards, leaf=10)
    
    # 2. Configurar os Alvos de Teste
    y_test_goals = (df_test["home_score"] + df_test["away_score"]).values
    y_test_hc = df_test["home_cur_sb_corners"].values
    y_test_ac = df_test["away_cur_sb_corners"].values
    y_test_shots = (df_test["home_cur_sb_shots"] + df_test["away_cur_sb_shots"]).values
    y_test_cards = (df_test["home_cur_sb_cards"] + df_test["away_cur_sb_cards"]).values
    
    y_test_res = df_test["result"].values
    y_test_btts = df_test["btts"].values
    y_test_ov = df_test["over_2_5"].values
    
    # 3. Gerar previsões e calcular baselines (com tratamento rigoroso anti-leakage)
    print("\n>> Calculando métricas e baselines no teste...")
    
    # A) Gols Totais
    goals_global_mean = y_train_goals.mean()
    # Baseline condicional: Média de gols por tournament_weight + elo_diff_bin no treino
    df_train_goals = df_train.copy()
    df_train_goals["goals_total"] = df_train_goals["home_score"] + df_train_goals["away_score"]
    df_train_goals["elo_diff_bin"] = pd.qcut(df_train_goals["elo_diff"], 5, labels=False, duplicates='drop')
    goals_group_means = df_train_goals.groupby(["tournament_weight", "elo_diff_bin"])["goals_total"].mean().to_dict()
    # Limites das faixas no treino
    goals_elo_quantiles = df_train_goals["elo_diff"].quantile([0.2, 0.4, 0.6, 0.8]).values
    
    def get_cond_goals(row):
        t_weight = row["tournament_weight"]
        elo = row["elo_diff"]
        bin_idx = 0
        for q in goals_elo_quantiles:
            if elo > q: bin_idx += 1
            else: break
        return goals_group_means.get((t_weight, bin_idx), goals_global_mean)
        
    goals_cond_pred = df_test.apply(get_cond_goals, axis=1).values
    
    # B) Escanteios Mandante
    hc_global_mean = df_train_adv["home_cur_sb_corners"].mean()
    # Baseline condicional forte: forma de escanteios l5
    hc_cond_pred = df_test["home_sb_corners_l5"].fillna(hc_global_mean).values
    
    # C) Escanteios Visitante
    ac_global_mean = df_train_adv["away_cur_sb_corners"].mean()
    # Baseline condicional forte: forma de escanteios l5
    ac_cond_pred = df_test["away_sb_corners_l5"].fillna(ac_global_mean).values
    
    # D) Shots Totais
    sh_global_mean = train_shots.mean()
    sh_cond_pred = (df_test["home_sb_shots_l5"].fillna(0.0) + df_test["away_sb_shots_l5"].fillna(0.0)).to_numpy(copy=True)
    sh_cond_pred[sh_cond_pred == 0] = sh_global_mean
    
    # E) Cartões Totais
    cards_global_mean = train_cards.mean()
    # Baseline condicional: por tipo de torneio
    df_train_adv["total_cards"] = df_train_adv["home_cur_sb_cards"] + df_train_adv["away_cur_sb_cards"]
    cards_group_means = df_train_adv.groupby("tournament_weight")["total_cards"].mean().to_dict()
    cards_cond_pred = df_test["tournament_weight"].map(cards_group_means).fillna(cards_global_mean).values
    
    # Coletar Métricas de Regressão
    targets_reg = {
        "gols_totais": (y_test_goals, qm_goals, goals_global_mean, goals_cond_pred, base_feats),
        "escanteios_mandante": (y_test_hc, qm_hc, hc_global_mean, hc_cond_pred, full_feats),
        "escanteios_visitante": (y_test_ac, qm_ac, ac_global_mean, ac_cond_pred, full_feats),
        "shots_totais": (y_test_shots, qm_shots, sh_global_mean, sh_cond_pred, full_feats),
        "cartoes_totais": (y_test_cards, qm_cards, cards_global_mean, cards_cond_pred, full_feats),
    }
    
    results_reg = {}
    for name, (y_true, qm, glob_mean, cond_pred, feats) in targets_reg.items():
        pred_mid = qm[0.5].predict(df_test[feats])
        pred_lo = qm[0.1].predict(df_test[feats])
        pred_hi = qm[0.9].predict(df_test[feats])
        
        # Cobertura e Largura
        coverage = np.mean((y_true >= pred_lo) & (y_true <= pred_hi))
        avg_width = np.mean(pred_hi - pred_lo)
        
        # Erros do modelo
        mae_mod = mean_absolute_error(y_true, pred_mid)
        rmse_mod = np.sqrt(mean_squared_error(y_true, pred_mid))
        
        # Global Baseline
        mae_glob = mean_absolute_error(y_true, np.full_like(y_true, glob_mean, dtype=float))
        rmse_glob = np.sqrt(mean_squared_error(y_true, np.full_like(y_true, glob_mean, dtype=float)))
        
        # Conditional Baseline
        mae_cond = mean_absolute_error(y_true, cond_pred)
        rmse_cond = np.sqrt(mean_squared_error(y_true, cond_pred))
        
        results_reg[name] = {
            "model_mae": float(mae_mod),
            "model_rmse": float(rmse_mod),
            "global_mae": float(mae_glob),
            "global_rmse": float(rmse_glob),
            "cond_mae": float(mae_cond),
            "cond_rmse": float(rmse_cond),
            "coverage_80": float(coverage),
            "avg_width_80": float(avg_width),
            "improvement_mae_vs_global": float((mae_glob - mae_mod) / mae_glob),
            "improvement_mae_vs_cond": float((mae_cond - mae_mod) / mae_cond),
        }
        
    # 4. Avaliar Calibração dos Classificadores
    print(">> Calculando calibração dos classificadores...")
    # BTTS
    btts_prob = clf_btts.predict_proba(df_test[base_feats])[:, 1]
    btts_brier = mean_squared_error(y_test_btts, btts_prob)
    btts_ece = expected_calibration_error(y_test_btts, btts_prob, n_bins=10)
    
    # Over 2.5
    ov_prob = clf_ov.predict_proba(df_test[base_feats])[:, 1]
    ov_brier = mean_squared_error(y_test_ov, ov_prob)
    ov_ece = expected_calibration_error(y_test_ov, ov_prob, n_bins=10)
    
    # Result
    res_classes = list(clf_res.classes_)
    res_prob = clf_res.predict_proba(df_test[base_feats])
    # Encodar y_test_res para índices correspondentes a clf_res.classes_
    y_test_res_encoded = np.array([res_classes.index(v) for v in y_test_res])
    res_brier = multiclass_brier_score(y_test_res_encoded, res_prob)
    res_ece = multiclass_ece(y_test_res, res_prob, res_classes, n_bins=10)
    
    results_clf = {
        "btts": {"brier": float(btts_brier), "ece": float(btts_ece)},
        "over_2_5": {"brier": float(ov_brier), "ece": float(ov_ece)},
        "result": {"brier": float(res_brier), "ece": float(res_ece), "classes": res_classes}
    }
    
    # Plots de calibração
    plt.figure(figsize=(15, 5))
    
    # BTTS
    prob_true_btts, prob_pred_btts = calibration_curve(y_test_btts, btts_prob, n_bins=10)
    plt.subplot(1, 3, 1)
    plt.plot([0, 1], [0, 1], "k--", label="Perfeita")
    plt.plot(prob_pred_btts, prob_true_btts, "s-", color="dodgerblue", label=f"BTTS (ECE={btts_ece:.4f})")
    plt.xlabel("Probabilidade Prevista")
    plt.ylabel("Frequência Observada")
    plt.title("Reliability - BTTS")
    plt.legend()
    
    # Over 2.5
    prob_true_ov, prob_pred_ov = calibration_curve(y_test_ov, ov_prob, n_bins=10)
    plt.subplot(1, 3, 2)
    plt.plot([0, 1], [0, 1], "k--", label="Perfeita")
    plt.plot(prob_pred_ov, prob_true_ov, "s-", color="crimson", label=f"Over 2.5 (ECE={ov_ece:.4f})")
    plt.xlabel("Probabilidade Prevista")
    plt.ylabel("Frequência Observada")
    plt.title("Reliability - Over 2.5")
    plt.legend()
    
    # Result (Classe Vitória Mandante - 'H')
    h_idx = res_classes.index("H")
    y_test_h = (y_test_res == "H").astype(int)
    h_prob = res_prob[:, h_idx]
    prob_true_h, prob_pred_h = calibration_curve(y_test_h, h_prob, n_bins=10)
    
    plt.subplot(1, 3, 3)
    plt.plot([0, 1], [0, 1], "k--", label="Perfeita")
    plt.plot(prob_pred_h, prob_true_h, "s-", color="forestgreen", label=f"Mandante H (ECE={res_ece:.4f})")
    plt.xlabel("Probabilidade Prevista")
    plt.ylabel("Frequência Observada")
    plt.title("Reliability - Vitória Mandante (H)")
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "calibration_reliability.png", dpi=150)
    plt.close()
    
    # 5. Diagnóstico de Resíduos e Teste Qui-Quadrado (Distribuições)
    print(">> Calculando diagnóstico de resíduos e testes qui-quadrado...")
    
    distribution_fits = {}
    
    for name, (y_true, qm, glob_mean, _, feats) in [
        ("total_goals", (y_test_goals, qm_goals, goals_global_mean, None, base_feats)),
        ("home_corners", (y_test_hc, qm_hc, hc_global_mean, None, full_feats)),
        ("away_corners", (y_test_ac, qm_ac, ac_global_mean, None, full_feats))
    ]:
        # A) Poisson
        # Parâmetro lambda = média de treino
        lam_fit = float(glob_mean)
        
        # B) Binomial Negativa
        # Ajustar via método dos momentos no treino
        if name == "total_goals":
            y_train_actual = y_train_goals
        elif name == "home_corners":
            y_train_actual = df_train_adv["home_cur_sb_corners"]
        else:
            y_train_actual = df_train_adv["away_cur_sb_corners"]
            
        train_mean = float(y_train_actual.mean())
        train_var = float(y_train_actual.var())
        
        if train_var > train_mean:
            nb_p = train_mean / train_var
            nb_n = (train_mean ** 2) / (train_var - train_mean)
        else:
            # Fallback para Poisson se não houver sobredispersão
            nb_p = 0.99
            nb_n = 100.0
            
        # C) Distribuição Implícita do Modelo
        # Para cada jogo, estimamos N(mu, std) onde mu = q50, std = (q90-q10)/2.563
        pred_q10 = qm[0.1].predict(df_test[feats])
        pred_q50 = qm[0.5].predict(df_test[feats])
        pred_q90 = qm[0.9].predict(df_test[feats])
        
        # Limite máximo de contagem a avaliar no Qui-Quadrado
        max_actual = int(max(y_true))
        counts_range = np.arange(max_actual + 1)
        
        poisson_probs = poisson.pmf(counts_range, lam_fit)
        nbinom_probs = nbinom.pmf(counts_range, nb_n, nb_p)
        
        # Modelo Implícito
        model_probs = np.zeros(len(counts_range))
        for i in range(len(y_true)):
            mu = pred_q50[i]
            std = max(0.1, (pred_q90[i] - pred_q10[i]) / 2.563)
            # Probabilidade discreta para cada inteiro k: integrar Normal de k-0.5 a k+0.5
            p_k = norm.cdf(counts_range + 0.5, loc=mu, scale=std) - norm.cdf(counts_range - 0.5, loc=mu, scale=std)
            # Normalizar para garantir que some 1
            p_k[p_k < 0] = 0.0
            if p_k.sum() > 0:
                p_k /= p_k.sum()
            model_probs += p_k
        model_probs /= len(y_true)
        
        # Teste Qui-Quadrado de Aderência
        chi2_poi_stat, chi2_poi_pval = run_chi2_test(y_true, poisson_probs)
        chi2_nb_stat, chi2_nb_pval = run_chi2_test(y_true, nbinom_probs)
        chi2_mod_stat, chi2_mod_pval = run_chi2_test(y_true, model_probs)
        
        distribution_fits[name] = {
            "poisson": {"stat": chi2_poi_stat, "pval": chi2_poi_pval, "lambda": lam_fit},
            "nbinom": {"stat": chi2_nb_stat, "pval": chi2_nb_pval, "n": float(nb_n), "p": float(nb_p)},
            "model_implied": {"stat": chi2_mod_stat, "pval": chi2_mod_pval}
        }
        
        # Salvar histograma comparativo
        plt.figure(figsize=(8, 5))
        counts, bins = np.histogram(y_true, bins=np.arange(max_actual + 2) - 0.5, density=True)
        bin_centers = 0.5 * (bins[:-1] + bins[1:])
        
        plt.bar(bin_centers, counts, width=0.6, alpha=0.5, color="gray", label="Realidade (Teste)")
        plt.plot(counts_range, poisson_probs, "o-", color="dodgerblue", label=f"Poisson (p={chi2_poi_pval:.4f})")
        plt.plot(counts_range, nbinom_probs, "s-", color="crimson", label=f"Neg Binomial (p={chi2_nb_pval:.4f})")
        plt.plot(counts_range, model_probs, "^-", color="forestgreen", label=f"Model Implied (p={chi2_mod_pval:.4f})")
        
        plt.xlabel("Contagem")
        plt.ylabel("Densidade de Probabilidade")
        plt.title(f"Ajuste de Distribuição - {name.replace('_', ' ').title()}")
        plt.legend()
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / f"distribution_fit_{name}.png", dpi=150)
        plt.close()

    # 6. Salvar dados de diagnóstico
    diagnostics_output = {
        "regression": results_reg,
        "classification": results_clf,
        "distributions": distribution_fits,
        "metadata": {
            "train_size": len(df_train),
            "test_size": len(df_test),
            "cutoff_date": cutoff_date.strftime("%Y-%m-%d")
        }
    }
    
    with open(REPORT_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(diagnostics_output, f, ensure_ascii=False, indent=2)
        
    print(f"\n>> Diagnóstico completo finalizado! Dados salvos em: {REPORT_DATA_PATH}")
    print(f">> Gráficos salvos na pasta: {PLOTS_DIR}")

if __name__ == "__main__":
    main()
