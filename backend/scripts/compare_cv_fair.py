import os
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.metrics import log_loss, accuracy_score, mean_absolute_error, mean_squared_error
from joblib import Parallel, delayed

# Hyperparameters
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
                                              n_estimators=100, max_depth=3,
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

def evaluate_fold(df_train, df_test, base_feats, full_feats, prefix_target):
    """
    Treina os modelos em df_train e avalia no df_test.
    As colunas de estatísticas de target no df_test usam o prefixo sb_ ou sb_ (que mapeia para a API).
    Mas wait, para as estatísticas reais (alvos das predições), as colunas em df_test
    são chamadas de home_cur_sb_corners, etc. em ambos os datasets.
    """
    # Train classification models
    clf_res = fit_rf_classifier(df_train, base_feats, "result")
    clf_btts = fit_rf_classifier(df_train, base_feats, "btts")
    clf_ov = fit_rf_classifier(df_train, base_feats, "over_2_5")
    
    # Train goals model (base features)
    y_train_goals = df_train["home_score"] + df_train["away_score"]
    qm_goals = fit_quantile_models(df_train, base_feats, y_train_goals, leaf=10)
    
    # Train advanced models (only on games with stats)
    df_train_adv = df_train[df_train["has_advanced_stats"] == 1]
    
    qm_hc = fit_quantile_models(df_train_adv, full_feats, df_train_adv["home_cur_sb_corners"], leaf=10)
    qm_ac = fit_quantile_models(df_train_adv, full_feats, df_train_adv["away_cur_sb_corners"], leaf=10)
    
    train_shots = df_train_adv["home_cur_sb_shots"] + df_train_adv["away_cur_sb_shots"]
    qm_sh = fit_quantile_models(df_train_adv, full_feats, train_shots, leaf=10)
    
    train_cards = df_train_adv["home_cur_sb_cards"] + df_train_adv["away_cur_sb_cards"]
    qm_cards = fit_quantile_models(df_train_adv, full_feats, train_cards, leaf=10)
    
    # --- Predict and Evaluate on df_test ---
    # We assume df_test is already filtered to intersection so all stats are non-null
    df_test_clean = df_test.dropna(subset=[
        "home_cur_sb_corners", "away_cur_sb_corners", 
        "home_cur_sb_shots", "away_cur_sb_shots",
        "home_cur_sb_cards", "away_cur_sb_cards"
    ]).copy()
    
    if len(df_test_clean) == 0:
        return None
        
    y_test_res = df_test_clean["result"].astype(str).values
    y_test_btts = df_test_clean["btts"].astype(int).values
    y_test_ov = df_test_clean["over_2_5"].astype(int).values
    y_test_goals = (df_test_clean["home_score"] + df_test_clean["away_score"]).values
    y_test_hc = df_test_clean["home_cur_sb_corners"].values
    y_test_ac = df_test_clean["away_cur_sb_corners"].values
    y_test_shots = (df_test_clean["home_cur_sb_shots"] + df_test_clean["away_cur_sb_shots"]).values
    y_test_cards = (df_test_clean["home_cur_sb_cards"] + df_test_clean["away_cur_sb_cards"]).values
    
    # 1. Result
    res_classes = list(clf_res.classes_)
    proba_res = clf_res.predict_proba(df_test_clean[base_feats])
    loss_res = log_loss(y_test_res, proba_res, labels=res_classes)
    pred_res = clf_res.predict(df_test_clean[base_feats])
    acc_res = accuracy_score(y_test_res, pred_res)
    
    # 2. BTTS
    btts_classes_str = [str(c) for c in clf_btts.classes_]
    proba_btts = clf_btts.predict_proba(df_test_clean[base_feats])
    loss_btts = log_loss(y_test_btts.astype(str), proba_btts, labels=btts_classes_str)
    pred_btts = clf_btts.predict(df_test_clean[base_feats]).astype(int)
    acc_btts = accuracy_score(y_test_btts, pred_btts)
    
    # 3. Over 2.5
    ov_classes_str = [str(c) for c in clf_ov.classes_]
    proba_ov = clf_ov.predict_proba(df_test_clean[base_feats])
    loss_ov = log_loss(y_test_ov.astype(str), proba_ov, labels=ov_classes_str)
    pred_ov = clf_ov.predict(df_test_clean[base_feats]).astype(int)
    acc_ov = accuracy_score(y_test_ov, pred_ov)
    
    # Quantile helpers
    def eval_quantile(qm_target, y_true, feats):
        pred_mid = qm_target[0.5].predict(df_test_clean[feats])
        pred_lo = qm_target[0.1].predict(df_test_clean[feats])
        pred_hi = qm_target[0.9].predict(df_test_clean[feats])
        
        mae = mean_absolute_error(y_true, pred_mid)
        rmse = np.sqrt(mean_squared_error(y_true, pred_mid))
        coverage = np.mean((y_true >= pred_lo) & (y_true <= pred_hi))
        return mae, rmse, coverage
        
    g_mae, g_rmse, g_cov = eval_quantile(qm_goals, y_test_goals, base_feats)
    hc_mae, hc_rmse, hc_cov = eval_quantile(qm_hc, y_test_hc, full_feats)
    ac_mae, ac_rmse, ac_cov = eval_quantile(qm_ac, y_test_ac, full_feats)
    sh_mae, sh_rmse, sh_cov = eval_quantile(qm_sh, y_test_shots, full_feats)
    cards_mae, cards_rmse, cards_cov = eval_quantile(qm_cards, y_test_cards, full_feats)
    
    return {
        "Res Acc": acc_res, "Res Loss": loss_res,
        "BTTS Acc": acc_btts, "BTTS Loss": loss_btts,
        "Over25 Acc": acc_ov, "Over25 Loss": loss_ov,
        "Goals MAE": g_mae, "Goals RMSE": g_rmse, "Goals Cov": g_cov,
        "HCorners MAE": hc_mae, "HCorners RMSE": hc_rmse, "HCorners Cov": hc_cov,
        "ACorners MAE": ac_mae, "ACorners RMSE": ac_rmse, "ACorners Cov": ac_cov,
        "Shots MAE": sh_mae, "Shots RMSE": sh_rmse, "Shots Cov": sh_cov,
        "Cards MAE": cards_mae, "Cards RMSE": cards_rmse, "Cards Cov": cards_cov,
    }

