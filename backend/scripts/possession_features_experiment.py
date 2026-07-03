#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/possession_features_experiment.py
==================================================
Parte 2 — Experimento 2 (features de posse/passes/faltas). Estas rolling pré-jogo
(home/away/diff × possession/passes/fouls × l3/l5) NÃO estão no base_feats atual.
Testa se agregam aos mercados de contagem (escanteios, cartões, finalizações, a gol),
com a NB de produção (GBR+NB), sob CV temporal. Gate: reduzir LogLoss sem piorar ECE.
Saída: backend/data/reports/possession_features_results.csv
"""
from __future__ import annotations
import warnings
from pathlib import Path
import sys
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reports" / "possession_features_results.csv"
POSS = []
for stat in ["possession", "passes", "fouls"]:
    for side in ["home", "away", "diff"]:
        for w in ["l3", "l5"]:
            POSS.append(f"{side}_sb_{stat}_{w}")

def cv_eval(sub, ch, ca, lado, feats, grade, line):
    cuts = np.linspace(0.5, 0.85, 4); lls, eces, maes = [], [], []
    for c in cuts:
        n = int(len(sub)*c); m = int(len(sub)*min(c+0.15, 1.0))
        tr, te = sub.iloc[:n], sub.iloc[n:m]
        if len(te) < 30: continue
        Xtr, Xte = tr[feats], te[feats]
        if lado == "total":
            Ph, _ = M.build_pmf("gbr", "nb", Xtr, tr[ch].astype(int).values, Xte, grade)
            Pa, _ = M.build_pmf("gbr", "nb", Xtr, tr[ca].astype(int).values, Xte, grade)
            P = np.zeros((len(te), 2*grade+1))
            for i in range(len(te)): P[i] = np.convolve(Ph[i], Pa[i])
            y = te[ch].astype(int).values + te[ca].astype(int).values
            mean = Ph@np.arange(grade+1) + Pa@np.arange(grade+1)
        else:
            col = ch if lado == "mandante" else ca
            y = te[col].astype(int).values
            P, mean = M.build_pmf("gbr", "nb", Xtr, tr[col].astype(int).values, Xte, grade)
        idx = np.clip(y, 0, P.shape[1]-1)
        lls.append(float(-np.mean(np.log(P[np.arange(len(y)), idx] + 1e-15))))
        over = P[:, int(np.floor(line))+1:].sum(1); yb = (y > line).astype(float)
        e = 0; edges = np.linspace(0, 1, 11)
        for b in range(10):
            mk = (over >= edges[b]) & (over < edges[b+1])
            if mk.mean() > 0: e += mk.mean()*abs(yb[mk].mean()-over[mk].mean())
        eces.append(e); maes.append(float(np.mean(np.abs(y-mean))))
    return np.mean(lls), np.std(lls), np.mean(eces), np.mean(maes)

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    poss = [c for c in POSS if c in adv.columns]
    MARKETS = [("escanteios","home_cur_sb_corners","away_cur_sb_corners",9.5,25),
               ("cartoes","home_cur_sb_cards","away_cur_sb_cards",3.5,15),
               ("finalizacoes","home_cur_sb_shots","away_cur_sb_shots",22.5,55),
               ("finalizacoes_gol","home_cur_sb_shots_on_target","away_cur_sb_shots_on_target",7.5,30)]
    rows = []
    for mkt, ch, ca, line, grade in MARKETS:
        sub = adv.dropna(subset=[ch, ca]).reset_index(drop=True)
        for lado, ln in [("mandante", line/2), ("visitante", line/2), ("total", line)]:
            for fsname, feats in [("base", M.FEATS), ("base+poss", M.FEATS + poss)]:
                ll, sd, ece, mae = cv_eval(sub, ch, ca, lado, feats, grade, ln)
                rows.append({"mercado": mkt, "lado": lado, "feature_set": fsname,
                             "cv_logloss": ll, "cv_ll_sd": sd, "cv_ece": ece, "cv_mae": mae})
            pd.DataFrame(rows).to_csv(OUT, index=False)
        print(f"[{mkt}] ok", flush=True)
    r = pd.DataFrame(rows)
    print("\n=== Δ (base+poss − base) por mercado/lado ===")
    for mkt in r.mercado.unique():
        for lado in ["mandante","visitante","total"]:
            s = r[(r.mercado==mkt)&(r.lado==lado)]
            if len(s) < 2: continue
            b = s[s.feature_set=="base"].iloc[0]; p = s[s.feature_set=="base+poss"].iloc[0]
            print(f"  {mkt:17} {lado:9} Δll={p.cv_logloss-b.cv_logloss:+.4f} (base {b.cv_logloss:.4f}) Δece={100*(p.cv_ece-b.cv_ece):+.1f}pp Δmae={p.cv_mae-b.cv_mae:+.3f}")
    print(f"-> {OUT}")

if __name__ == "__main__":
    main()
