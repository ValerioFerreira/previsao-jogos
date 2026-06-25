#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/validate_corners_nb_calibration.py
==========================================
Revalida a calibração do modelo de PRODUÇÃO (classe CornersNB) no mesmo protocolo
temporal da validação original, sobre a base unificada da API. Objetivo: confirmar
que a classe que serve a produção reproduz a vantagem de calibração da NB
independente sobre a quantílica (log-loss e ECE) nos três mercados — não herdada
da validação antiga, mas medida com o código de produção.

OOS exige holdout, então treina-se na janela de treino (<= corte) e avalia-se no
futuro. O r reportado aqui é o do fold de treino (≈ validação original); o artefato
de produção aplica a MESMA receita à base inteira (r_H=18.20/r_A=16.70).

Rodar da raiz:  ./.venv/Scripts/python.exe scripts/validate_corners_nb_calibration.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
sys.path.insert(0, str(Path("api").resolve()))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from corners_nb_model import CornersNB
import compare_corners as cc  # reusa funcoes metricas/quantilicas validadas

CSV_PATH = Path("international_features_enriched_apifootball.csv")
M_C = cc.M_C  # 25


def count_logloss(prob_matrix, actual, max_c):
    clipped = np.clip(actual, 0, max_c).astype(int)
    return -np.mean(np.log(prob_matrix[np.arange(len(actual)), clipped] + 1e-15))


def over_metrics(prob_matrix, actual, line):
    y_over = (actual > line).astype(int)
    prob_over = prob_matrix[:, int(line) + 1:].sum(axis=1)
    return cc.expected_calibration_error(y_over, prob_over)


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df_adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_corners", "away_cur_sb_corners"]).copy()
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff = df_adv.iloc[n_train_idx]["date"]
    tr = df_adv[df_adv["date"] <= cutoff].reset_index(drop=True)
    te = df_adv[df_adv["date"] > cutoff].reset_index(drop=True)
    print(f"Corte: {cutoff:%Y-%m-%d} | Treino: {len(tr)} | Teste: {len(te)}")

    feats = [c for c in cc.numeric_features(df) if c not in cc.LEAK_OR_ID]
    yh_tr = tr["home_cur_sb_corners"].astype(int).values
    ya_tr = tr["away_cur_sb_corners"].astype(int).values
    yh_te = te["home_cur_sb_corners"].astype(int).values
    ya_te = te["away_cur_sb_corners"].astype(int).values
    yt_te = yh_te + ya_te

    # ---- Quantílica (atual) ----
    qh = cc.fit_quantile_models(tr, feats, tr["home_cur_sb_corners"])
    qa = cc.fit_quantile_models(tr, feats, tr["away_cur_sb_corners"])
    qt = cc.fit_quantile_models(tr, feats, tr["home_cur_sb_corners"] + tr["away_cur_sb_corners"])
    Xte = te[feats]
    ph_q = cc.compute_quantile_corners_distribution(qh[0.1].predict(Xte), qh[0.5].predict(Xte), qh[0.9].predict(Xte), M_C)
    pa_q = cc.compute_quantile_corners_distribution(qa[0.1].predict(Xte), qa[0.5].predict(Xte), qa[0.9].predict(Xte), M_C)
    pt_q = cc.compute_quantile_corners_distribution(qt[0.1].predict(Xte), qt[0.5].predict(Xte), qt[0.9].predict(Xte), 2 * M_C)

    # ---- CornersNB (PRODUÇÃO) treinada no fold ----
    model = CornersNB(max_corners=M_C, feats=feats).fit(tr[feats], yh_tr, ya_tr)
    print(f"  (r do fold de treino: r_H={model.r_H_:.4f}, r_A={model.r_A_:.4f})")
    d = model.predict_distributions(te[feats])
    ph_n, pa_n, pt_n = d["home"], d["away"], d["total"]

    rows = [
        ("Mandante",  4.5, M_C,     yh_te, ph_q, ph_n),
        ("Visitante", 3.5, M_C,     ya_te, pa_q, pa_n),
        ("Total",     8.5, 2 * M_C, yt_te, pt_q, pt_n),
    ]
    print("\n%-10s | %-22s | %-22s" % ("Mercado", "Quantílica (LL / ECE)", "NB Prod (LL / ECE)"))
    print("-" * 62)
    for name, line, maxc, actual, pq, pn in rows:
        ll_q = count_logloss(pq, actual, maxc); ece_q = over_metrics(pq, actual, line)
        ll_n = count_logloss(pn, actual, maxc); ece_n = over_metrics(pn, actual, line)
        win_ll = "NB" if ll_n < ll_q else "Quant"
        win_ece = "NB" if ece_n < ece_q else "Quant"
        print(f"{name:<10s} | {ll_q:7.5f} / {ece_q:6.2%}      | {ll_n:7.5f} / {ece_n:6.2%}   "
              f"[LL:{win_ll} ECE:{win_ece}]")


if __name__ == "__main__":
    main()