def print_comparison_table(sb_agg, ap_agg, title):
    print(f"\n\n=== {title} ===")
    print("| Métrica | StatsBomb (Prod) | API-Football (Novo) |")
    print("|---|---|---|")
    
    def fmt_cell(metric_name, is_pct=False):
        mean_sb, std_sb = sb_agg.get(metric_name, (np.nan, np.nan))
        mean_ap, std_ap = ap_agg.get(metric_name, (np.nan, np.nan))
        
        if np.isnan(mean_sb):
            sb_str = "N/A"
        elif std_sb is None or np.isnan(std_sb):
            sb_str = f"{mean_sb:.2%}" if is_pct else f"{mean_sb:.4f}"
        else:
            sb_str = f"{mean_sb:.2%} ± {std_sb:.2%}" if is_pct else f"{mean_sb:.4f} ± {std_sb:.4f}"
            
        if np.isnan(mean_ap):
            ap_str = "N/A"
        elif std_ap is None or np.isnan(std_ap):
            ap_str = f"{mean_ap:.2%}" if is_pct else f"{mean_ap:.4f}"
        else:
            ap_str = f"{mean_ap:.2%} ± {std_ap:.2%}" if is_pct else f"{mean_ap:.4f} ± {std_ap:.4f}"
            
        return sb_str, ap_str
            
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
        ("Cards MAE", "Total de Cartões (MAE)", False),
        ("Cards RMSE", "Total de Cartões (RMSE)", False),
        ("Cards Cov", "Total de Cartões (Cobertura 80%)", True),
    ]
    
    for metric_key, label, is_pct in metrics_to_print:
        cell_sb, cell_ap = fmt_cell(metric_key, is_pct)
        print(f"| **{label}** | {cell_sb} | {cell_ap} |")

