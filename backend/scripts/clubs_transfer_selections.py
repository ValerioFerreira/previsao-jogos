#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_transfer_selections.py
=====================================
Fase 3 do plano de pesquisa de clubes: responde à pergunta 2 da diretriz —
"o conhecimento de clubes melhora as previsões de seleções?"

Quatro modos, todos avaliados nos MESMOS 5 folds temporais de SELEÇÕES (comparação
justa contra a produção real, não um proxy):
  zero_shot : treina só em clubes (todo o histórico de clubes ANTERIOR à data de
              corte do fold de seleções), prevê seleções direto — mede se o sinal
              aprendido em clubes generaliza sem nenhum ajuste.
  pooled    : treina em clubes+seleções juntos, com peso amostral configurável para
              clubes (w em {0.25, 0.5, 1.0}) — mede se clubes funciona como dado
              auxiliar que reduz variância sem enviesar seleções.
  finetune  : hiperparâmetros = vencedor do tuning de clubes (clubs_tune_dc.py),
              MAS o fit final é feito só nos dados de seleções do fold (warm-start
              conceitual: usa a config aprendida, não os pesos).
  baseline  : produção real (hiperparâmetros de produção, só dados de seleções) —
              a referência para o gate.

Gate (docs/PLANO_PESQUISA_CLUBES.md fase 3): promover para main SOMENTE se algum
modo bater o baseline em ≥4/5 folds, sem piorar ECE, e a diferença for material
(não ruído de seed). Este script só MEDE e REPORTA — não aplica a exceção de push
automaticamente (decisão fica para o relatório da fase 9 / usuário).

Uso: python scripts/clubs_transfer_selections.py [--best-config n_estimators,depth,lr]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (temporal_folds, multiclass_logloss, rps_hda,
                                     ece_multiclass, brier_multiclass, accuracy,
                                     compare, FoldResult)
import json

SEL_CSV = ROOT / "international_features_enriched_apifootball.csv"
CLUBS_PARQUET = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_CSV = ROOT / "data" / "reports" / "clubs_transfer_selections.csv"
META = ROOT / "model_artifacts" / "meta.json"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def result_probs(model, X):
    d = model.predict_proba_markets(X)
    return d["result"][:, ::-1]


def metrics(y_idx, probs):
    return {"logloss": multiclass_logloss(y_idx, probs), "rps": rps_hda(y_idx, probs),
           "brier": brier_multiclass(y_idx, probs), "ece": ece_multiclass(y_idx, probs),
           "accuracy": accuracy(y_idx, probs)}


