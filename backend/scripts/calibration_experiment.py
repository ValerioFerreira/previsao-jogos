#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/calibration_experiment.py
==========================================
Parte 2 — Experimento 1 (Calibração). Calibra as probabilidades O/U dos mercados de
contagem (as usadas para apostas), comparando Isotonic · Platt(sigmoid) · Beta, em
esquema TEMPORAL (calibrador ajustado no passado, avaliado no futuro). Reusa as
predições OOF da validação (`market_promotion_pooled.csv`, dist=nb=produção).
Métricas antes/depois: Brier, LogLoss(binária), ECE + dados de reliability diagram.
Saída: backend/data/reports/calibration_results.csv (+ reliability bins).
"""
from __future__ import annotations
import warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
POOLED = ROOT / "data" / "reports" / "market_promotion_pooled.csv"
OUT = ROOT / "data" / "reports" / "calibration_results.csv"
OUT_REL = ROOT / "data" / "reports" / "calibration_reliability.csv"

def brier(y, p): return float(np.mean((p - y) ** 2))
def logloss(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
def ece(y, p, nb=10):
    e = 0; edges = np.linspace(0, 1, nb + 1)
    for b in range(nb):
        m = (p >= edges[b]) & (p < edges[b + 1])
        if m.mean() > 0: e += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(e)

def beta_fit(p, y):
    # beta calibration: logistic on [ln p, ln(1-p)]
    p = np.clip(p, 1e-6, 1 - 1e-6)
    Z = np.column_stack([np.log(p), np.log(1 - p)])
    lr = LogisticRegression(max_iter=2000).fit(Z, y)
    return lr
def beta_apply(lr, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return lr.predict_proba(np.column_stack([np.log(p), np.log(1 - p)]))[:, 1]

def main():
    d = pd.read_csv(POOLED)
    d = d[d.dist == "nb"].copy()   # produção
    rows, rel = [], []
    for mkt in d.mercado.unique():
        for lado in ["mandante", "visitante", "total"]:
            s = d[(d.mercado == mkt) & (d.lado == lado)].reset_index(drop=True)
            if len(s) < 200: continue
            y = s["abs_y_gt"].to_numpy(float); p = s["over"].to_numpy(float)
            # split temporal: primeiras 60% calibram, últimas 40% avaliam
            cut = int(len(s) * 0.6)
            ptr, ytr, pte, yte = p[:cut], y[:cut], p[cut:], y[cut:]
            base = {"brier": brier(yte, pte), "ll": logloss(yte, pte), "ece": ece(yte, pte)}
            # isotonic
            iso = IsotonicRegression(out_of_bounds="clip").fit(ptr, ytr); pi = iso.predict(pte)
            # platt
            pl = LogisticRegression(max_iter=2000).fit(ptr.reshape(-1, 1), ytr)
            pp = pl.predict_proba(pte.reshape(-1, 1))[:, 1]
            # beta
            bl = beta_fit(ptr, ytr); pb = beta_apply(bl, pte)
            cals = {"base": pte, "isotonic": pi, "platt": pp, "beta": pb}
            for name, pc in cals.items():
                rows.append({"mercado": mkt, "lado": lado, "metodo": name, "n_test": len(yte),
                             "brier": brier(yte, pc), "logloss": logloss(yte, pc), "ece": ece(yte, pc)})
                if lado == "total":  # reliability bins p/ diagrama
                    edges = np.linspace(0, 1, 11)
                    for b in range(10):
                        m = (pc >= edges[b]) & (pc < edges[b + 1])
                        if m.sum() > 0:
                            rel.append({"mercado": mkt, "metodo": name, "bin": round((edges[b]+edges[b+1])/2, 2),
                                        "conf": float(pc[m].mean()), "freq": float(yte[m].mean()), "n": int(m.sum())})
    pd.DataFrame(rows).to_csv(OUT, index=False)
    pd.DataFrame(rel).to_csv(OUT_REL, index=False)
    # resumo
    r = pd.DataFrame(rows)
    print("=== Calibração O/U (linha principal) — média sobre mercados/lados, por método ===")
    print(r.groupby("metodo")[["brier", "logloss", "ece"]].mean().round(4).to_string())
    print("\n=== por mercado (total): ECE antes(base) vs melhor método ===")
    for mkt in r.mercado.unique():
        s = r[(r.mercado == mkt) & (r.lado == "total")]
        base = s[s.metodo == "base"].iloc[0]
        best = s[s.metodo != "base"].sort_values("logloss").iloc[0]
        print(f"  {mkt:17} base ll={base.logloss:.4f} ece={100*base.ece:.1f}% -> {best.metodo} ll={best.logloss:.4f} ece={100*best.ece:.1f}%")
    print(f"\n-> {OUT}")

if __name__ == "__main__":
    main()
