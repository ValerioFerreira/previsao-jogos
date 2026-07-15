#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_b_transfer_selections.py
========================================
Fase 7 do plano: repete o teste de transferência (zero-shot/pooled/finetune) da
Fase 3, mas com a MELHOR arquitetura da Linha B em vez do DC-NB. Por padrão usa
CatBoost+pi-ratings (vencedor da Fase 1 entre os candidatos B — ver
docs/PESQUISA_CLUBES.md §4). Se a Fase 6 (sweep/state-space/ensemble) revelar um
candidato B melhor, trocar --model.

Mesmo gate da Fase 3: promoção a `main` só com ganho consistente (>=4/5 folds)
sobre a PRODUÇÃO REAL (DC-NB em seleções), não sobre o zero-shot de clubes.

Uso: python scripts/clubs_b_transfer_selections.py [--model catboost_pi]
"""
import argparse
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, accuracy, compare, FoldResult)
from research_clubs.gbm_models import add_rating_features, PI_FEATS, ELO_FEATS

SEL_CSV = ROOT / "international_features_enriched_apifootball.csv"
CLUBS_PARQUET = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_CSV = ROOT / "data" / "reports" / "clubs_b_transfer_selections.csv"
META = ROOT / "model_artifacts" / "meta.json"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "ece": ece_multiclass(y_idx, probs), "accuracy": accuracy(y_idx, probs)}


def result_probs_dc(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def fit_baseline(tr, te, bf):
    X_tr = tr[bf].fillna(tr[bf].median(numeric_only=True))
    X_te = te[bf].fillna(tr[bf].median(numeric_only=True))
    m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                              max_goals=12, random_state=42)
    m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
    return result_probs_dc(m, X_te)


def fit_catboost_pi(tr, te, feats):
    from catboost import CatBoostClassifier
    X_tr = tr[feats].to_numpy(dtype=float)
    X_te = te[feats].to_numpy(dtype=float)
    y_tr = tr["result"].map(Y_MAP).to_numpy()
    m = CatBoostClassifier(loss_function="MultiClass", depth=6, iterations=800,
                           learning_rate=0.03, l2_leaf_reg=3.0, random_seed=42,
                           verbose=0, allow_writing_files=False, thread_count=-1)
    m.fit(X_tr, y_tr)
    return m.predict_proba(X_te)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["catboost_pi"], default="catboost_pi")
    a = ap.parse_args()

    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    sel = pd.read_csv(SEL_CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    sel = add_rating_features(sel)
    clubs = pd.read_parquet(CLUBS_PARQUET)
    clubs["date"] = pd.to_datetime(clubs["date"])
    clubs = clubs[(clubs["home_matches_played_before"] >= 5) &
                  (clubs["away_matches_played_before"] >= 5)].reset_index(drop=True)
    clubs = add_rating_features(clubs)
    print(f"seleções: {len(sel)} | clubes: {len(clubs)} | modelo B: {a.model}")

    feats_b = PI_FEATS + ELO_FEATS
    rows = []
    modes = ["baseline_dc", "zero_shot_B", "pooled_B_w0.5", "finetune_B"]
    results_by_mode = {m: [] for m in modes}

    for fold, tr_idx, te_idx in temporal_folds(sel):
        tr_sel, te_sel = sel.loc[tr_idx], sel.loc[te_idx]
        cutoff = tr_sel["date"].max()
        clubs_tr = clubs[clubs["date"] <= cutoff]
        y_idx = te_sel["result"].map(Y_MAP).to_numpy()

        p_base = fit_baseline(tr_sel, te_sel, bf)
        met_base = metrics(y_idx, p_base)
        results_by_mode["baseline_dc"].append(FoldResult(fold, len(te_sel), met_base))

        p_zs = fit_catboost_pi(clubs_tr, te_sel, feats_b)
        met_zs = metrics(y_idx, p_zs)
        results_by_mode["zero_shot_B"].append(FoldResult(fold, len(te_sel), met_zs))

        pooled = pd.concat([tr_sel, clubs_tr], ignore_index=True)
        # CatBoost não usa sample_weight aqui por simplicidade — pooled 1:1, mas
        # clubes é ~5x maior, então sub-amostra proporcional (peso 0.5 = mantém metade)
        clubs_sub = clubs_tr.sample(frac=0.5, random_state=42)
        pooled_half = pd.concat([tr_sel, clubs_sub], ignore_index=True)
        p_pool = fit_catboost_pi(pooled_half, te_sel, feats_b)
        met_pool = metrics(y_idx, p_pool)
        results_by_mode["pooled_B_w0.5"].append(FoldResult(fold, len(te_sel), met_pool))

        p_ft = fit_catboost_pi(tr_sel, te_sel, feats_b)  # mesmos hiperparâmetros, fit só em seleções
        met_ft = metrics(y_idx, p_ft)
        results_by_mode["finetune_B"].append(FoldResult(fold, len(te_sel), met_ft))

        for mode, met in [("baseline_dc", met_base), ("zero_shot_B", met_zs),
                          ("pooled_B_w0.5", met_pool), ("finetune_B", met_ft)]:
            rows.append({"mode": mode, "fold": fold, "n": len(te_sel), **met})
        pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
        print(f"{fold}: baseline={met_base['logloss']:.4f} zero_shot_B={met_zs['logloss']:.4f} "
              f"pooled_B={met_pool['logloss']:.4f} finetune_B={met_ft['logloss']:.4f}", flush=True)

    print("\n===== COMPARAÇÃO vs baseline_dc (produção) =====")
    for mode in ["zero_shot_B", "pooled_B_w0.5", "finetune_B"]:
        comp = compare(results_by_mode["baseline_dc"], results_by_mode[mode], metric="logloss")
        wins = comp.iloc[:-1]["melhora"].sum()
        delta = comp.iloc[-1]["delta"]
        veredito = "CANDIDATO A PROMOÇÃO" if wins >= 4 and delta < -0.001 else \
            ("misto" if wins >= 2 else "reprovado")
        print(f"{mode}: {wins}/5 folds melhoram | delta={delta:+.4f} -> {veredito}")


if __name__ == "__main__":
    main()
