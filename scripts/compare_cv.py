import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.metrics import log_loss, accuracy_score, mean_absolute_error, mean_squared_error

# Define hyperparameters
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
        ("clf", RandomForestClassifier(n_estimators=500, max_depth=10, min_samples_leaf=5,
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

def make_key(df_):
    return (df_["date"].dt.strftime("%Y-%m-%d") + "_" + 
            df_["home_team"].str.strip().str.lower() + "_" + 
            df_["away_team"].str.strip().str.lower())

def evaluate_fold(df_train, df_test, base_feats, full_feats, model_label):
    # Train models
    clf_res = fit_rf_classifier(df_train, base_feats, "result")
    clf_btts = fit_rf_classifier(df_train, base_feats, "btts")
    clf_ov = fit_rf_classifier(df_train, base_feats, "over_2_5")
    
    # Goals quantile model (leaf=10)
    y_train_goals = df_train["home_score"] + df_train["away_score"]
    qm_goals = fit_quantile_models(df_train, base_feats, y_train_goals, leaf=10)
    
    # Corners/Shots models (leaf=10 for StatsBomb, leaf=1 for API-Football)
    leaf_adv = 10 if model_label == "StatsBomb" else 1
    
    df_train_adv = df_train[df_train["has_advanced_stats"] == 1]
    
    qm_hc = fit_quantile_models(df_train_adv, full_feats, df_train_adv["home_cur_sb_corners"], leaf=leaf_adv)
    qm_ac = fit_quantile_models(df_train_adv, full_feats, df_train_adv["away_cur_sb_corners"], leaf=leaf_adv)
    
    train_shots = df_train_adv["home_cur_sb_shots"] + df_train_adv["away_cur_sb_shots"]
    qm_sh = fit_quantile_models(df_train_adv, full_feats, train_shots, leaf=leaf_adv)
    
    # --- Predict and Evaluate on df_test ---
    y_test_res = df_test["result"].astype(str).values
    y_test_btts = df_test["btts"].astype(int).values
    y_test_ov = df_test["over_2_5"].astype(int).values
    y_test_goals = (df_test["home_score"] + df_test["away_score"]).values
    y_test_hc = df_test["home_cur_sb_corners"].values
    y_test_ac = df_test["away_cur_sb_corners"].values
    y_test_shots = (df_test["home_cur_sb_shots"] + df_test["away_cur_sb_shots"]).values
    
    # 1. Result
    res_classes = list(clf_res.classes_)
    proba_res = clf_res.predict_proba(df_test[base_feats])
    # Ensure log_loss is computed with correct labels
    loss_res = log_loss(y_test_res, proba_res, labels=res_classes)
    pred_res = clf_res.predict(df_test[base_feats])
    acc_res = accuracy_score(y_test_res, pred_res)
    
    # 2. BTTS
    btts_classes_str = [str(c) for c in clf_btts.classes_]
    y_test_btts_str = y_test_btts.astype(str)
    proba_btts = clf_btts.predict_proba(df_test[base_feats])
    loss_btts = log_loss(y_test_btts_str, proba_btts, labels=btts_classes_str)
    pred_btts = clf_btts.predict(df_test[base_feats]).astype(int)
    acc_btts = accuracy_score(y_test_btts, pred_btts)
    
    # 3. Over 2.5
    ov_classes_str = [str(c) for c in clf_ov.classes_]
    y_test_ov_str = y_test_ov.astype(str)
    proba_ov = clf_ov.predict_proba(df_test[base_feats])
    loss_ov = log_loss(y_test_ov_str, proba_ov, labels=ov_classes_str)
    pred_ov = clf_ov.predict(df_test[base_feats]).astype(int)
    acc_ov = accuracy_score(y_test_ov, pred_ov)
    
    # Quantile helper
    def eval_quantile(qm_target, y_true, feats):
        pred_mid = qm_target[0.5].predict(df_test[feats])
        pred_lo = qm_target[0.1].predict(df_test[feats])
        pred_hi = qm_target[0.9].predict(df_test[feats])
        
        mae = mean_absolute_error(y_true, pred_mid)
        rmse = np.sqrt(mean_squared_error(y_true, pred_mid))
        coverage = np.mean((y_true >= pred_lo) & (y_true <= pred_hi))
        return mae, rmse, coverage
        
    g_mae, g_rmse, g_cov = eval_quantile(qm_goals, y_test_goals, base_feats)
    hc_mae, hc_rmse, hc_cov = eval_quantile(qm_hc, y_test_hc, full_feats)
    ac_mae, ac_rmse, ac_cov = eval_quantile(qm_ac, y_test_ac, full_feats)
    sh_mae, sh_rmse, sh_cov = eval_quantile(qm_sh, y_test_shots, full_feats)
    
    return {
        "Res Acc": acc_res, "Res Loss": loss_res,
        "BTTS Acc": acc_btts, "BTTS Loss": loss_btts,
        "Over25 Acc": acc_ov, "Over25 Loss": loss_ov,
        "Goals MAE": g_mae, "Goals RMSE": g_rmse, "Goals Cov": g_cov,
        "HCorners MAE": hc_mae, "HCorners RMSE": hc_rmse, "HCorners Cov": hc_cov,
        "ACorners MAE": ac_mae, "ACorners RMSE": ac_rmse, "ACorners Cov": ac_cov,
        "Shots MAE": sh_mae, "Shots RMSE": sh_rmse, "Shots Cov": sh_cov,
    }

def main():
    print("================================================================================")
    print("INICIANDO VALIDAÇÃO CRUZADA 5-FOLD (TESTE EXCLUSIVO COPA 2022)")
    print("================================================================================")
    
    # Load datasets
    df_sb = pd.read_csv("api/international_features_enriched.csv", parse_dates=["date"])
    df_ap = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"])
    
    df_sb["key"] = make_key(df_sb)
    df_ap["key"] = make_key(df_ap)
    
    # Common matches with advanced stats
    df_sb_adv = df_sb[df_sb["has_advanced_stats"] == 1]
    df_ap_adv = df_ap[df_ap["has_advanced_stats"] == 1]
    
    common_keys = sorted(list(set(df_sb_adv["key"]).intersection(set(df_ap_adv["key"]))))
    print(f"Total de jogos de teste comuns (Copa 2022): {len(common_keys)}")
    
    # Prepare folds
    kf = KFold(n_splits=5, shuffle=True, random_state=RS)
    common_keys = np.array(common_keys)
    
    sb_metrics_list = []
    ap_metrics_list = []
    
    # Features lists
    all_feats_sb = numeric_features(df_sb)
    base_feats_sb, full_feats_sb = split_feature_sets(all_feats_sb)
    
    all_feats_ap = numeric_features(df_ap)
    base_feats_ap, full_feats_ap = split_feature_sets(all_feats_ap)
    
    for fold, (train_idx, test_idx) in enumerate(kf.split(common_keys), start=1):
        print(f"\n--- FOLD {fold}/5 ---")
        test_keys_fold = common_keys[test_idx]
        print(f"Jogos de teste neste fold: {len(test_keys_fold)}")
        
        # Test sets
        df_test_sb = df_sb[df_sb["key"].isin(test_keys_fold)].sort_values("key").reset_index(drop=True)
        df_test_ap = df_ap[df_ap["key"].isin(test_keys_fold)].sort_values("key").reset_index(drop=True)
        
        # Train sets (exclude test keys to prevent leakage)
        df_train_sb = df_sb[~df_sb["key"].isin(test_keys_fold)].reset_index(drop=True)
        df_train_ap = df_ap[~df_ap["key"].isin(test_keys_fold)].reset_index(drop=True)
        
        # Evaluate StatsBomb
        sb_res = evaluate_fold(df_train_sb, df_test_sb, base_feats_sb, full_feats_sb, "StatsBomb")
        sb_metrics_list.append(sb_res)
        
        # Evaluate API-Football
        ap_res = evaluate_fold(df_train_ap, df_test_ap, base_feats_ap, full_feats_ap, "API-Football")
        ap_metrics_list.append(ap_res)
        
    # Aggregate results
    def aggregate(metrics_list):
        agg = {}
        keys = metrics_list[0].keys()
        for k in keys:
            vals = [m[k] for m in metrics_list]
            agg[k] = (np.mean(vals), np.std(vals))
        return agg
        
    sb_agg = aggregate(sb_metrics_list)
    ap_agg = aggregate(ap_metrics_list)
    
    # Print markdown table
    print("\n\n=== TABELA DE VALIDAÇÃO CRUZADA (Média ± Desvio) ===")
    print("| Métrica | StatsBomb (Prod) | API-Football |")
    print("|---|---|---|")
    
    def fmt_cell(metric_name, is_pct=False):
        mean_sb, std_sb = sb_agg[metric_name]
        mean_ap, std_ap = ap_agg[metric_name]
        if is_pct:
            return f"{mean_sb:.2%} ± {std_sb:.2%}", f"{mean_ap:.2%} ± {std_ap:.2%}"
        else:
            return f"{mean_sb:.4f} ± {std_sb:.4f}", f"{mean_ap:.4f} ± {std_ap:.4f}"
            
    metrics_to_print = [
        ("Res Acc", "Vencedor (Acurácia)", True),
        ("Res Loss", "Vencedor (Log-Loss)", False),
        ("BTTS Acc", "Ambas Marcam (Acurácia)", True),
        ("BTTS Loss", "Ambas Marcam (Log-Loss)", False),
        ("Over25 Acc", "Over 2.5 (Acurácia)", True),
        ("Over25 Loss", "Over 2.5 (Log-Loss)", False),
        ("Goals MAE", "Total de Gols (MAE)", False),
        ("Goals RMSE", "Total de Gols (RMSE)", False),
        ("Goals Cov", "Total de Gols (Cobertura 80%)", True),
        ("HCorners MAE", "Escanteios Mandante (MAE)", False),
        ("HCorners RMSE", "Escanteios Mandante (RMSE)", False),
        ("HCorners Cov", "Escanteios Mandante (Cobertura 80%)", True),
        ("ACorners MAE", "Escanteios Visitante (MAE)", False),
        ("ACorners RMSE", "Escanteios Visitante (RMSE)", False),
        ("ACorners Cov", "Escanteios Visitante (Cobertura 80%)", True),
        ("Shots MAE", "Finalizações (MAE)", False),
        ("Shots RMSE", "Finalizações (RMSE)", False),
        ("Shots Cov", "Finalizações (Cobertura 80%)", True),
    ]
    
    for metric_key, label, is_pct in metrics_to_print:
        cell_sb, cell_ap = fmt_cell(metric_key, is_pct)
        print(f"| **{label}** | {cell_sb} | {cell_ap} |")

if __name__ == "__main__":
    main()
