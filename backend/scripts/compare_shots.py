#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/compare_shots.py
========================
Modernizacao de CHUTES (Fase A). Compara a quantilica atual (baseline) contra a
NB independente (mandante/visitante/total), VARRENDO o time decay (H), sobre os
~4.1k jogos com stats, split temporal.

Chutes sao sobredispersos (var/media ~3.3) -> NB deve achar r finito (real).
E foi o unico alvo onde o decay reduziu o vies e melhorou calibracao -> aqui ele
e aplicado e tunado. Reporta r, vies, log-loss, ECE por mercado e por H.

Peso: w = 0.5^((ancora - data)/H), ancora = data max do treino. r estimado s/ peso.
Deliverable: comparacao_chutes.md
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.optimize import minimize
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor

sys.path.insert(0, "scripts")
import compare_corners as cc

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
FULL = META["full_feats"]
M = 55                      # grade por lado (chutes vao ate ~51)
H_YEARS = [None, 3, 2, 1]   # None = sem decay
L_HOME, L_AWAY, L_TOTAL = 12.5, 10.5, 22.5
RS = 42


def gbr():
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100,
                                                       max_depth=3, learning_rate=0.05, random_state=RS))])


def opt_r(y, lam):
    def obj(r):
        if r <= 0.05:
            return 1e10
        return -np.sum(np.log(nbinom.pmf(y, n=r, p=r / (r + lam)) + 1e-15))
    return float(minimize(obj, [5.0], bounds=[(0.1, 5000.0)], method="L-BFGS-B").x[0])


def nb_pmf(lam, r, maxc):
    k = np.arange(maxc + 1)
    out = np.zeros((len(lam), maxc + 1))
    for i, l in enumerate(lam):
        pm = nbinom.pmf(k, n=r, p=r / (r + l)); out[i] = pm / pm.sum()
    return out


def metrics(prob, actual, line, maxc, point):
    n = len(actual); clipped = np.clip(actual, 0, maxc).astype(int)
    ll = float(-np.mean(np.log(prob[np.arange(n), clipped] + 1e-15)))
    ece = float(cc.expected_calibration_error((actual > line).astype(int), prob[:, int(line) + 1:].sum(axis=1)))
    return ll, ece, float(point.mean() - actual.mean())


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_shots", "away_cur_sb_shots"]).copy()
    adv = adv.sort_values("date").reset_index(drop=True)
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr, te = adv[adv["date"] <= cut].reset_index(drop=True), adv[adv["date"] > cut].reset_index(drop=True)
    anchor = tr["date"].max()
    print(f"Corte {cut:%Y-%m-%d} | treino {len(tr)} | teste {len(te)}")

    yh, ya = tr["home_cur_sb_shots"].astype(int).values, tr["away_cur_sb_shots"].astype(int).values
    yh_te, ya_te = te["home_cur_sb_shots"].astype(int).values, te["away_cur_sb_shots"].astype(int).values
    yt_te = yh_te + ya_te
    Xtr, Xte = tr[FULL], te[FULL]

    # baseline quantilico
    qh = cc.fit_quantile_models(tr, FULL, tr["home_cur_sb_shots"])
    qa = cc.fit_quantile_models(tr, FULL, tr["away_cur_sb_shots"])
    qt = cc.fit_quantile_models(tr, FULL, tr["home_cur_sb_shots"] + tr["away_cur_sb_shots"])
    ph_q = cc.compute_quantile_corners_distribution(qh[0.1].predict(Xte), qh[0.5].predict(Xte), qh[0.9].predict(Xte), M)
    pa_q = cc.compute_quantile_corners_distribution(qa[0.1].predict(Xte), qa[0.5].predict(Xte), qa[0.9].predict(Xte), M)
    pt_q = cc.compute_quantile_corners_distribution(qt[0.1].predict(Xte), qt[0.5].predict(Xte), qt[0.9].predict(Xte), 2 * M)
    qbase = {
        "Mandante": metrics(ph_q, yh_te, L_HOME, M, qh[0.5].predict(Xte)),
        "Visitante": metrics(pa_q, ya_te, L_AWAY, M, qa[0.5].predict(Xte)),
        "Total": metrics(pt_q, yt_te, L_TOTAL, 2 * M, qt[0.5].predict(Xte)),
    }

    L = ["# Comparacao CHUTES — Quantilica vs NB independente (com varredura de decay)", "",
         f"- Corte {cut:%Y-%m-%d} | treino {len(tr)} | teste {len(te)} | grade M={M}",
         "- Vies = media prevista - real (negativo = subestima). H = meia-vida (anos).", ""]
    for mk in ["Mandante", "Visitante", "Total"]:
        line = {"Mandante": L_HOME, "Visitante": L_AWAY, "Total": L_TOTAL}[mk]
        L.append(f"## {mk} (linha O{line})")
        L.append("| Abordagem | r | Vies | LogLoss | ECE |")
        L.append("|---|---|---|---|---|")
        ll, ece, bias = qbase[mk]
        L.append(f"| Quantilica (atual) | – | {bias:+.3f} | {ll:.4f} | {ece:.2%} |")

    for H in H_YEARS:
        w = (0.5 ** ((anchor - tr["date"]).dt.days.values / (H * 365.0))) if H else None
        mh, ma = gbr(), gbr()
        mh.fit(Xtr, yh, reg__sample_weight=w); ma.fit(Xtr, ya, reg__sample_weight=w)
        lh_tr = np.maximum(mh.predict(Xtr), 0.05); la_tr = np.maximum(ma.predict(Xtr), 0.05)
        rH, rA = opt_r(yh, lh_tr), opt_r(ya, la_tr)
        lh_te = np.maximum(mh.predict(Xte), 0.05); la_te = np.maximum(ma.predict(Xte), 0.05)
        ph, pa = nb_pmf(lh_te, rH, M), nb_pmf(la_te, rA, M)
        pt = cc.convolve_probabilities(ph, pa, max_corners=M)
        rec = {"Mandante": (rH, ph, yh_te, L_HOME, M, lh_te),
               "Visitante": (rA, pa, ya_te, L_AWAY, M, la_te),
               "Total": ((rH + rA) / 2, pt, yt_te, L_TOTAL, 2 * M, lh_te + la_te)}
        for mk in ["Mandante", "Visitante", "Total"]:
            r, prob, act, line, mc, pt_pt = rec[mk]
            ll, ece, bias = metrics(prob, act, line, mc, pt_pt)
            tag = "sem decay" if H is None else f"decay H={H}"
            # achar a secao do mercado e inserir
            idx = L.index(f"## {mk} (linha O{line})") + 3
            while idx < len(L) and L[idx].startswith("|"):
                idx += 1
            L.insert(idx, f"| NB {tag} | {r:.1f} | {bias:+.3f} | {ll:.4f} | {ece:.2%} |")

    Path("comparacao_chutes.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print("\nRelatorio: comparacao_chutes.md")


if __name__ == "__main__":
    main()
