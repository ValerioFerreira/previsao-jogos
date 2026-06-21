#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/compare_cards.py
========================
Passo 2b — Validacao dos modelos de contagem para CARTOES (espelho do
compare_corners.py). Compara, em split temporal sobre os ~4.1k jogos com stats:
  - Quantilica (baseline, treinada no fold)
  - NB independente (Abordagem A)
  - NB acoplada (Abordagem B)
nos 3 mercados: mandante, visitante, total.

Pergunta central (difere de escanteios): a correlacao entre lados em cartoes e
POSITIVA (jogo pegado cartoneia os dois)? Se sim, o acoplado pode ganhar aqui.
Reporta beta, r de dispersao, log-loss/ECE/cobertura e vies global.

Deliverable: comparacao_cartoes.md  (NAO promove nada; so diagnostico)
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
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, "scripts")
import compare_corners as cc  # reusa helpers + BivariateNBCorners (NB bivariada generica)

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
FULL_FEATS = META["full_feats"]
REPORT = Path("comparacao_cartoes.md")

M = 15                 # grade por lado (cartoes raramente passam disso)
RS = 42
L_HOME, L_AWAY, L_TOTAL = 1.5, 1.5, 3.5   # linhas O/U representativas


def nb_indep_dist(lambdas, r, maxc):
    k = np.arange(maxc + 1)
    out = np.zeros((len(lambdas), maxc + 1))
    for i, lam in enumerate(lambdas):
        p = r / (r + lam)
        pm = nbinom.pmf(k, n=r, p=p)
        out[i] = pm / pm.sum()
    return out


def optimize_r(y, lam):
    def obj(r):
        if r <= 0.05:
            return 1e10
        return -np.sum(np.log(nbinom.pmf(y, n=r, p=r / (r + lam)) + 1e-15))
    return float(minimize(obj, [5.0], bounds=[(0.1, 1000.0)], method="L-BFGS-B").x[0])


