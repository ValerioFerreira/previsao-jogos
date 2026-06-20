import sys
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
from sklearn.metrics import log_loss, mean_absolute_error, mean_squared_error
from sklearn.calibration import calibration_curve
from scipy.stats import norm

# Add api directory to sys.path
sys.path.append(str(Path("api").resolve()))
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")

CSV_PATH = Path("api/international_features_enriched.csv")
ARTIFACTS_DIR = Path(r"C:\Users\10341953440\.gemini\antigravity\brain\38bd63cd-c1e9-4756-9d77-8346dce6bac3")
PLOTS_DIR = ARTIFACTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
COMP_DATA_PATH = ARTIFACTS_DIR / "dixon_coles_comparison_old.json"

RS = 42
QUANTILES = [0.1, 0.5, 0.9]
M_GOALS = 12

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

def compute_quantile_goals_distribution(pred_q10, pred_q50, pred_q90, max_goals=12):
    N = len(pred_q50)
    probs = np.zeros((N, max_goals + 1))
    k = np.arange(max_goals + 1)
    
    for i in range(N):
        mu = pred_q50[i]
        std = max(0.1, (pred_q90[i] - pred_q10[i]) / 2.563)
        
        p_k = norm.cdf(k + 0.5, loc=mu, scale=std) - norm.cdf(k - 0.5, loc=mu, scale=std)
        p_k[p_k < 0] = 0.0
        if p_k.sum() > 0:
            p_k /= p_k.sum()
        else:
            p_k[0] = 1.0
            
        probs[i] = p_k
        
    return probs

