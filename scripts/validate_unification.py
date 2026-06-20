import sys
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss, mean_absolute_error, mean_squared_error
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor


sys.path.append(str(Path("api").resolve()))
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")

CSV_PATH = Path("international_features_enriched_apifootball.csv")
RS = 42
M_GOALS = 12
QUANTILES = [0.1, 0.5, 0.9]


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
    print("RE-VALIDAÇÃO COMPLETA — DATASET API-FOOTBALL (PRODUÇÃO UNIFICADA)")
    print("================================================================================")
    
    if not CSV_PATH.exists():
        print(f"[ERRO] {CSV_PATH} não encontrado.")
        return
        
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # 1. Carregar artefatos oficiais da produção (recém unificados)
    from predictor import Predictor
    p = Predictor(art_dir="api/model_artifacts")
    
    bf = p.meta["base_feats"]
    ff = p.meta["full_feats"]
    
    # Divisão temporal 80% / 20%
    df_adv = df[df["has_advanced_stats"] == 1].copy()
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff_date = df_adv.iloc[n_train_idx]["date"]
    print(f"Data de corte temporal: {cutoff_date.strftime('%Y-%m-%d')}")
    
    df_train = df[df["date"] <= cutoff_date].reset_index(drop=True)
    df_test = df[(df["date"] > cutoff_date) & (df["has_advanced_stats"] == 1)].reset_index(drop=True)
    
    print(f"Treino: {len(df_train)} jogos | Teste: {len(df_test)} jogos")
    
    # Re-treinar os modelos no treino temporal para avaliação probabilística out-of-sample justa
    # NOTA: O modelo em produção foi treinado com N=9.976, mas para avaliar métricas probabilisticas out-of-sample (como ECE/Log-loss)
    # sem vazamento, precisamos ajustar os modelos temporais sobre o conjunto de treino correspondente.
    print("\n>> Treinando modelos temporais para avaliação justa out-of-sample...")
    
    # Dixon-Coles temporal
    dc_temp = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=M_GOALS, random_state=RS)
    dc_temp.fit(df_train[bf], df_train["home_score"], df_train["away_score"])
    
    # Modelos legados (RF) temporais para comparação
    clf_res_temp = fit_rf_classifier(df_train, bf, "result")
    clf_btts_temp = fit_rf_classifier(df_train, bf, "btts")
    clf_ov_temp = fit_rf_classifier(df_train, bf, "over_2_5")
    
    y_train_goals = df_train["home_score"] + df_train["away_score"]
    qm_goals_temp = fit_quantile_models(df_train, bf, y_train_goals, leaf=10)
    
    # --------------------------------------------------------------------------
    # 2. Avaliação de Gols e Resultado (Dixon-Coles)
    # --------------------------------------------------------------------------
    print("\n>> Executando avaliações no teste temporal...")
    
    X_test = df_test[bf]
    y_test_goals = (df_test["home_score"] + df_test["away_score"]).values
    y_test_res = df_test["result"].values
    y_test_btts = df_test["btts"].values
    y_test_ov = df_test["over_2_5"].values
    
    # Predições Dixon-Coles
    dc_probs = dc_temp.predict_proba_markets(X_test)
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
            
    # Predições Legado
    prob_btts_curr = clf_btts_temp.predict_proba(X_test)[:, 1]
    prob_ov_curr = clf_ov_temp.predict_proba(X_test)[:, 1]
    
    res_classes = list(clf_res_temp.classes_)
    prob_res_curr = clf_res_temp.predict_proba(X_test)
    y_test_res_encoded = np.array([res_classes.index(v) for v in y_test_res])
    
    pred_q10 = qm_goals_temp[0.1].predict(X_test)
    pred_q50 = qm_goals_temp[0.5].predict(X_test)
    pred_q90 = qm_goals_temp[0.9].predict(X_test)
    prob_goals_curr = compute_quantile_goals_distribution(pred_q10, pred_q50, pred_q90, max_goals=M_GOALS)
    
    # Métricas Dixon-Coles vs Legado
    btts_brier_curr = mean_squared_error(y_test_btts, prob_btts_curr)
    btts_brier_dc = mean_squared_error(y_test_btts, prob_btts_dc)
    btts_ece_curr = expected_calibration_error(y_test_btts, prob_btts_curr)
    btts_ece_dc = expected_calibration_error(y_test_btts, prob_btts_dc)
    
    ov_brier_curr = mean_squared_error(y_test_ov, prob_ov_curr)
    ov_brier_dc = mean_squared_error(y_test_ov, prob_ov_dc)
    ov_ece_curr = expected_calibration_error(y_test_ov, prob_ov_curr)
    ov_ece_dc = expected_calibration_error(y_test_ov, prob_ov_dc)
    
    res_logloss_curr = log_loss(y_test_res_encoded, prob_res_curr, labels=np.arange(3))
    res_logloss_dc = log_loss(y_test_res_encoded, prob_res_dc, labels=np.arange(3))
    res_ece_curr = multiclass_ece(y_test_res, prob_res_curr, res_classes)
    res_ece_dc = multiclass_ece(y_test_res, prob_res_dc, ["A", "D", "H"])
    
    y_test_goals_clipped = np.clip(y_test_goals, 0, M_GOALS).astype(int)
    g_logloss_curr = -np.mean(np.log(prob_goals_curr[np.arange(len(df_test)), y_test_goals_clipped] + 1e-15))
    g_logloss_dc = -np.mean(np.log(prob_goals_dc[np.arange(len(df_test)), y_test_goals_clipped] + 1e-15))
    
    # --------------------------------------------------------------------------
    # 3. Sanidade de Gols, Escanteios e Chutes (Viés Global)
    # --------------------------------------------------------------------------
    # Usando o Predictor oficial unificado para gerar as predições nos jogos de teste
    preds_goals_test = []
    preds_shots_test = []
    preds_hc_test = []
    preds_ac_test = []
    
    # Valores reais
    real_goals_test = []
    real_shots_test = []
    real_hc_test = []
    real_ac_test = []
    
    print("\n>> Calculando viés global nos 816 jogos do conjunto de teste...")
    for idx, row in df_test.iterrows():
        # Obter previsões
        pred = p.predict(
            row["home_team"], row["away_team"],
            neutral=bool(row["neutral"]),
            tournament=row["tournament"]
        )
        
        preds_goals_test.append(pred["gols"]["estimativa"])
        preds_shots_test.append(pred["chutes"]["estimativa"])
        preds_hc_test.append(pred["escanteios"][row["home_team"]]["estimativa"])
        preds_ac_test.append(pred["escanteios"][row["away_team"]]["estimativa"])
        
        real_goals_test.append(row["home_score"] + row["away_score"])
        real_shots_test.append(row.get("home_cur_sb_shots", 0) + row.get("away_cur_sb_shots", 0))
        real_hc_test.append(row.get("home_cur_sb_corners", 0))
        real_ac_test.append(row.get("away_cur_sb_corners", 0))
        
    print("\n" + "="*80)
    print(" DIAGNÓSTICO (a) & (d) — VERIFICAÇÃO DE VIÉS GLOBAL")
    print("="*80)
    print(f"  Target | Média Prevista | Média Real | Viés (Previsto - Real) | Status")
    print("-" * 80)
    for target, pred_arr, real_arr in [
        ("Gols Totais", preds_goals_test, real_goals_test),
        ("Total Chutes", preds_shots_test, real_shots_test),
        ("Escanteios Mandante", preds_hc_test, real_hc_test),
        ("Escanteios Visitante", preds_ac_test, real_ac_test)
    ]:
        p_mean = np.mean(pred_arr)
        r_mean = np.mean(real_arr)
        bias = p_mean - r_mean
        status = "OK" if abs(bias) < 0.25 else "WARNING"
        print(f"  {target:<20} | {p_mean:>14.4f} | {r_mean:>10.4f} | {bias:>+22.4f} | {status}")

        
    # --------------------------------------------------------------------------
    # 4. Apresentação de Métricas de Calibração (Dixon-Coles)
    # --------------------------------------------------------------------------
    print("\n" + "="*80)
    print(" DIAGNÓSTICO (b) — TABELA COMPARATIVA DE CALIBRAÇÃO (BASE API)")
    print("="*80)
    print(f"{'Mercado / Métrica':<35} | {'Modelo Atual (RF/Quant)':<25} | {'Modelo Dixon-Coles NB':<25} | {'Ganhos':<10}")
    print("-"*100)
    print(f"{'BTTS - Brier Score':<35} | {btts_brier_curr:.5f}                     | {btts_brier_dc:.5f}                     | {'+' if btts_brier_dc < btts_brier_curr else '-'}")
    print(f"{'BTTS - ECE':<35} | {btts_ece_curr:.5f}                     | {btts_ece_dc:.5f}                     | {'+' if btts_ece_dc < btts_ece_curr else '-'}")
    print("-"*100)
    print(f"{'Over 2.5 - Brier Score':<35} | {ov_brier_curr:.5f}                     | {ov_brier_dc:.5f}                     | {'+' if ov_brier_dc < ov_brier_curr else '-'}")
    print(f"{'Over 2.5 - ECE':<35} | {ov_ece_curr:.5f}                     | {ov_ece_dc:.5f}                     | {'+' if ov_ece_dc < ov_ece_curr else '-'}")
    print("-"*100)
    print(f"{'Resultado H/D/A - Log-Loss':<35} | {res_logloss_curr:.5f}                     | {res_logloss_dc:.5f}                     | {'+' if res_logloss_dc < res_logloss_curr else '-'}")
    print(f"{'Resultado H/D/A - ECE':<35} | {res_ece_curr:.5f}                     | {res_ece_dc:.5f}                     | {'+' if res_ece_dc < res_ece_curr else '-'}")
    print("-"*100)
    print(f"{'Total Gols - Log-Loss':<35} | {g_logloss_curr:.5f}                     | {g_logloss_dc:.5f}                     | {'+' if g_logloss_dc < g_logloss_curr else '-'}")
    print("="*100)

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

if __name__ == "__main__":
    main()