def fit_dc(X, yh, ya, sw=None, n_est=100, depth=3, lr=0.05):
    m = DixonColesNBRegressor(n_estimators=n_est, max_depth=depth, learning_rate=lr,
                              max_goals=12, random_state=42)
    m.fit(X, yh, ya, sample_weight=sw)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--best-config", type=str, default="100,3,0.05",
                    help="n_estimators,max_depth,learning_rate do vencedor do tuning de clubes")
    a = ap.parse_args()
    n_est, depth, lr = a.best_config.split(",")
    n_est, depth, lr = int(n_est), int(depth), float(lr)

    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    sel = pd.read_csv(SEL_CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    clubs = pd.read_parquet(CLUBS_PARQUET)
    clubs["date"] = pd.to_datetime(clubs["date"])
    clubs = clubs[(clubs["home_matches_played_before"] >= 5) &
                  (clubs["away_matches_played_before"] >= 5)].reset_index(drop=True)
    print(f"seleções: {len(sel)} | clubes: {len(clubs)}")

    missing = [c for c in bf if c not in clubs.columns]
    assert not missing, f"faltam base_feats em clubes: {missing}"

    rows = []
    baseline_folds, results_by_mode = [], {}
    modes = ["baseline", "zero_shot", "pooled_w0.5", "finetune"]
    for mode in modes:
        results_by_mode[mode] = []

    for fold, tr_idx, te_idx in temporal_folds(sel):
        tr_sel, te_sel = sel.loc[tr_idx], sel.loc[te_idx]
        cutoff = tr_sel["date"].max()
        clubs_tr = clubs[clubs["date"] <= cutoff]
        X_te = te_sel[bf].fillna(tr_sel[bf].median(numeric_only=True))
        y_idx = te_sel["result"].map(Y_MAP).to_numpy()

        # baseline: produção real (hiperparâmetros de produção)
        X_tr = tr_sel[bf].fillna(tr_sel[bf].median(numeric_only=True))
        m_base = fit_dc(X_tr, tr_sel["home_score"].to_numpy(), tr_sel["away_score"].to_numpy())
        met_base = metrics(y_idx, result_probs(m_base, X_te))
        results_by_mode["baseline"].append(FoldResult(fold, len(te_sel), met_base))

        # zero-shot: só clubes
        Xc = clubs_tr[bf].fillna(clubs_tr[bf].median(numeric_only=True))
        m_zs = fit_dc(Xc, clubs_tr["home_score"].to_numpy(), clubs_tr["away_score"].to_numpy())
        X_te_zs = te_sel[bf].fillna(clubs_tr[bf].median(numeric_only=True))
        met_zs = metrics(y_idx, result_probs(m_zs, X_te_zs))
        results_by_mode["zero_shot"].append(FoldResult(fold, len(te_sel), met_zs))

        # pooled: clubes (peso 0.5) + seleções (peso 1.0)
        pooled_X = pd.concat([X_tr, Xc], ignore_index=True)
        pooled_yh = np.concatenate([tr_sel["home_score"].to_numpy(), clubs_tr["home_score"].to_numpy()])
        pooled_ya = np.concatenate([tr_sel["away_score"].to_numpy(), clubs_tr["away_score"].to_numpy()])
        sw = np.concatenate([np.ones(len(tr_sel)), np.full(len(clubs_tr), 0.5)])
        m_pool = fit_dc(pooled_X, pooled_yh, pooled_ya, sw=sw)
        met_pool = metrics(y_idx, result_probs(m_pool, X_te))
        results_by_mode["pooled_w0.5"].append(FoldResult(fold, len(te_sel), met_pool))

        # finetune: hiperparâmetros vencedores do tuning de clubes, fit só em seleções
        m_ft = fit_dc(X_tr, tr_sel["home_score"].to_numpy(), tr_sel["away_score"].to_numpy(),
                     n_est=n_est, depth=depth, lr=lr)
        met_ft = metrics(y_idx, result_probs(m_ft, X_te))
        results_by_mode["finetune"].append(FoldResult(fold, len(te_sel), met_ft))

        for mode, met in [("baseline", met_base), ("zero_shot", met_zs),
                          ("pooled_w0.5", met_pool), ("finetune", met_ft)]:
            row = {"mode": mode, "fold": fold, "n": len(te_sel), **met}
            rows.append(row)
        pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
        print(f"{fold}: baseline ll={met_base['logloss']:.4f} | zero_shot ll={met_zs['logloss']:.4f} "
              f"| pooled ll={met_pool['logloss']:.4f} | finetune ll={met_ft['logloss']:.4f}", flush=True)

    print("\n===== COMPARAÇÃO vs BASELINE (fold a fold) =====")
    for mode in ["zero_shot", "pooled_w0.5", "finetune"]:
        comp = compare(results_by_mode["baseline"], results_by_mode[mode], metric="logloss")
        print(f"\n-- {mode} --")
        print(comp.to_string(index=False))
        wins = comp.iloc[:-1]["melhora"].sum()
        n_folds = len(comp) - 1
        veredito = "CANDIDATO A PROMOÇÃO" if wins >= 4 else ("misto" if wins >= 2 else "reprovado")
        print(f"   {wins}/{n_folds} folds melhoram -> {veredito}")


if __name__ == "__main__":
    main()
