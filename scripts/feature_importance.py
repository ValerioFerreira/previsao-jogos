#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/feature_importance.py
==============================
Executa análise de importância de features offline e robusta para 11 alvos:
  - Resultado (multiclasse)
  - Gols (total, 1T, 2T)
  - Escanteios (mandante, visitante)
  - Chutes (total)
  - Chutes ao gol (total)
  - Cartões (total, 1T, 2T)

Métodos:
  - SHAP values (TreeExplainer com agregação multiclasse e amostragem de teste)
  - Importância por permutação (5 folds, neg_MAE ou neg_log_loss)
  - Importância Gini nativa
  - Informação mútua
  - Correlações de Pearson e Spearman

Tratamento de multicolinearidade por agrupamento de correlação (|r| > 0.85).
Salva os gráficos SHAP em api/model_artifacts_apifootball/plots/.
Gera relatório detalhado em api/model_artifacts_apifootball/feature_importance_report.json.
"""

import os
import gzip
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
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.model_selection import KFold, StratifiedKFold
import shap

warnings.filterwarnings("ignore")

# Caminhos e Constantes
CSV_PATH = Path("international_features_enriched_apifootball.csv")
FIXTURES_DIR = Path("data/raw/fixtures")
OUT_DIR = Path("api/model_artifacts_apifootball")
PLOTS_DIR = OUT_DIR / "plots"
REPORT_PATH = OUT_DIR / "feature_importance_report.json"

RS = 42

LEAK_OR_ID = {
    "match_id", "date", "home_team", "away_team", "city", "country", "tournament",
    "home_score", "away_score", "goal_diff", "total_goals", "result",
    "home_win", "away_win", "draw", "btts", "over_2_5",
    "has_advanced_stats", "year", "month", "decade",
}

# Normalização de nomes (API-Football -> martj42/international_results)
TEAM_NAME_MAP = {
    "Korea Republic":           "South Korea",
    "IR Iran":                  "Iran",
    "China PR":                 "China",
    "Kyrgyz Republic":          "Kyrgyzstan",
    "North Macedonia":          "North Macedonia",
    "FYR Macedonia":            "North Macedonia",
    "Cote d'Ivoire":            "Ivory Coast",
    "Congo DR":                 "DR Congo",
    "USA":                      "United States",
    "Trinidad & Tobago":        "Trinidad and Tobago",
    "Antigua & Barbuda":        "Antigua and Barbuda",
    "St Kitts & Nevis":         "Saint Kitts and Nevis",
    "St. Kitts and Nevis":      "Saint Kitts and Nevis",
    "St Vincent & Grenadines":  "Saint Vincent and the Grenadines",
    "St. Vincent / Grenadines": "Saint Vincent and the Grenadines",
    "Czechia":                  "Czech Republic",
    "Czech Republic":           "Czech Republic",
    "Türkiye":                  "Turkey",
    "Turkey":                   "Turkey",
    "Bosnia-Herzegovina":       "Bosnia and Herzegovina",
    "Bosnia & Herzegovina":     "Bosnia and Herzegovina",
    "Cape Verde Islands":       "Cape Verde",
    "Cape Verde":               "Cape Verde",
    "Republic of Ireland":      "Republic of Ireland",
    "Rep. of Ireland":          "Republic of Ireland",
    "Rep. Of Ireland":          "Republic of Ireland",
    "Sao Tome and Principe":    "São Tomé and Príncipe",
    "São Tomé and Príncipe":    "São Tomé and Príncipe",
    "St. Lucia":                "Saint Lucia",
    "French Guyana":            "French Guiana",
    "US Virgin Islands":        "United States Virgin Islands",
    "andorra":                  "Andorra",
    "Chinese Taipei":           "Taiwan",
    "Mação":                    "Macau",
}

def normalize_team(name):
    return TEAM_NAME_MAP.get(name, name)

def scan_raw_fixtures():
    print(">> Escaneando arquivos json.gz crus para indexação...")
    gz_files = list(FIXTURES_DIR.glob("**/*.json.gz"))
    raw_index = {}
    for path in gz_files:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
            teams = data.get("teams", {})
            home = normalize_team(teams.get("home", {}).get("name", ""))
            away = normalize_team(teams.get("away", {}).get("name", ""))
            fixture = data.get("fixture", {})
            date_str = fixture.get("date", "")[:10]
            if home and away and date_str:
                raw_index[(date_str, home, away)] = data
        except Exception:
            pass
    print(f"   Indexed {len(raw_index)} raw matches.")
    return raw_index

def build_halftime_and_event_targets(df, raw_index):
    print(">> Construindo alvos por tempo e consolidados adicionais...")
    goals_1h_list = []
    goals_2h_list = []
    cards_1h_list = []
    cards_2h_list = []
    
    matched_count = 0
    
    for idx, row in df.iterrows():
        ht = row["home_team"]
        at = row["away_team"]
        d = pd.to_datetime(row["date"])
        
        data = None
        for delta in [0, 1, -1, 2, -2]:
            c_d = d + pd.Timedelta(days=delta)
            c_ds = c_d.strftime("%Y-%m-%d")
            
            # Regular
            if (c_ds, ht, at) in raw_index:
                data = raw_index[(c_ds, ht, at)]
                break
            # Swapped
            if (c_ds, at, ht) in raw_index:
                data = raw_index[(c_ds, at, ht)]
                break
                
        if data is None:
            goals_1h_list.append(np.nan)
            goals_2h_list.append(np.nan)
            cards_1h_list.append(np.nan)
            cards_2h_list.append(np.nan)
            continue
            
        matched_count += 1
        
        # 1. Gols 1T / 2T
        score = data.get("score", {})
        halftime = score.get("halftime", {})
        
        home_ht = halftime.get("home")
        away_ht = halftime.get("away")
        
        total_goals_row = int(row["home_score"]) + int(row["away_score"])
        
        if home_ht is not None and away_ht is not None:
            g_1h = int(home_ht) + int(away_ht)
            g_2h = max(0, total_goals_row - g_1h)
            goals_1h_list.append(float(g_1h))
            goals_2h_list.append(float(g_2h))
        else:
            # Fallback de eventos
            events = data.get("events", [])
            g_1h = 0
            for ev in events:
                if ev.get("type") == "Goal":
                    elapsed = ev.get("time", {}).get("elapsed", 0)
                    if elapsed <= 45:
                        g_1h += 1
            g_2h = max(0, total_goals_row - g_1h)
            goals_1h_list.append(float(g_1h))
            goals_2h_list.append(float(g_2h))
            
        # 2. Cartões 1T / 2T
        events = data.get("events", [])
        c_1h = 0
        c_2h = 0
        for ev in events:
            if ev.get("type") == "Card":
                t = ev.get("time", {})
                elapsed = t.get("elapsed", 0)
                # 1H logic: elapsed <= 45
                if elapsed <= 45:
                    c_1h += 1
                else:
                    c_2h += 1
                    
        # sb_cards original
        sb_c = row.get("sb_cards")
        if pd.notna(sb_c):
            total_ev_c = c_1h + c_2h
            if total_ev_c > 0:
                c_1h_clean = min(c_1h, int(sb_c))
                c_2h_clean = int(sb_c) - c_1h_clean
                cards_1h_list.append(float(c_1h_clean))
                cards_2h_list.append(float(c_2h_clean))
            else:
                cards_1h_list.append(0.0)
                cards_2h_list.append(float(sb_c))
        else:
            if row["has_advanced_stats"] == 1:
                cards_1h_list.append(float(c_1h))
                cards_2h_list.append(float(c_2h))
            else:
                cards_1h_list.append(np.nan)
                cards_2h_list.append(np.nan)
                
    df["goals_1h"] = goals_1h_list
    df["goals_2h"] = goals_2h_list
    df["cards_1h"] = cards_1h_list
    df["cards_2h"] = cards_2h_list
    
    # Adicionais consolidados
    df["total_shots"] = df["home_cur_sb_shots"] + df["away_cur_sb_shots"]
    df["total_shots_on_target"] = df["home_cur_sb_shots_on_target"] + df["away_cur_sb_shots_on_target"]
    df["total_cards"] = df["home_cur_sb_cards"] + df["away_cur_sb_cards"]
    
    print(f"   Criados alvos com sucesso. Jogos mapeados: {matched_count} / {len(df)}")
    return df

def get_feature_lists(df):
    all_numeric = []
    for c in df.columns:
        if c in LEAK_OR_ID:
            continue
        if c.startswith(("home_cur_", "away_cur_", "diff_cur_")):
            continue
        if c in ["goals_1h", "goals_2h", "cards_1h", "cards_2h", "total_shots", "total_shots_on_target", "total_cards"]:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            all_numeric.append(c)
            
    base_feats = [c for c in all_numeric if "sb_" not in c]
    full_feats = list(all_numeric)
    return base_feats, full_feats

def find_collinear_groups(X, threshold=0.85):
    # Imputa antes de calcular a correlação
    imp = SimpleImputer(strategy="median")
    X_imp = pd.DataFrame(imp.fit_transform(X), columns=X.columns)
    corr_matrix = X_imp.corr().abs()
    
    features = list(X.columns)
    adj = {f: set() for f in features}
    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            f1 = features[i]
            f2 = features[j]
            if corr_matrix.loc[f1, f2] > threshold:
                adj[f1].add(f2)
                adj[f2].add(f1)
                
    visited = set()
    groups = []
    for f in features:
        if f not in visited:
            comp = []
            queue = [f]
            visited.add(f)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            groups.append(comp)
            
    return groups

def analyze_target(df, target_name, info, base_feats, full_feats, collinear_groups):
    print(f"\n>>> Processando alvo: {target_name} ({info['type']})")
    
    target_col = info["col"]
    features_type = info["features"]
    dataset_type = info["dataset"]
    target_type = info["type"]
    
    # 1. Filtrar dataset
    if dataset_type == "advanced":
        sub = df[df["has_advanced_stats"] == 1].copy()
    else:
        sub = df.copy()
        
    sub = sub.dropna(subset=[target_col])
    
    # Selecionar features
    feats = base_feats if features_type == "base" else full_feats
    X = sub[feats]
    y = sub[target_col]
    
    n_samples = len(sub)
    print(f"    Registros para treino: {n_samples} | Features: {len(feats)}")
    
    if n_samples < 50:
        print("    [AVISO] Dados insuficientes. Pulando.")
        return None
        
    # Inicializar contêineres de importância
    shap_fold_runs = []
    perm_fold_runs = []
    gini_fold_runs = []
    
    # 2. Configurar Cross-Validation
    if target_type == "classification":
        y_str = y.astype(str)
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RS)
        splits = list(cv.split(X, y_str))
    else:
        cv = KFold(n_splits=5, shuffle=True, random_state=RS)
        splits = list(cv.split(X, y))
        
    # Loops de Fold
    for fold, (train_idx, test_idx) in enumerate(splits, start=1):
        # Split
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]
        
        # Pipeline Imputer
        imp = SimpleImputer(strategy="median")
        X_train_imp = imp.fit_transform(X_train)
        X_test_imp = imp.transform(X_test)
        
        # Model
        if target_type == "classification":
            y_train_fit = y_train.astype(str)
            y_test_fit = y_test.astype(str)
            model = RandomForestClassifier(n_estimators=30, max_depth=10,
                                           min_samples_leaf=5, class_weight="balanced",
                                           random_state=RS, n_jobs=1)
            model.fit(X_train_imp, y_train_fit)
            scoring = "neg_log_loss"
        else:
            y_train_fit = y_train.astype(float)
            y_test_fit = y_test.astype(float)
            model = RandomForestRegressor(n_estimators=30, max_depth=10,
                                          min_samples_leaf=5, random_state=RS, n_jobs=1)
            model.fit(X_train_imp, y_train_fit)
            scoring = "neg_mean_absolute_error"
            
        # a) Native Gini Importance
        gini_fold_runs.append(model.feature_importances_)
        
        # b) SHAP values & Permutation sampling (Amostrando teste para garantir velocidade)
        X_test_shap_df = pd.DataFrame(X_test_imp, columns=feats)
        if len(X_test_shap_df) > 300:
            if target_type == "classification":
                probs = y_test_fit.value_counts(normalize=True)
                w = probs[y_test_fit].values
                w = w / w.sum()
                idx_sample = np.random.choice(len(X_test_shap_df), size=300, replace=False, p=w)
            else:
                idx_sample = np.random.choice(len(X_test_shap_df), size=300, replace=False)
            X_test_shap = X_test_shap_df.iloc[idx_sample]
            y_test_shap = y_test_fit.iloc[idx_sample]
        else:
            X_test_shap = X_test_shap_df
            y_test_shap = y_test_fit

        # c) Permutation Importance
        perm = permutation_importance(model, X_test_shap.values, y_test_shap, scoring=scoring,
                                      n_repeats=1, random_state=RS, n_jobs=-1)
        perm_fold_runs.append(perm.importances_mean)
        
        # d) SHAP values
        explainer = shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")
        shap_vals = explainer.shap_values(X_test_shap, check_additivity=False)
        
        # Agregação multiclasse / binária
        if isinstance(shap_vals, list):
            mean_abs = np.zeros(shap_vals[0].shape[1])
            for c_shap in shap_vals:
                mean_abs += np.abs(c_shap).mean(axis=0)
            mean_abs /= len(shap_vals)
        else:
            if len(shap_vals.shape) == 3: # Novo formato do shap para multiclasse pode retornar shape (n_samples, n_features, n_classes)
                mean_abs = np.abs(shap_vals).mean(axis=(0, 2))
            else:
                mean_abs = np.abs(shap_vals).mean(axis=0)
                
        # Para salvar shap values globais para plotar no fold 1
        if fold == 1:
            fold1_model = model
            fold1_shap_vals = shap_vals
            fold1_X_test_shap = X_test_shap
            
        shap_fold_runs.append(mean_abs)
        
    # Calcular Médias e Desvios
    gini_mean = np.mean(gini_fold_runs, axis=0)
    gini_std = np.std(gini_fold_runs, axis=0)
    
    perm_mean = np.mean(perm_fold_runs, axis=0)
    perm_std = np.std(perm_fold_runs, axis=0)
    
    shap_mean = np.mean(shap_fold_runs, axis=0)
    shap_std = np.std(shap_fold_runs, axis=0)
    
    # 3. Informação Mútua e Correlação (Global)
    imp_global = SimpleImputer(strategy="median")
    X_global_imp = pd.DataFrame(imp_global.fit_transform(X), columns=feats)
    
    # Amostra global para MI se > 1000 para acelerar
    if len(X_global_imp) > 1000:
        if target_type == "classification":
            probs = y.value_counts(normalize=True)
            w = probs[y].values
            w = w / w.sum()
            idx_mi = np.random.choice(len(X_global_imp), size=1000, replace=False, p=w)
        else:
            idx_mi = np.random.choice(len(X_global_imp), size=1000, replace=False)
        X_mi = X_global_imp.iloc[idx_mi]
        y_mi = y.iloc[idx_mi]
    else:
        X_mi = X_global_imp
        y_mi = y
        
    if target_type == "classification":
        mi_scores = mutual_info_classif(X_mi, y_mi.astype(str), random_state=RS)
        # Mapeia resultado para ordinal para correlação
        if target_col == "result":
            y_num = y.map({"H": 1, "D": 0, "A": -1}).fillna(0).astype(float)
        else:
            y_num = y.astype(float)
    else:
        mi_scores = mutual_info_regression(X_mi, y_mi.astype(float), random_state=RS)
        y_num = y.astype(float)
        
    pearson_corr = [X_global_imp[col].corr(y_num, method="pearson") for col in feats]
    spearman_corr = [X_global_imp[col].corr(y_num, method="spearman") for col in feats]
    
    # 4. Criar Tabela Consolidada
    res_df = pd.DataFrame(index=feats)
    res_df["shap_mean"] = shap_mean
    res_df["shap_std"] = shap_std
    res_df["perm_mean"] = perm_mean
    res_df["perm_std"] = perm_std
    res_df["gini_mean"] = gini_mean
    res_df["gini_std"] = gini_std
    res_df["mutual_info"] = mi_scores
    res_df["pearson_corr"] = pearson_corr
    res_df["spearman_corr"] = spearman_corr
    
    # Normalização e Consenso (Soma de importâncias SHAP e Permutação normalizadas)
    res_df["shap_norm"] = res_df["shap_mean"] / res_df["shap_mean"].sum()
    perm_clean = res_df["perm_mean"].clip(lower=0.0) # ignora quedas negativas de performance
    if perm_clean.sum() > 0:
        res_df["perm_norm"] = perm_clean / perm_clean.sum()
    else:
        res_df["perm_norm"] = 1.0 / len(feats)
        
    res_df["consensus"] = (res_df["shap_norm"] + res_df["perm_norm"]) / 2.0
    res_df = res_df.sort_values("consensus", ascending=False)
    
    # 5. Mapear Grupos Colineares
    col_group_map = {}
    for group_idx, grp in enumerate(collinear_groups):
        grp_intersection = [f for f in grp if f in feats]
        if len(grp_intersection) > 1:
            for f in grp_intersection:
                col_group_map[f] = {
                    "group_id": f"Grupo_{group_idx}",
                    "size": len(grp_intersection),
                    "members": grp_intersection
                }
                
    res_df["group_id"] = [col_group_map[f]["group_id"] if f in col_group_map else "Individual" for f in res_df.index]
    
    # 6. Salvar Gráficos SHAP (usando Fold 1)
    os.makedirs(PLOTS_DIR, exist_ok=True)
    
    # Summary Plot
    plt.figure(figsize=(10, 6))
    if target_type == "classification" and isinstance(fold1_shap_vals, list):
        # Multiclass summary plot (bar)
        shap.summary_plot(fold1_shap_vals, fold1_X_test_shap, plot_type="bar", show=False)
        plt.title(f"SHAP Multiclass Bar - {target_name}")
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / f"shap_summary_bar_{target_name}.png", dpi=150)
        plt.close()
        
        # Também plota o dot plot para a classe Vitória Mandante (classe 0 - "H")
        class_idx = 0
        if "H" in fold1_model.classes_:
            class_idx = list(fold1_model.classes_).index("H")
        
        plt.figure(figsize=(10, 6))
        shap.summary_plot(fold1_shap_vals[class_idx], fold1_X_test_shap, show=False)
        plt.title(f"SHAP Summary (Classe Vitória Mandante) - {target_name}")
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / f"shap_summary_{target_name}.png", dpi=150)
        plt.close()
    else:
        # Regression or single output
        shap.summary_plot(fold1_shap_vals, fold1_X_test_shap, show=False)
        plt.title(f"SHAP Summary - {target_name}")
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / f"shap_summary_{target_name}.png", dpi=150)
        plt.close()
        
    # Dependence Plot para as top 2 features individuais
    top_features = list(res_df.index[:2])
    for rank, feat in enumerate(top_features, start=1):
        plt.figure(figsize=(8, 5))
        try:
            # Para multiclasse
            if target_type == "classification" and isinstance(fold1_shap_vals, list):
                class_idx = 0
                if "H" in fold1_model.classes_:
                    class_idx = list(fold1_model.classes_).index("H")
                shap.dependence_plot(feat, fold1_shap_vals[class_idx], fold1_X_test_shap, show=False)
            else:
                shap.dependence_plot(feat, fold1_shap_vals, fold1_X_test_shap, show=False)
                
            plt.title(f"SHAP Dependence ({feat}) - {target_name}")
            plt.tight_layout()
            plt.savefig(PLOTS_DIR / f"shap_dependence_{target_name}_top{rank}.png", dpi=150)
        except Exception as e:
            print(f"      [Aviso] Falha ao gerar dependence plot para {feat}: {e}")
        plt.close()
        
    # Converter resultados para JSON serialize
    records = []
    for f, r in res_df.iterrows():
        records.append({
            "feature": f,
            "shap_mean": float(r["shap_mean"]),
            "shap_std": float(r["shap_std"]),
            "perm_mean": float(r["perm_mean"]),
            "perm_std": float(r["perm_std"]),
            "gini_mean": float(r["gini_mean"]),
            "gini_std": float(r["gini_std"]),
            "mutual_info": float(r["mutual_info"]),
            "pearson_corr": float(r["pearson_corr"]) if pd.notna(r["pearson_corr"]) else 0.0,
            "spearman_corr": float(r["spearman_corr"]) if pd.notna(r["spearman_corr"]) else 0.0,
            "consensus": float(r["consensus"]),
            "group_id": r["group_id"],
            "collinear_members": col_group_map[f]["members"] if f in col_group_map else [f]
        })
        
    return {
        "target": target_name,
        "n_samples": n_samples,
        "rankings": records
    }

def main():
    print("================================================================================")
    print("ANALISE DE IMPORTÂNCIA DE FEATURES (feature_importance.py)")
    print("================================================================================")
    
    if not CSV_PATH.exists():
        print(f"[ERRO] {CSV_PATH} não encontrado. Abortando.")
        return
        
    raw_index = scan_raw_fixtures()
    
    # 1. Carregar e enriquecer com alvos reconstruídos
    df = pd.read_csv(CSV_PATH)
    df = build_halftime_and_event_targets(df, raw_index)
    
    # 2. Obter listas de features
    base_feats, full_feats = get_feature_lists(df)
    print(f">> Features Base (sem SB): {len(base_feats)}")
    print(f">> Features Completas (com SB): {len(full_feats)}")
    
    # 3. Detectar grupos colineares usando features completas
    print(">> Calculando agrupamentos de multicolinearidade (|r| > 0.85)...")
    collinear_groups = find_collinear_groups(df[full_feats], threshold=0.85)
    print(f"   Encontrados {len(collinear_groups)} grupos de features.")
    
    # 4. Alvos a serem analisados
    targets = {
        "result": {
            "type": "classification",
            "features": "base",
            "dataset": "full",
            "col": "result",
        },
        "total_goals": {
            "type": "regression",
            "features": "base",
            "dataset": "full",
            "col": "total_goals",
        },
        "goals_1h": {
            "type": "regression",
            "features": "base",
            "dataset": "full_halftime",
            "col": "goals_1h",
        },
        "goals_2h": {
            "type": "regression",
            "features": "base",
            "dataset": "full_halftime",
            "col": "goals_2h",
        },
        "home_corners": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "home_cur_sb_corners",
        },
        "away_corners": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "away_cur_sb_corners",
        },
        "total_shots": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "total_shots",
        },
        "total_shots_on_target": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "total_shots_on_target",
        },
        "total_cards": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "total_cards",
        },
        "cards_1h": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "cards_1h",
        },
        "cards_2h": {
            "type": "regression",
            "features": "full",
            "dataset": "advanced",
            "col": "cards_2h",
        },
    }
    
    results_report = {}
    
    # 5. Executar análise para cada alvo
    for target_name, info in targets.items():
        res = analyze_target(df, target_name, info, base_feats, full_feats, collinear_groups)
        if res is not None:
            results_report[target_name] = res
            
    # 6. Gravar Relatório JSON
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results_report, f, ensure_ascii=False, indent=2)
        
    print(f"\n>> Análise completa finalizada! Relatório gravado em {REPORT_PATH}")
    print(f">> Gráficos SHAP salvos na pasta: {PLOTS_DIR}")

if __name__ == "__main__":
    main()