def metrics(prob, actual, line, maxc, point):
    n = len(actual)
    clipped = np.clip(actual, 0, maxc).astype(int)
    ll = -np.mean(np.log(prob[np.arange(n), clipped] + 1e-15))
    y_over = (actual > line).astype(int)
    p_over = prob[:, int(line) + 1:].sum(axis=1)
    brier = mean_squared_error(y_over, p_over)
    ece = cc.expected_calibration_error(y_over, p_over)
    cov, wid = [], []
    for i in range(n):
        cdf = np.cumsum(prob[i])
        q10 = np.searchsorted(cdf, 0.1); q90 = np.searchsorted(cdf, 0.9)
        wid.append(q90 - q10); cov.append(1.0 if q10 <= actual[i] <= q90 else 0.0)
    return {"ll": ll, "brier": brier, "ece": ece, "cov": np.mean(cov), "wid": np.mean(wid),
            "mae": mean_absolute_error(actual, point), "rmse": np.sqrt(mean_squared_error(actual, point)),
            "mean_pred": float(np.mean(point))}


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["date"], low_memory=False).sort_values("date").reset_index(drop=True)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_cards", "away_cur_sb_cards"]).copy()
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr = adv[adv["date"] <= cut].reset_index(drop=True)
    te = adv[adv["date"] > cut].reset_index(drop=True)
    print(f"Corte {cut:%Y-%m-%d} | treino {len(tr)} | teste {len(te)}")

    yh_tr = tr["home_cur_sb_cards"].astype(int).values
    ya_tr = tr["away_cur_sb_cards"].astype(int).values
    yh_te = te["home_cur_sb_cards"].astype(int).values
    ya_te = te["away_cur_sb_cards"].astype(int).values
    yt_te = yh_te + ya_te
    Xtr, Xte = tr[FULL_FEATS], te[FULL_FEATS]

    # --- Quantilica (baseline) ---
    qh = cc.fit_quantile_models(tr, FULL_FEATS, tr["home_cur_sb_cards"])
    qa = cc.fit_quantile_models(tr, FULL_FEATS, tr["away_cur_sb_cards"])
    qt = cc.fit_quantile_models(tr, FULL_FEATS, tr["home_cur_sb_cards"] + tr["away_cur_sb_cards"])
    ph_q = cc.compute_quantile_corners_distribution(qh[0.1].predict(Xte), qh[0.5].predict(Xte), qh[0.9].predict(Xte), M)
    pa_q = cc.compute_quantile_corners_distribution(qa[0.1].predict(Xte), qa[0.5].predict(Xte), qa[0.9].predict(Xte), M)
    pt_q = cc.compute_quantile_corners_distribution(qt[0.1].predict(Xte), qt[0.5].predict(Xte), qt[0.9].predict(Xte), 2 * M)
    pth_q50, pta_q50, ptt_q50 = qh[0.5].predict(Xte), qa[0.5].predict(Xte), qt[0.5].predict(Xte)

    # --- Abordagem A (NB independente) ---
    mh = Pipeline([("imp", SimpleImputer(strategy="median")), ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100, max_depth=3, learning_rate=0.05, random_state=RS))])
    ma = Pipeline([("imp", SimpleImputer(strategy="median")), ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100, max_depth=3, learning_rate=0.05, random_state=RS))])
    mh.fit(Xtr, yh_tr); ma.fit(Xtr, ya_tr)
    lam_tr_h = np.maximum(mh.predict(Xtr), 0.05); lam_tr_a = np.maximum(ma.predict(Xtr), 0.05)
    rH = optimize_r(yh_tr, lam_tr_h); rA = optimize_r(ya_tr, lam_tr_a)
    lam_te_h = np.maximum(mh.predict(Xte), 0.05); lam_te_a = np.maximum(ma.predict(Xte), 0.05)
    ph_a = nb_indep_dist(lam_te_h, rH, M); pa_a = nb_indep_dist(lam_te_a, rA, M)
    pt_a = cc.convolve_probabilities(ph_a, pa_a, max_corners=M)

    # --- Abordagem B (NB acoplada) ---
    mb = cc.BivariateNBCorners(max_corners=M, random_state=RS)
    mb.fit(Xtr, yh_tr, ya_tr)
    Pj, lam_b_h, lam_b_a = mb.predict_joint(Xte)
    ph_b = np.zeros((len(te), M + 1)); pa_b = np.zeros((len(te), M + 1)); pt_b = np.zeros((len(te), 2 * M + 1))
    for i in range(len(te)):
        ph_b[i] = Pj[i].sum(axis=1); pa_b[i] = Pj[i].sum(axis=0)
        for x in range(M + 1):
            for y in range(M + 1):
                pt_b[i, x + y] += Pj[i, x, y]

    markets = [
        ("Mandante", yh_te, L_HOME, M, ph_q, ph_a, ph_b, pth_q50, lam_te_h, lam_b_h),
        ("Visitante", ya_te, L_AWAY, M, pa_q, pa_a, pa_b, pta_q50, lam_te_a, lam_b_a),
        ("Total", yt_te, L_TOTAL, 2 * M, pt_q, pt_a, pt_b, ptt_q50, lam_te_h + lam_te_a, lam_b_h + lam_b_a),
    ]
    res = {}
    for name, act, line, mc, pq, pa_, pb, ptq, pta_, ptb in markets:
        res[name] = {
            "atual": metrics(pq, act, line, mc, ptq),
            "A": metrics(pa_, act, line, mc, pta_),
            "B": metrics(pb, act, line, mc, ptb),
        }

    # --- relatorio ---
    L = ["# Comparacao de Modelos de Contagem para CARTOES (Passo 2b)", "",
         f"- Corte temporal: {cut:%Y-%m-%d} | treino {len(tr)} | teste {len(te)}",
         f"- Grade M={M}", "",
         "## Parametros estimados (MLE no treino)",
         f"- Independente: r_H={rH:.4f}, r_A={rA:.4f}",
         f"- Acoplada: r_H={mb.r_H_:.4f}, r_A={mb.r_A_:.4f}, **beta={mb.beta_:.4f}** "
         f"(correlacao {'POSITIVA' if mb.beta_>0 else 'negativa'}), forma "
         f"{'exponencial' if mb.use_exponential_ else 'linear'}", "",
         "## Vies global (media prevista vs real)",
         "| Mercado | Real | Atual | A (indep) | B (acopl) |", "|---|---|---|---|---|"]
    for name, act, *_ in markets:
        L.append(f"| {name} | {np.mean(act):.3f} | {res[name]['atual']['mean_pred']:.3f} | "
                 f"{res[name]['A']['mean_pred']:.3f} | {res[name]['B']['mean_pred']:.3f} |")
    L.append("")
    for name, act, line, *_ in markets:
        L.append(f"## {name} (linha Over {line})")
        L.append("| Abordagem | LogLoss | Brier | ECE | Cob80% | Largura | MAE | RMSE |")
        L.append("|---|---|---|---|---|---|---|---|")
        for key, lab in [("atual", "Atual (Quantilica)"), ("A", "A (Independente)"), ("B", "B (Acoplada)")]:
            r = res[name][key]
            L.append(f"| {lab} | {r['ll']:.5f} | {r['brier']:.5f} | {r['ece']:.2%} | {r['cov']:.2%} | "
                     f"{r['wid']:.2f} | {r['mae']:.3f} | {r['rmse']:.3f} |")
        L.append("")
    # recomendacao
    L.append("## Recomendacao por mercado (LogLoss; ECE como desempate)")
    for name, *_ in markets:
        rr = res[name]
        cand = {"Atual": rr["atual"]["ll"], "A (indep)": rr["A"]["ll"], "B (acopl)": rr["B"]["ll"]}
        best = min(cand, key=cand.get)
        L.append(f"- **{name}:** {best} (LL atual={rr['atual']['ll']:.5f} · A={rr['A']['ll']:.5f} · B={rr['B']['ll']:.5f})")
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print("Relatorio:", REPORT)
    print("\n".join(L))


if __name__ == "__main__":
    main()
