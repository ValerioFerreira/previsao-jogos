#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/promotion_validation.py
=======================================
Validação DECISIVA de promoção (Parte 1) para os mercados de contagem candidatos
(finalizações, escanteios, finalizações a gol). Compara, com a MESMA média GBR de
produção, as distribuições Poisson · NB (produção atual) · Generalized-Poisson, sob
**CV TEMPORAL expanding** e com **SEGMENTAÇÃO** (equilíbrio, competição, continente).

Premissa verificada: a produção já usa NB (ShotsNB/CornersNB) — então o teste real é
"GP bate a NB de produção?". Gate: promover só se GP reduzir LogLoss vs NB sem piorar
calibração (ECE) de forma consistente (folds + segmentos).

Saídas: market_promotion_pooled.csv (predições OOF por linha) + resumo impresso.
"""
from __future__ import annotations
import warnings, json
from pathlib import Path
import sys
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reports" / "market_promotion_pooled.csv"

def comp_group(t):
    t = str(t)
    if 'World Cup' in t and 'qualif' in t.lower(): return 'Eliminatorias'
    if t == 'FIFA World Cup': return 'Copa do Mundo'
    if 'Nations League' in t: return 'Nations League'
    if t in ('Friendly', 'Friendlies'): return 'Amistoso'
    if 'qualif' in t.lower(): return 'Eliminatorias'
    if any(k in t for k in ['Euro', 'Copa Am', 'African Cup', 'Asian Cup', 'Gold Cup', 'COSAFA']): return 'Continental'
    return 'Outros'

def continent(t):
    t = str(t)
    if 'UEFA' in t or 'Euro' in t: return 'UEFA'
    if 'CONMEBOL' in t or 'Copa Am' in t: return 'CONMEBOL'
    if 'AFC' in t or 'Asian' in t: return 'AFC'
    if 'African' in t or 'COSAFA' in t: return 'CAF'
    if 'CONCACAF' in t or 'Gold Cup' in t: return 'CONCACAF'
    return 'Mundial/Outros'

def balance(elo):
    a = abs(elo)
    return 'equilibrado' if a <= 80 else ('intermediario' if a <= 150 else 'favorito_forte')

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    MARKETS = [
        ("finalizacoes", "home_cur_sb_shots", "away_cur_sb_shots", 22.5, 55),
        ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25),
        ("finalizacoes_gol", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30),
    ]
    DISTS = ["poisson", "nb", "gp"]
    rows = []
    for mkt, ch, ca, line, grade in MARKETS:
        sub = adv.dropna(subset=[ch, ca]).reset_index(drop=True)
        cuts = np.linspace(0.5, 0.85, 4)
        for lado, ln in [("mandante", line/2), ("visitante", line/2), ("total", line)]:
            col = ch if lado == "mandante" else (ca if lado == "visitante" else None)
            for c in cuts:
                n = int(len(sub)*c); m = int(len(sub)*min(c+0.15, 1.0))
                tr, te = sub.iloc[:n], sub.iloc[n:m]
                if len(te) < 30: continue
                Xtr, Xte = tr[M.FEATS], te[M.FEATS]
                for dist in DISTS:
                    if lado == "total":
                        Ph, _ = M.build_pmf("gbr", dist, Xtr, tr[ch].astype(int).values, Xte, grade)
                        Pa, _ = M.build_pmf("gbr", dist, Xtr, tr[ca].astype(int).values, Xte, grade)
                        P = np.zeros((len(te), 2*grade+1))
                        for i in range(len(te)): P[i] = np.convolve(Ph[i], Pa[i])
                        y = (te[ch].astype(int).values + te[ca].astype(int).values)
                        mean = Ph @ np.arange(grade+1) + Pa @ np.arange(grade+1)
                    else:
                        y = te[col].astype(int).values
                        P, mean = M.build_pmf("gbr", dist, Xtr, tr[col].astype(int).values, Xte, grade)
                    idx = np.clip(y, 0, P.shape[1]-1)
                    cll = -np.log(P[np.arange(len(y)), idx] + 1e-15)
                    over = P[:, int(np.floor(ln))+1:].sum(axis=1)
                    for i in range(len(te)):
                        rows.append({"mercado": mkt, "lado": lado, "dist": dist, "fold": round(c, 2),
                                     "y": int(y[i]), "count_ll": float(cll[i]), "over": float(over[i]),
                                     "line": ln, "abs_y_gt": int(y[i] > ln), "mean": float(mean[i]),
                                     "balance": balance(te["elo_diff"].values[i]),
                                     "comp": comp_group(te["tournament"].values[i]),
                                     "cont": continent(te["tournament"].values[i])})
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"[{mkt}/{lado}] ok ({len(rows)} linhas)", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