def main():
    print("================================================================================")
    print("RE-VALIDAÇÃO NO DATASET AN TIGO DE PRODUÇÃO (api/international_features_enriched.csv)")
    print("================================================================================")
    
    if not CSV_PATH.exists():
        print(f"[ERRO] {CSV_PATH} não encontrado.")
        return
        
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    all_feats = numeric_features(df)
    base_feats = [c for c in all_feats if "sb_" not in c]
    
    # Divisão temporal usando has_advanced_stats (para termos jogos de teste com mesma data e volume do diagnóstico)
    df_adv = df[df["has_advanced_stats"] == 1].copy()
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff_date = df_adv.iloc[n_train_idx]["date"]
    print(f"Data de corte temporal: {cutoff_date.strftime('%Y-%m-%d')}")
    
    df_train = df[df["date"] <= cutoff_date].reset_index(drop=True)
    df_test = df[(df["date"] > cutoff_date) & (df["has_advanced_stats"] == 1)].reset_index(drop=True)
    
    print(f"Treino: {len(df_train)} jogos | Teste: {len(df_test)} jogos")
    
    # 1. Ajustar os Modelos Atuais no Treino
    print("\n>> Ajustando modelos ATUAIS no treino...")
    clf_res = fit_rf_classifier(df_train, base_feats, "result")
    clf_btts = fit_rf_classifier(df_train, base_feats, "btts")
    clf_ov = fit_rf_classifier(df_train, base_feats, "over_2_5")
    
    y_train_goals = df_train["home_score"] + df_train["away_score"]
    qm_goals = fit_quantile_models(df_train, base_feats, y_train_goals, leaf=10)
    
    # 2. Ajustar o Modelo Dixon-Coles NB no Treino
    print("\n>> Ajustando modelo DIXON-COLES (Binomial Negativo) no treino...")
    dc_model = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=M_GOALS, random_state=RS)
    dc_model.fit(df_train[base_feats], df_train["home_score"], df_train["away_score"])
    
    # 3. Gerar previsões e probabilidades no conjunto de Teste (Out-of-sample)
    print("\n>> Gerando predições probabilísticas no teste...")
    X_test = df_test[base_feats]
    y_test_goals = (df_test["home_score"] + df_test["away_score"]).values
    y_test_res = df_test["result"].values
    y_test_btts = df_test["btts"].values
    y_test_ov = df_test["over_2_5"].values
    
    # A) Previsões Modelo Atual
    prob_btts_curr = clf_btts.predict_proba(X_test)[:, 1]
    prob_ov_curr = clf_ov.predict_proba(X_test)[:, 1]
    
    res_classes = list(clf_res.classes_)
    prob_res_curr = clf_res.predict_proba(X_test)
    y_test_res_encoded = np.array([res_classes.index(v) for v in y_test_res])
    
    pred_q10 = qm_goals[0.1].predict(X_test)
    pred_q50 = qm_goals[0.5].predict(X_test)
    pred_q90 = qm_goals[0.9].predict(X_test)
    prob_goals_curr = compute_quantile_goals_distribution(pred_q10, pred_q50, pred_q90, max_goals=M_GOALS)
    
    # B) Previsões Modelo Dixon-Coles NB (Unificado)
    dc_probs = dc_model.predict_proba_markets(X_test)
    prob_res_dc = dc_probs["result"]  # [A, D, H]
    prob_btts_dc = dc_probs["btts"]
    prob_ov_dc = dc_probs["over_2_5"]
    
    P_joint_dc = dc_probs["joint"]
    prob_goals_dc = np.zeros((len(df_test), M_GOALS + 1))
    for i in range(len(df_test)):
        for x in range(M_GOALS + 1):
            for y in range(M_GOALS + 1):
                if x + y <= M_GOALS:
                    prob_goals_dc[i, x + y] += P_joint_dc[i, x, y]
        if prob_goals_dc[i].sum() > 0:
            prob_goals_dc[i] /= prob_goals_dc[i].sum()
            
    # 4. Cálculo de Métricas Probabilísticas
    print("\n>> Calculando métricas probabilísticas...")
    
    # 1. BTTS
    btts_brier_curr = mean_squared_error(y_test_btts, prob_btts_curr)
    btts_brier_dc = mean_squared_error(y_test_btts, prob_btts_dc)
    btts_ece_curr = expected_calibration_error(y_test_btts, prob_btts_curr)
    btts_ece_dc = expected_calibration_error(y_test_btts, prob_btts_dc)
    
    # 2. Over 2.5
    ov_brier_curr = mean_squared_error(y_test_ov, prob_ov_curr)
    ov_brier_dc = mean_squared_error(y_test_ov, prob_ov_dc)
    ov_ece_curr = expected_calibration_error(y_test_ov, prob_ov_curr)
    ov_ece_dc = expected_calibration_error(y_test_ov, prob_ov_dc)
    
    # 3. Resultado de Partida (Multiclasse)
    res_logloss_curr = log_loss(y_test_res_encoded, prob_res_curr, labels=np.arange(3))
    res_logloss_dc = log_loss(y_test_res_encoded, prob_res_dc, labels=np.arange(3))
    res_ece_curr = multiclass_ece(y_test_res, prob_res_curr, res_classes)
    res_ece_dc = multiclass_ece(y_test_res, prob_res_dc, ["A", "D", "H"])
    
    # 4. Gols Totais
    y_test_goals_clipped = np.clip(y_test_goals, 0, M_GOALS).astype(int)
    g_logloss_curr = -np.mean(np.log(prob_goals_curr[np.arange(len(df_test)), y_test_goals_clipped] + 1e-15))
    g_logloss_dc = -np.mean(np.log(prob_goals_dc[np.arange(len(df_test)), y_test_goals_clipped] + 1e-15))
    
    # MAE/RMSE
    mae_curr = mean_absolute_error(y_test_goals, pred_q50)
    rmse_curr = np.sqrt(mean_squared_error(y_test_goals, pred_q50))
    
    pred_goals_dc = np.sum(prob_goals_dc * np.arange(M_GOALS + 1), axis=1)
    mae_dc = mean_absolute_error(y_test_goals, pred_goals_dc)
    rmse_dc = np.sqrt(mean_squared_error(y_test_goals, pred_goals_dc))
    
    comparison = {
        "btts": {
            "brier_curr": float(btts_brier_curr),
            "brier_dc": float(btts_brier_dc),
            "ece_curr": float(btts_ece_curr),
            "ece_dc": float(btts_ece_dc)
        },
        "over_2_5": {
            "brier_curr": float(ov_brier_curr),
            "brier_dc": float(ov_brier_dc),
            "ece_curr": float(ov_ece_curr),
            "ece_dc": float(ov_ece_dc)
        },
        "result": {
            "logloss_curr": float(res_logloss_curr),
            "logloss_dc": float(res_logloss_dc),
            "ece_curr": float(res_ece_curr),
            "ece_dc": float(res_ece_dc)
        },
        "total_goals": {
            "logloss_curr": float(g_logloss_curr),
            "logloss_dc": float(g_logloss_dc),
            "mae_curr": float(mae_curr),
            "mae_dc": float(mae_dc),
            "rmse_curr": float(rmse_curr),
            "rmse_dc": float(rmse_dc)
        }
    }
    
    with open(COMP_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
        
    print("\n" + "="*80)
    print(" TABELA COMPARATIVA DE DESEMPENHO PROBABILÍSTICO (PRODUÇÃO / ANTIGO)")
    print("="*80)
    print(f"{'Mercado / Métrica':<35} | {'Modelo Atual (RF/Quant)':<25} | {'Modelo Dixon-Coles NB':<25}")
    print("-"*80)
    print(f"{'BTTS - Brier Score':<35} | {btts_brier_curr:.5f}                     | {btts_brier_dc:.5f}")
    print(f"{'BTTS - ECE':<35} | {btts_ece_curr:.5f}                     | {btts_ece_dc:.5f}")
    print("-"*80)
    print(f"{'Over 2.5 - Brier Score':<35} | {ov_brier_curr:.5f}                     | {ov_brier_dc:.5f}")
    print(f"{'Over 2.5 - ECE':<35} | {ov_ece_curr:.5f}                     | {ov_ece_dc:.5f}")
    print("-"*80)
    print(f"{'Resultado H/D/A - Log-Loss':<35} | {res_logloss_curr:.5f}                     | {res_logloss_dc:.5f}")
    print(f"{'Resultado H/D/A - ECE':<35} | {res_ece_curr:.5f}                     | {res_ece_dc:.5f}")
    print("-"*80)
    print(f"{'Total Gols - Log-Loss':<35} | {g_logloss_curr:.5f}                     | {g_logloss_dc:.5f}")
    print(f"{'Total Gols - MAE':<35} | {mae_curr:.5f}                     | {mae_dc:.5f}")
    print(f"{'Total Gols - RMSE':<35} | {rmse_curr:.5f}                     | {rmse_dc:.5f}")
    print("="*80)
    
    # Plots
    plt.figure(figsize=(12, 5))
    
    prob_true_b_curr, prob_pred_b_curr = calibration_curve(y_test_btts, prob_btts_curr, n_bins=8)
    prob_true_b_dc, prob_pred_b_dc = calibration_curve(y_test_btts, prob_btts_dc, n_bins=8)
    
    plt.subplot(1, 2, 1)
    plt.plot([0, 1], [0, 1], "k--", label="Perfeita")
    plt.plot(prob_pred_b_curr, prob_true_b_curr, "s-", color="gray", alpha=0.7, label=f"Atual (ECE={btts_ece_curr:.4f})")
    plt.plot(prob_pred_b_dc, prob_true_b_dc, "o-", color="dodgerblue", linewidth=2, label=f"Dixon-Coles (ECE={btts_ece_dc:.4f})")
    plt.xlabel("Probabilidade Prevista")
    plt.ylabel("Frequência Observada")
    plt.title("Reliability - Ambas Marcam (BTTS)")
    plt.legend()
    
    prob_true_o_curr, prob_pred_o_curr = calibration_curve(y_test_ov, prob_ov_curr, n_bins=8)
    prob_true_o_dc, prob_pred_o_dc = calibration_curve(y_test_ov, prob_ov_dc, n_bins=8)
    
    plt.subplot(1, 2, 2)
    plt.plot([0, 1], [0, 1], "k--", label="Perfeita")
    plt.plot(prob_pred_o_curr, prob_true_o_curr, "s-", color="gray", alpha=0.7, label=f"Atual (ECE={ov_ece_curr:.4f})")
    plt.plot(prob_pred_o_dc, prob_true_o_dc, "o-", color="crimson", linewidth=2, label=f"Dixon-Coles (ECE={ov_ece_dc:.4f})")
    plt.xlabel("Probabilidade Prevista")
    plt.ylabel("Frequência Observada")
    plt.title("Reliability - Over 2.5 Gols")
    plt.legend()
    
    plt.tight_layout()
    plot_path = PLOTS_DIR / "compare_calibration_dc_old.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()
    
    print(f">> Gráfico salvo em: {plot_path}")
    print(f">> Dados de comparação salvos em: {COMP_DATA_PATH}")

if __name__ == "__main__":
    main()
