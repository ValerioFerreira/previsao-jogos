#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/exp5_attack_defense.py
======================================
EXP 5 — FORCA ATAQUE x DEFESA -> lambda (estilo Dixon-Coles) para os mercados de
CONTAGEM (finalizacoes, escanteios, a gol, cartoes). O DC de producao ja faz isso
para GOLS; aqui perguntamos se um modelo de forcas por SELECAO bate o GBR+features
de producao nesses mercados.

Modelo de forca (Poisson log-linear, regularizado):
   log E[count_home] = mu + att_home + def_away + home_adv
   log E[count_away] = mu + att_away + def_home
Ajuste via sklearn PoissonRegressor sobre design one-hot (att do time que conta,
def do adversario, indicador de mando), com regularizacao L2. Dispersao NB via MLE.
Comparado a GBR+NB de producao, CV temporal expanding, log-loss marginal + ECE.

Point-in-time: forcas estimadas so com jogos do treino; selecoes nao vistas usam media.
Saida: data/reports/exp5_attack_defense_results.csv
"""
from __future__ import annotations
import warnings
from pathlib import Path
import sys
import numpy as np, pandas as pd
from scipy.stats import nbinom
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import OneHotEncoder
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_models_experiments as M

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reports" / "exp5_attack_defense_results.csv"

MARKETS = [
    ("finalizacoes", "home_cur_sb_shots", "away_cur_sb_shots", 22.5, 55),
    ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25),
    ("finalizacoes_gol", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30),
    ("cartoes", "home_cur_sb_cards", "away_cur_sb_cards", 3.5, 15),
]

def build_long(tr, ch, ca):
    """Empilha (atacante, defensor, mando, count) para mandante e visitante."""
    home = pd.DataFrame({"att": tr["home_team"].values, "deff": tr["away_team"].values,
                         "is_home": 1.0, "y": tr[ch].astype(float).values})
    away = pd.DataFrame({"att": tr["away_team"].values, "deff": tr["home_team"].values,
                         "is_home": 0.0, "y": tr[ca].astype(float).values})
    return pd.concat([home, away], ignore_index=True)

def fit_strength(tr, ch, ca, alpha=1.0):
    long = build_long(tr, ch, ca)
    enc_a = OneHotEncoder(handle_unknown="ignore", sparse_output=True).fit(long[["att"]])
    enc_d = OneHotEncoder(handle_unknown="ignore", sparse_output=True).fit(long[["deff"]])
    from scipy.sparse import hstack, csr_matrix
    Xa = enc_a.transform(long[["att"]]); Xd = enc_d.transform(long[["deff"]])
    Xh = csr_matrix(long[["is_home"]].values)
    X = hstack([Xa, Xd, Xh]).tocsr()
    reg = PoissonRegressor(alpha=alpha, max_iter=600).fit(X, long["y"].values)
    return reg, enc_a, enc_d

def predict_lambda(reg, enc_a, enc_d, att, deff, is_home):
    from scipy.sparse import hstack, csr_matrix
    att = np.asarray(att); deff = np.asarray(deff); n = len(att)
    Xa = enc_a.transform(pd.DataFrame({"att": att})[["att"]])
    Xd = enc_d.transform(pd.DataFrame({"deff": deff})[["deff"]])
    Xh = csr_matrix(np.full((n, 1), float(is_home)))
    X = hstack([Xa, Xd, Xh]).tocsr()
    return np.maximum(reg.predict(X), 0.1)

def fit_nb_r(y, lam):
    from market_models_experiments import fit_nb_r as f
    return f(y, lam)

def marg_pmf(lam, r, grade):
    ks = np.arange(grade + 1); p = r / (r + lam[:, None])
    P = nbinom.pmf(ks[None, :], r, p); return P / P.sum(1, keepdims=True)

def ece_ou(y, over, line):
    yb = (y > line).astype(float); e = 0.0; edges = np.linspace(0, 1, 11)
    for b in range(10):
        mk = (over >= edges[b]) & (over < edges[b + 1])
        if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - over[mk].mean())
    return float(e)

def eval_count_ll(y, P):
    idx = np.clip(y, 0, P.shape[1] - 1)
    return float(-np.mean(np.log(P[np.arange(len(y)), idx] + 1e-15)))

def main():
    df = pd.read_csv(M.CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4)
    rows = []
    for mkt, ch, ca, line, grade in MARKETS:
        sub = adv.dropna(subset=[ch, ca, "home_team", "away_team"]).reset_index(drop=True)
        for c in cuts:
            n = int(len(sub) * c); m = int(len(sub) * min(c + 0.15, 1.0))
            tr, te = sub.iloc[:n], sub.iloc[n:m]
            if len(te) < 30: continue
            # ---- forca ataque x defesa
            reg, ea, ed = fit_strength(tr, ch, ca, alpha=1.0)
            lam_h_tr = predict_lambda(reg, ea, ed, tr["home_team"], tr["away_team"], 1.0)
            lam_a_tr = predict_lambda(reg, ea, ed, tr["away_team"], tr["home_team"], 0.0)
            r_h = fit_nb_r(tr[ch].astype(int).values, lam_h_tr); r_a = fit_nb_r(tr[ca].astype(int).values, lam_a_tr)
            lam_h = predict_lambda(reg, ea, ed, te["home_team"], te["away_team"], 1.0)
            lam_a = predict_lambda(reg, ea, ed, te["away_team"], te["home_team"], 0.0)
            Ph = marg_pmf(lam_h, r_h, grade); Pa = marg_pmf(lam_a, r_a, grade)
            # ---- GBR+NB producao
            Pgh, _ = M.build_pmf("gbr", "nb", tr[M.FEATS], tr[ch].astype(int).values, te[M.FEATS], grade)
            Pga, _ = M.build_pmf("gbr", "nb", tr[M.FEATS], tr[ca].astype(int).values, te[M.FEATS], grade)
            yh = te[ch].astype(int).values; ya = te[ca].astype(int).values
            for lado, P_ad, P_gbr, y, ln in [("mandante", Ph, Pgh, yh, line / 2),
                                             ("visitante", Pa, Pga, ya, line / 2)]:
                k0 = int(np.floor(ln)) + 1
                rows.append({"mercado": mkt, "lado": lado, "fold": round(c, 2), "n_test": len(te),
                             "ll_attdef": eval_count_ll(y, P_ad), "ll_gbr": eval_count_ll(y, P_gbr),
                             "dLL": eval_count_ll(y, P_ad) - eval_count_ll(y, P_gbr),
                             "ece_attdef": ece_ou(y, P_ad[:, k0:].sum(1), ln),
                             "ece_gbr": ece_ou(y, P_gbr[:, k0:].sum(1), ln)})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        sm = pd.DataFrame([r for r in rows if r["mercado"] == mkt])
        print(f"[{mkt}] dLL(attdef-gbr)={sm.dLL.mean():+.4f}  "
              f"ll_gbr={sm.ll_gbr.mean():.4f} ll_attdef={sm.ll_attdef.mean():.4f}  "
              f"dECE={100*(sm.ece_attdef.mean()-sm.ece_gbr.mean()):+.2f}pp", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
