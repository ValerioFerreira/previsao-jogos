#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/exp4_copula.py
==============================
EXP 4 — DEPENDENCIA BIVARIADA (COPULA) mandante x visitante nos mercados de TOTAL.
A producao assume INDEPENDENCIA (convolucao das PMFs NB de cada lado) para o total.
Aqui medimos a correlacao residual home x away (apos condicionar nas medias) e
testamos uma COPULA GAUSSIANA sobre as marginais NB de producao, derivando a PMF do
TOTAL com dependencia. Compara LL/ECE do total: independencia vs copula.

Trabalho anterior achou correlacao fraca em escanteios (beta~-0.04). Reportamos rho
estimado point-in-time por fold + ganho/perda no total. Gate: so vale se reduzir LL
do total sem piorar ECE, consistente. Saida: data/reports/exp4_copula_results.csv
"""
from __future__ import annotations
import warnings
from pathlib import Path
import sys
import numpy as np, pandas as pd
from scipy.stats import norm, nbinom
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reports" / "exp4_copula_results.csv"

MARKETS = [
    ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25),
    ("finalizacoes", "home_cur_sb_shots", "away_cur_sb_shots", 22.5, 55),
    ("finalizacoes_gol", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30),
    ("gols", "home_score", "away_score", 2.5, 12),
    ("cartoes", "home_cur_sb_cards", "away_cur_sb_cards", 3.5, 15),
]

def nb_params(lam, r):
    lam = np.maximum(lam, 1e-6); p = r / (r + lam)
    return p

def pit_normal(y, lam, r):
    """Pseudo-observacao normal via PIT randomizado (discreto) -> escore z."""
    p = nb_params(lam, r)
    cdf_hi = nbinom.cdf(y, r, p); cdf_lo = nbinom.cdf(y - 1, r, p)
    u = cdf_lo + np.random.default_rng(0).uniform(0, 1, len(y)) * (cdf_hi - cdf_lo)
    u = np.clip(u, 1e-6, 1 - 1e-6)
    return norm.ppf(u)

def draw_copula_uniforms(rho, S, seed=42):
    """Amostras uniformes (S,2) com dependencia gaussiana (copula)."""
    rng = np.random.default_rng(seed)
    L = np.array([[1.0, 0.0], [rho, np.sqrt(max(1 - rho * rho, 1e-9))]])
    Z = rng.standard_normal((S, 2)) @ L.T
    return norm.cdf(Z)  # (S,2) uniformes correlacionadas

def _invcdf_samples(lam, r, U_col, grade):
    """Amostra contagens NB via CDF em grade + searchsorted (evita nbinom.ppf lento)."""
    K = 2 * grade
    ks = np.arange(K + 1)
    p = r / (r + lam)                       # (N,)
    cdf = nbinom.cdf(ks[None, :], r, p[:, None])  # (N, K+1) vetorizado e rapido
    cdf[:, -1] = 1.0
    out = np.empty((len(lam), len(U_col)), dtype=np.int32)
    for b in range(len(lam)):
        out[b] = np.searchsorted(cdf[b], U_col, side="left")
    return out

def mc_block(lam_h, lam_a, r_h, r_a, U, yt, line, grade, blk=200):
    """Vetorizado em blocos: retorna (ll_por_jogo, over_prob_por_jogo). U=(S,2)."""
    N = len(lam_h)
    ll = np.empty(N); over = np.empty(N)
    for s in range(0, N, blk):
        e = min(s + blk, N)
        sh = _invcdf_samples(lam_h[s:e], r_h, U[:, 0], grade)   # (B,S)
        sa = _invcdf_samples(lam_a[s:e], r_a, U[:, 1], grade)
        tot = sh + sa
        yb = yt[s:e][:, None]
        ll[s:e] = -np.log((tot == yb).mean(axis=1) + 1e-15)
        over[s:e] = (tot > line).mean(axis=1)
    return ll, over

def ece_ou(y, over, line):
    yb = (y > line).astype(float); e = 0.0; edges = np.linspace(0, 1, 11)
    for b in range(10):
        mk = (over >= edges[b]) & (over < edges[b + 1])
        if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - over[mk].mean())
    return float(e)

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    rows = []
    done = set()
    if OUT.exists():
        prev = pd.read_csv(OUT); rows = prev.to_dict("records"); done = set(prev["mercado"].unique())
        print(f"retomando: mercados ja feitos = {sorted(done)}", flush=True)
    cuts = np.linspace(0.5, 0.85, 4)
    # baratos primeiro (grade menor) p/ garantir checkpoint cedo
    markets_ord = sorted(MARKETS, key=lambda x: x[4])
    for mkt, ch, ca, line, grade in markets_ord:
        if mkt in done:
            continue
        sub = adv.dropna(subset=[ch, ca]).reset_index(drop=True) if mkt != "gols" else adv.reset_index(drop=True)
        for c in cuts:
            n = int(len(sub) * c); m = int(len(sub) * min(c + 0.15, 1.0))
            tr, te = sub.iloc[:n], sub.iloc[n:m]
            if len(te) < 30: continue
            # marginais NB de producao (GBR + r MLE) por lado
            from market_models_experiments import make_reg, fit_nb_r
            rh = make_reg("gbr").fit(tr[M.FEATS], tr[ch].astype(int).values)
            ra = make_reg("gbr").fit(tr[M.FEATS], tr[ca].astype(int).values)
            lam_h_tr = np.maximum(rh.predict(tr[M.FEATS]), 0.1); lam_a_tr = np.maximum(ra.predict(tr[M.FEATS]), 0.1)
            r_h = fit_nb_r(tr[ch].astype(int).values, lam_h_tr); r_a = fit_nb_r(tr[ca].astype(int).values, lam_a_tr)
            # rho point-in-time: correlacao dos escores normais PIT no treino
            zh = pit_normal(tr[ch].astype(int).values, lam_h_tr, r_h)
            za = pit_normal(tr[ca].astype(int).values, lam_a_tr, r_a)
            rho = float(np.corrcoef(zh, za)[0, 1]); rho = np.clip(rho, -0.85, 0.85)
            # teste
            lam_h_te = np.maximum(rh.predict(te[M.FEATS]), 0.1); lam_a_te = np.maximum(ra.predict(te[M.FEATS]), 0.1)
            yt = te[ch].astype(int).values + te[ca].astype(int).values
            S = 10000
            U_ind = draw_copula_uniforms(0.0, S); U_cop = draw_copula_uniforms(rho, S)
            ll_ind, over_ind = mc_block(lam_h_te, lam_a_te, r_h, r_a, U_ind, yt, line, grade)
            ll_cop, over_cop = mc_block(lam_h_te, lam_a_te, r_h, r_a, U_cop, yt, line, grade)
            rows.append({"mercado": mkt, "fold": round(c, 2), "n_test": len(te), "rho": rho,
                         "ll_indep": float(np.mean(ll_ind)), "ll_copula": float(np.mean(ll_cop)),
                         "dLL": float(np.mean(ll_cop) - np.mean(ll_ind)),
                         "ece_indep": ece_ou(yt, np.array(over_ind), line),
                         "ece_copula": ece_ou(yt, np.array(over_cop), line)})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        sm = pd.DataFrame([r for r in rows if r["mercado"] == mkt])
        print(f"[{mkt}] rho_medio={sm.rho.mean():+.3f}  dLL_total={sm.dLL.mean():+.4f}  "
              f"dECE={100*(sm.ece_copula.mean()-sm.ece_indep.mean()):+.2f}pp", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
