import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import log_loss, accuracy_score, mean_absolute_error, mean_squared_error

def main():
    print("================================================================================")
    # 1. Load data
    df_sb = pd.read_csv("api/international_features_enriched.csv", parse_dates=["date"])
    df_ap = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"])
    
    # 2. Filter for advanced stats matches
    df_sb_adv = df_sb[df_sb["has_advanced_stats"] == 1].copy()
    df_ap_adv = df_ap[df_ap["has_advanced_stats"] == 1].copy()
    
    print(f"StatsBomb advanced stats matches: {len(df_sb_adv)}")
    print(f"API-Football advanced stats matches: {len(df_ap_adv)}")
    
    # 3. Create unique keys
    def make_key(df_):
        return (df_["date"].dt.strftime("%Y-%m-%d") + "_" + 
                df_["home_team"].str.strip().str.lower() + "_" + 
                df_["away_team"].str.strip().str.lower())
                
    df_sb_adv["key"] = make_key(df_sb_adv)
    df_ap_adv["key"] = make_key(df_ap_adv)
    
    # 4. Find intersection
    common_keys = set(df_sb_adv["key"]).intersection(set(df_ap_adv["key"]))
    print(f"Common advanced stats matches: {len(common_keys)}")
    
    if len(common_keys) == 0:
        print("[ERRO] Nenhum jogo com estatisticas avancadas em comum!")
        return
        
    df_sb_common = df_sb_adv[df_sb_adv["key"].isin(common_keys)].sort_values("key").reset_index(drop=True)
    df_ap_common = df_ap_adv[df_ap_adv["key"].isin(common_keys)].sort_values("key").reset_index(drop=True)
    
    # Double check alignment
    assert (df_sb_common["key"] == df_ap_common["key"]).all(), "Dataframes are not aligned!"
    
    # 5. Load models
    meta_sb = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
    meta_ap = json.load(open("api/model_artifacts_apifootball/meta.json", encoding="utf-8"))
    
    clf_res_sb = joblib.load("api/model_artifacts/clf_result.joblib")
    clf_btts_sb = joblib.load("api/model_artifacts/clf_btts.joblib")
    clf_ov_sb = joblib.load("api/model_artifacts/clf_over25.joblib")
    qm_sb = joblib.load("api/model_artifacts/quantile_models.joblib")
    
    clf_res_ap = joblib.load("api/model_artifacts_apifootball/clf_result.joblib")
    clf_btts_ap = joblib.load("api/model_artifacts_apifootball/clf_btts.joblib")
    clf_ov_ap = joblib.load("api/model_artifacts_apifootball/clf_over25.joblib")
    qm_ap = joblib.load("api/model_artifacts_apifootball/quantile_models.joblib")
    
    # 6. Extract predictions and calculate metrics
    def evaluate_model(df_, meta_, clf_res, clf_btts, clf_ov, qm, label):
        bf = meta_["base_feats"]
        ff = meta_["full_feats"]
        
        # Targets
        y_res = df_["result"].astype(str).values
        y_btts = df_["btts"].astype(int).values
        y_ov = df_["over_2_5"].astype(int).values
        y_goals = (df_["home_score"] + df_["away_score"]).values
        y_hc = df_["home_cur_sb_corners"].values
        y_ac = df_["away_cur_sb_corners"].values
        y_shots = (df_["home_cur_sb_shots"] + df_["away_cur_sb_shots"]).values
        
        # Predict result
        res_classes = list(clf_res.classes_)
        proba_res = clf_res.predict_proba(df_[bf])
        loss_res = log_loss(y_res, proba_res, labels=res_classes)
        pred_res = clf_res.predict(df_[bf])
        acc_res = accuracy_score(y_res, pred_res)
        
        # Predict btts
        btts_classes = list(clf_btts.classes_)
        y_btts_str = y_btts.astype(str)
        btts_classes_str = [str(c) for c in btts_classes]
        proba_btts = clf_btts.predict_proba(df_[bf])
        loss_btts = log_loss(y_btts_str, proba_btts, labels=btts_classes_str)
        pred_btts = clf_btts.predict(df_[bf]).astype(int)
        acc_btts = accuracy_score(y_btts, pred_btts)
        
        # Predict over 2.5
        ov_classes = list(clf_ov.classes_)
        y_ov_str = y_ov.astype(str)
        ov_classes_str = [str(c) for c in ov_classes]
        proba_ov = clf_ov.predict_proba(df_[bf])
        loss_ov = log_loss(y_ov_str, proba_ov, labels=ov_classes_str)
        pred_ov = clf_ov.predict(df_[bf]).astype(int)
        acc_ov = accuracy_score(y_ov, pred_ov)
        
        # Quantile helper
        def eval_quantile(qm_target, y_true, feats):
            m = qm[qm_target]
            pred_mid = m[0.5].predict(df_[feats])
            pred_lo = m[0.1].predict(df_[feats])
            pred_hi = m[0.9].predict(df_[feats])
            
            mae = mean_absolute_error(y_true, pred_mid)
            rmse = np.sqrt(mean_squared_error(y_true, pred_mid))
            
            # Coverage (fraction of true values within [pred_lo, pred_hi])
            coverage = np.mean((y_true >= pred_lo) & (y_true <= pred_hi))
            return mae, rmse, coverage
            
        g_mae, g_rmse, g_cov = eval_quantile("total_goals", y_goals, bf)
        hc_mae, hc_rmse, hc_cov = eval_quantile("home_corners", y_hc, ff)
        ac_mae, ac_rmse, ac_cov = eval_quantile("away_corners", y_ac, ff)
        sh_mae, sh_rmse, sh_cov = eval_quantile("total_shots", y_shots, ff)
        
        return {
            "Label": label,
            "Res Accuracy": acc_res,
            "Res Log-Loss": loss_res,
            "BTTS Accuracy": acc_btts,
            "BTTS Log-Loss": loss_btts,
            "Over25 Accuracy": acc_ov,
            "Over25 Log-Loss": loss_ov,
            "Goals MAE": g_mae,
            "Goals RMSE": g_rmse,
            "Goals Coverage": g_cov,
            "HCorners MAE": hc_mae,
            "HCorners RMSE": hc_rmse,
            "HCorners Coverage": hc_cov,
            "ACorners MAE": ac_mae,
            "ACorners RMSE": ac_rmse,
            "ACorners Coverage": ac_cov,
            "Shots MAE": sh_mae,
            "Shots RMSE": sh_rmse,
            "Shots Coverage": sh_cov,
        }
        
    metrics_sb = evaluate_model(df_sb_common, meta_sb, clf_res_sb, clf_btts_sb, clf_ov_sb, qm_sb, "StatsBomb (Prod)")
    metrics_ap = evaluate_model(df_ap_common, meta_ap, clf_res_ap, clf_btts_ap, clf_ov_ap, qm_ap, "API-Football")
    
    # 7. Print side-by-side comparison table
    df_metrics = pd.DataFrame([metrics_sb, metrics_ap]).set_index("Label")
    print(df_metrics.T.to_string())
    
    # Print markdown table
    print("\n\n=== TABELA DE COMPARACAO ===")
    print("| Métrica | StatsBomb (Prod) | API-Football |")
    print("|---|---|---|")
    print(f"| **Vencedor (Acurácia)** | {metrics_sb['Res Accuracy']:.4%} | {metrics_ap['Res Accuracy']:.4%} |")
    print(f"| **Vencedor (Log-Loss)** | {metrics_sb['Res Log-Loss']:.4f} | {metrics_ap['Res Log-Loss']:.4f} |")
    print(f"| **Ambas Marcam (Acurácia)** | {metrics_sb['BTTS Accuracy']:.4%} | {metrics_ap['BTTS Accuracy']:.4%} |")
    print(f"| **Ambas Marcam (Log-Loss)** | {metrics_sb['BTTS Log-Loss']:.4f} | {metrics_ap['BTTS Log-Loss']:.4f} |")
    print(f"| **Over 2.5 (Acurácia)** | {metrics_sb['Over25 Accuracy']:.4%} | {metrics_ap['Over25 Accuracy']:.4%} |")
    print(f"| **Over 2.5 (Log-Loss)** | {metrics_sb['Over25 Log-Loss']:.4f} | {metrics_ap['Over25 Log-Loss']:.4f} |")
    print(f"| **Total de Gols: MAE** | {metrics_sb['Goals MAE']:.3f} | {metrics_ap['Goals MAE']:.3f} |")
    print(f"| **Total de Gols: RMSE** | {metrics_sb['Goals RMSE']:.3f} | {metrics_ap['Goals RMSE']:.3f} |")
    print(f"| **Total de Gols: Cob. Intervalo (80%)** | {metrics_sb['Goals Coverage']:.2%} | {metrics_ap['Goals Coverage']:.2%} |")
    print(f"| **Escanteios Mandante: MAE** | {metrics_sb['HCorners MAE']:.3f} | {metrics_ap['HCorners MAE']:.3f} |")
    print(f"| **Escanteios Mandante: RMSE** | {metrics_sb['HCorners RMSE']:.3f} | {metrics_ap['HCorners RMSE']:.3f} |")
    print(f"| **Escanteios Mandante: Cob. Intervalo (80%)** | {metrics_sb['HCorners Coverage']:.2%} | {metrics_ap['HCorners Coverage']:.2%} |")
    print(f"| **Escanteios Visitante: MAE** | {metrics_sb['ACorners MAE']:.3f} | {metrics_ap['ACorners MAE']:.3f} |")
    print(f"| **Escanteios Visitante: RMSE** | {metrics_sb['ACorners RMSE']:.3f} | {metrics_ap['ACorners RMSE']:.3f} |")
    print(f"| **Escanteios Visitante: Cob. Intervalo (80%)** | {metrics_sb['ACorners Coverage']:.2%} | {metrics_ap['ACorners Coverage']:.2%} |")
    print(f"| **Finalizações: MAE** | {metrics_sb['Shots MAE']:.3f} | {metrics_ap['Shots MAE']:.3f} |")
    print(f"| **Finalizações: RMSE** | {metrics_sb['Shots RMSE']:.3f} | {metrics_ap['Shots RMSE']:.3f} |")
    print(f"| **Finalizações: Cob. Intervalo (80%)** | {metrics_sb['Shots Coverage']:.2%} | {metrics_ap['Shots Coverage']:.2%} |")

if __name__ == "__main__":
    main()