def main():
    print("================================================================================")
    print("FAIR HEAD-TO-HEAD BROAD VALIDATION (5-FOLD & TEMPORAL)")
    print("================================================================================")
    
    # Load datasets
    df_sb = pd.read_csv("api/international_features_enriched.csv", parse_dates=["date"])
    df_ap = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"])
    
    df_sb = df_sb.sort_values("date").reset_index(drop=True)
    df_ap = df_ap.sort_values("date").reset_index(drop=True)
    
    df_sb["key"] = make_key(df_sb)
    df_ap["key"] = make_key(df_ap)
    
    # Find intersection of games where BOTH have advanced stats
    df_sb_adv = df_sb[df_sb["has_advanced_stats"] == 1]
    df_ap_adv = df_ap[df_ap["has_advanced_stats"] == 1]
    
    common_keys = set(df_sb_adv["key"]).intersection(set(df_ap_adv["key"]))
    print(f"StatsBomb advanced: {len(df_sb_adv)}")
    print(f"API-Football advanced: {len(df_ap_adv)}")
    print(f"Common intersection advanced: {len(common_keys)}")
    
    # Ensure they exist in both dataframes
    df_sb_common = df_sb[df_sb["key"].isin(common_keys)].sort_values("key").reset_index(drop=True)
    df_ap_common = df_ap[df_ap["key"].isin(common_keys)].sort_values("key").reset_index(drop=True)
    
    # Feature lists
    all_feats_sb = numeric_features(df_sb)
    base_feats_sb, full_feats_sb = split_feature_sets(all_feats_sb)
    
    all_feats_ap = numeric_features(df_ap)
    base_feats_ap, full_feats_ap = split_feature_sets(all_feats_ap)
    
    # ==========================================================================
    # MODALIDADE 1: 5-FOLD CV FAIR (TEST SET RESTRICTED TO INTERSECTION)
    # ==========================================================================
    print("\n>> Running Fair 5-Fold CV...")
    
    # We split the common intersection keys into 5 folds
    common_keys_list = sorted(list(common_keys))
    kf = KFold(n_splits=5, shuffle=True, random_state=RS)
    
    def run_fold_sb(train_idx, test_idx):
        test_keys = [common_keys_list[i] for i in test_idx]
        df_test = df_sb_common[df_sb_common["key"].isin(test_keys)].reset_index(drop=True)
        df_train = df_sb[~df_sb["key"].isin(test_keys)].reset_index(drop=True)
        return evaluate_fold(df_train, df_test, base_feats_sb, full_feats_sb, "StatsBomb")
        
    sb_metrics_list = Parallel(n_jobs=-1)(
        delayed(run_fold_sb)(train_idx, test_idx)
        for train_idx, test_idx in kf.split(common_keys_list)
    )
    sb_metrics_list = [res for res in sb_metrics_list if res is not None]
    
    def run_fold_ap(train_idx, test_idx):
        test_keys = [common_keys_list[i] for i in test_idx]
        df_test = df_ap_common[df_ap_common["key"].isin(test_keys)].reset_index(drop=True)
        # Train on API-Football broad dataset, excluding the test keys of this fold
        df_train = df_ap[~df_ap["key"].isin(test_keys)].reset_index(drop=True)
        return evaluate_fold(df_train, df_test, base_feats_ap, full_feats_ap, "API-Football")
        
    ap_metrics_list = Parallel(n_jobs=-1)(
        delayed(run_fold_ap)(train_idx, test_idx)
        for train_idx, test_idx in kf.split(common_keys_list)
    )
    ap_metrics_list = [res for res in ap_metrics_list if res is not None]
    
    def aggregate(metrics_list):
        agg = {}
        if not metrics_list: return agg
        keys = metrics_list[0].keys()
        for k in keys:
            vals = [m[k] for m in metrics_list]
            agg[k] = (np.mean(vals), np.std(vals))
        return agg
        
    sb_agg_cv = aggregate(sb_metrics_list)
    ap_agg_cv = aggregate(ap_metrics_list)
    
    print_comparison_table(sb_agg_cv, ap_agg_cv, "MODALIDADE 1: VALIDAÇÃO CRUZADA 5-FOLD JUSTA (TESTE COMUM INTERSECÇÃO)")
    
    # ==========================================================================
    # MODALIDADE 2: VALIDAÇÃO TEMPORAL JUSTA (TESTE COMUM APÓS CUTOFF)
    # ==========================================================================
    print("\n>> Running Fair Temporal Validation...")
    
    # We sort intersection keys by date to get chronological split
    df_intersection_sorted = df_sb_common.sort_values("date").reset_index(drop=True)
    n_train_common = int(len(df_intersection_sorted) * 0.8)
    cutoff_date = df_intersection_sorted.iloc[n_train_common]["date"]
    print(f"Fair Temporal Cutoff Date: {cutoff_date.strftime('%Y-%m-%d')}")
    
    # Test set: matches in the intersection after cutoff
    test_keys = df_intersection_sorted[df_intersection_sorted["date"] > cutoff_date]["key"].values
    print(f"Temporal Test Set Size: {len(test_keys)}")
    
    # StatsBomb Temporal
    df_train_sb_t = df_sb[df_sb["date"] <= cutoff_date].reset_index(drop=True)
    df_test_sb_t = df_sb_common[df_sb_common["key"].isin(test_keys)].reset_index(drop=True)
    sb_res_t = evaluate_fold(df_train_sb_t, df_test_sb_t, base_feats_sb, full_feats_sb, "StatsBomb")
    
    # API-Football Temporal
    df_train_ap_t = df_ap[df_ap["date"] <= cutoff_date].reset_index(drop=True)
    df_test_ap_t = df_ap_common[df_ap_common["key"].isin(test_keys)].reset_index(drop=True)
    ap_res_t = evaluate_fold(df_train_ap_t, df_test_ap_t, base_feats_ap, full_feats_ap, "API-Football")
    
    sb_agg_t = {k: (v, np.nan) for k, v in sb_res_t.items()} if sb_res_t else {}
    ap_agg_t = {k: (v, np.nan) for k, v in ap_res_t.items()} if ap_res_t else {}
    
    print_comparison_table(sb_agg_t, ap_agg_t, "MODALIDADE 2: VALIDAÇÃO TEMPORAL JUSTA (TESTE COMUM FUTURO)")

if __name__ == "__main__":
    main()
