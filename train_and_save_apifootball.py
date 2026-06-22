#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_and_save_apifootball.py
==============================
Versao paralela do train_and_save.py que:
  - Le international_features_enriched_apifootball.csv (na raiz do projeto)
  - Salva artefatos em api/model_artifacts_apifootball/
  - NAO modifica o model_artifacts/ original nem o predictor.py

Uso (rodar da raiz do projeto):
    python train_and_save_apifootball.py

Os dois modelos coexistem para comparacao posterior.
"""
import os, json, warnings
import numpy as np, pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor

warnings.filterwarnings("ignore")

# Leitura do CSV novo e saida em pasta separada
CSV = "international_features_enriched_apifootball.csv"
OUT = "api/model_artifacts_apifootball"
os.makedirs(OUT, exist_ok=True)

RS       = 42
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
        if c in LEAK_OR_ID:
            continue
        if c.startswith(("home_cur_", "away_cur_")):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def split_feature_sets(all_feats):
    base = [c for c in all_feats if "sb_" not in c]
    return base, list(all_feats)


def per_team_bases(df):
    bases = []
    for c in df.columns:
        if c.startswith("home_") and not c.startswith("home_cur_"):
            b = c[len("home_"):]
            if f"away_{b}" in df.columns and b not in ("team", "score", "win"):
                bases.append(b)
    return sorted(set(bases))


def build_team_snapshot(df, bases):
    long = []
    for _, r in df.iterrows():
        long.append((r["date"], r["home_team"], {b: r.get(f"home_{b}") for b in bases}))
        long.append((r["date"], r["away_team"], {b: r.get(f"away_{b}") for b in bases}))
    ldf = pd.DataFrame(long, columns=["date", "team", "vals"]).sort_values("date")
    snap = {}
    for team, grp in ldf.groupby("team"):
        acc = {}
        for _, rr in grp.iterrows():
            for b, v in rr["vals"].items():
                if pd.notna(v):
                    acc[b] = float(v)
        snap[team] = acc
    return snap


def fit_rf_classifier(df, feats, target_col):
    sub = df.dropna(subset=[target_col]).copy()
    X, y = sub[feats], sub[target_col].astype(str)
    pipe = Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(n_estimators=500, max_depth=10,
                                       min_samples_leaf=5, class_weight="balanced",
                                       random_state=RS, n_jobs=-1)),
    ])
    pipe.fit(X, y)
    return pipe, list(pipe.named_steps["clf"].classes_), len(sub)


def fit_quantile_models(df, feats, target_series, leaf=10):
    sub = df.copy()
    sub["_y"] = target_series
    sub = sub.dropna(subset=["_y"])
    X, y = sub[feats], sub["_y"].astype(float)
    models = {}
    for q in QUANTILES:
        pipe = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(
                loss="quantile", alpha=q,
                n_estimators=300, max_depth=3,
                learning_rate=0.05, min_samples_leaf=leaf,
                random_state=RS)),
        ])
        pipe.fit(X, y)
        models[q] = pipe
    return models, len(sub)


def main():
    print(f">> Carregando {CSV}")
    if not os.path.exists(CSV):
        print(f"[ERRO] {CSV} nao encontrado. Execute build_final_dataset.py primeiro.")
        return

    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    all_feats   = numeric_features(df)
    base_feats, full_feats = split_feature_sets(all_feats)
    print(f"   features base: {len(base_feats)} | completas: {len(full_feats)}")
    print(f"   linhas: {len(df)} | com stats avancadas: {int(df.get('has_advanced_stats', pd.Series(0)).fillna(0).sum())}")

    print(">> Classificadores (vencedor, ambas marcam, over 2.5)...")
    clf_res,  classes,   n_res  = fit_rf_classifier(df, base_feats, "result")
    clf_btts, btts_cls,  n_btts = fit_rf_classifier(df, base_feats, "btts")
    clf_ov,   ov_cls,    n_ov   = fit_rf_classifier(df, base_feats, "over_2_5")

    print(">> Regressores quantilicos (gols / escanteios / chutes)...")
    qm = {}
    qm["total_goals"], n_g = fit_quantile_models(df, base_feats,
                                                  df["home_score"] + df["away_score"])
    adv = df[df["has_advanced_stats"] == 1].copy()

    if len(adv) >= 10:
        print(f"   Partidas com stats avancadas: {len(adv)}")
        # Verifica se colunas existem
        cur_cols = [c for c in adv.columns if c.startswith("home_cur_sb_")]
        if cur_cols:
            qm["home_corners"], n_hc = fit_quantile_models(
                adv, full_feats, adv.get("home_cur_sb_corners", pd.Series(dtype=float)))
            qm["away_corners"], n_ac = fit_quantile_models(
                adv, full_feats, adv.get("away_cur_sb_corners", pd.Series(dtype=float)))
            shots_total = (adv.get("home_cur_sb_shots", pd.Series(0, dtype=float)) +
                           adv.get("away_cur_sb_shots", pd.Series(0, dtype=float)))
            qm["total_shots"], n_sh = fit_quantile_models(adv, full_feats, shots_total)
        else:
            print("   [AVISO] Colunas home_cur_sb_* ausentes — usando base_feats para regressores avancados")
            qm["home_corners"], n_hc = fit_quantile_models(adv, base_feats,
                                                            pd.Series(dtype=float))
            qm["away_corners"], n_ac = (qm["home_corners"], 0)
            qm["total_shots"],  n_sh = (qm["home_corners"], 0)
    else:
        print(f"   [AVISO] Poucas partidas com stats avancadas ({len(adv)}). "
              f"Regressores de escanteios/chutes treinados com dados insuficientes.")
        # Treinar com o que tem (pode dar warn mas nao crasha)
        if len(adv) > 0:
            qm["home_corners"], n_hc = fit_quantile_models(
                adv, full_feats, adv.get("home_cur_sb_corners",
                                          pd.Series(np.nan, index=adv.index)), leaf=1)
            qm["away_corners"], n_ac = fit_quantile_models(
                adv, full_feats, adv.get("away_cur_sb_corners",
                                          pd.Series(np.nan, index=adv.index)), leaf=1)
            shots_total = (adv.get("home_cur_sb_shots", pd.Series(0, index=adv.index)) +
                           adv.get("away_cur_sb_shots", pd.Series(0, index=adv.index)))
            qm["total_shots"], n_sh = fit_quantile_models(adv, full_feats, shots_total, leaf=1)
        else:
            # Fallback: treinar com df geral (sem stats avancadas)
            qm["home_corners"], n_hc = fit_quantile_models(df, base_feats,
                                                            pd.Series(np.nan, index=df.index))
            qm["away_corners"], n_ac = (qm["home_corners"], 0)
            qm["total_shots"],  n_sh = (qm["home_corners"], 0)

    print(">> Snapshot das selecoes...")
    bases    = per_team_bases(df)
    snapshot = build_team_snapshot(df, bases)
    teams    = sorted(snapshot.keys())
    medians  = {c: (float(df[c].median()) if pd.notna(df[c].median()) else 0.0)
                for c in full_feats}

    # Salvar artefatos na pasta SEPARADA (nao toca model_artifacts/ original)
    joblib.dump(clf_res,  f"{OUT}/clf_result.joblib",        compress=3)
    joblib.dump(clf_btts, f"{OUT}/clf_btts.joblib",          compress=3)
    joblib.dump(clf_ov,   f"{OUT}/clf_over25.joblib",        compress=3)
    joblib.dump(qm,       f"{OUT}/quantile_models.joblib",   compress=3)

    # Salvar results_slim.csv para predictor (h2h lookups)
    slim_cols = ["date", "home_team", "away_team", "home_score", "away_score"]
    slim_cols_avail = [c for c in slim_cols if c in df.columns]
    df[slim_cols_avail].to_csv(f"{OUT}/results_slim.csv", index=False)

    new_feats = [
        "has_boxscore_signal",
        "resid_home_style_crosses_l5", "resid_home_style_crosses_l10",
        "resid_away_style_crosses_l5", "resid_away_style_crosses_l10",
        "resid_home_style_ppda_l5", "resid_home_style_ppda_l10",
        "resid_away_style_ppda_l5", "resid_away_style_ppda_l10",
        "resid_home_style_fouls_suff_ratio_l5", "resid_home_style_fouls_suff_ratio_l10",
        "resid_away_style_fouls_suff_ratio_l5", "resid_away_style_fouls_suff_ratio_l10",
        "diff_resid_style_crosses_l5", "diff_resid_style_crosses_l10",
        "diff_resid_style_ppda_l5", "diff_resid_style_ppda_l10",
        "diff_resid_style_fouls_suff_ratio_l5", "diff_resid_style_fouls_suff_ratio_l10",
        "pred_home_shots", "pred_away_shots"
    ]
    for f in new_feats:
        if f not in full_feats:
            full_feats.append(f)

    meta = {
        "classes":       classes,
        "btts_classes":  btts_cls,
        "over25_classes":ov_cls,
        "quantiles":     QUANTILES,
        "base_feats":    base_feats,
        "full_feats":    full_feats,
        "bases":         bases,
        "teams":         teams,
        "medians":       medians,
        "snapshot":      snapshot,
        "n_train": {
            "result":       n_res,
            "btts":         n_btts,
            "over25":       n_ov,
            "goals":        n_g,
            "home_corners": n_hc,
            "away_corners": n_ac,
            "shots":        n_sh,
        },
        "tournament_weights": {
            "Amistoso":                            0.20,
            "Eliminatorias":                       0.60,
            "Liga das Nacoes":                     0.70,
            "Copa America / Euro / Copa Africana": 0.85,
            "Copa do Mundo":                       1.00,
        },
        "source": "api-football",
    }
    with open(f"{OUT}/meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n>> OK! Artefatos em ./{OUT}/")
    print("   linhas de treino:", meta["n_train"])
    print(f"   selecoes: {len(teams)}")


if __name__ == "__main__":
    main()
