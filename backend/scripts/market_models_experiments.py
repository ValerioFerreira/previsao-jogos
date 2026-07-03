#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/market_models_experiments.py
=============================================
FASE 2 — bateria do zero para os MERCADOS DE CONTAGEM (foco do projeto):
gols, finalizações, finalizações a gol, escanteios, cartões — por equipe (mandante/
visitante) e por tempo (gols/cartões 1º/2º), comparando exaustivamente:

  Regressor de média (lambda):   GBR(squared) · HGB(poisson) · HGB(squared)
  Distribuição de contagem:      Poisson · NegBinom(r via MLE) · GeneralizedPoisson(MLE)

Avaliação (split temporal 80/20 por data, sem leakage — features pré-jogo):
  - log-loss de contagem (PMF no valor observado)  [PRIMÁRIA]
  - ECE da linha O/U principal (calibração)
  - MAE da média
Salva CSV resumível: backend/data/reports/market_models_results.csv

Uso: python backend/scripts/market_models_experiments.py
"""
from __future__ import annotations
import warnings, json, time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson
from scipy.optimize import minimize_scalar, minimize
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "international_features_enriched_apifootball.csv"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
HALFT = ROOT / "data" / "built" / "halftime_targets.parquet"
OUT = ROOT / "data" / "reports" / "market_models_results.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

# features pré-jogo (sem box-score do próprio jogo): base_feats da produção
FEATS = [f for f in META["base_feats"]]

# ----------------------------------------------------------------- distribuições
def fit_nb_r(y, lam):
    lam = np.maximum(lam, 1e-3)
    def nll(r):
        if r <= 0.05: return 1e12
        p = r / (r + lam)
        return -np.sum(np.log(nbinom.pmf(y, n=r, p=p) + 1e-15))
    res = minimize_scalar(nll, bounds=(0.1, 1000), method="bounded")
    return float(res.x)

def fit_gp_lambda(y, mu):
    mu = np.maximum(mu, 1e-3)
    def nll(a):
        a = a[0]
        lam = mu * (1 - a)               # reparam: media = mu
        lam = np.maximum(lam, 1e-6)
        m = lam + a * y
        m = np.maximum(m, 1e-9)
        ll = np.log(lam) + (y - 1) * np.log(m) - m - np.array([np.sum(np.log(np.arange(1, k + 1))) if k > 0 else 0 for k in y])
        return -np.sum(ll)
    res = minimize(nll, [0.0], bounds=[(-0.4, 0.6)], method="L-BFGS-B")
    return float(res.x[0])

def pmf_poisson(k, lam): return poisson.pmf(k, np.maximum(lam, 1e-6))
def pmf_nb(k, lam, r):
    lam = np.maximum(lam, 1e-6); p = r / (r + lam)
    return nbinom.pmf(k, n=r, p=p)
def pmf_gp(k, mu, a):
    mu = np.maximum(mu, 1e-6); lam = np.maximum(mu * (1 - a), 1e-6)
    m = np.maximum(lam + a * k, 1e-9)
    from scipy.special import gammaln
    logpmf = np.log(lam) + (k - 1) * np.log(m) - m - gammaln(k + 1)
    return np.exp(logpmf)

# ----------------------------------------------------------------- mean models
def make_reg(kind):
    if kind == "gbr":
        return Pipeline([("imp", SimpleImputer(strategy="median")),
                         ("r", GradientBoostingRegressor(loss="squared_error", n_estimators=100,
                                                          max_depth=3, learning_rate=0.05, random_state=42))])
    if kind == "hgb_pois":
        return HistGradientBoostingRegressor(loss="poisson", max_depth=3, max_iter=300,
                                             learning_rate=0.05, min_samples_leaf=30, random_state=42)
    return HistGradientBoostingRegressor(loss="squared_error", max_depth=3, max_iter=300,
                                         learning_rate=0.05, min_samples_leaf=30, random_state=42)

# ----------------------------------------------------------------- avaliação
def count_logloss(y, pmf_matrix):
    idx = np.clip(y, 0, pmf_matrix.shape[1] - 1).astype(int)
    p = pmf_matrix[np.arange(len(y)), idx]
    return float(-np.mean(np.log(p + 1e-15)))

def ece_ou(y, over_prob, line):
    yb = (y > line).astype(float); pb = over_prob; e = 0.0
    edges = np.linspace(0, 1, 11)
    for b in range(10):
        m = (pb >= edges[b]) & (pb < edges[b + 1])
        if m.mean() > 0: e += m.mean() * abs(yb[m].mean() - pb[m].mean())
    return float(e)

def build_pmf(reg_kind, dist, Xtr, ytr, Xte, grade):
    reg = make_reg(reg_kind).fit(Xtr, ytr)
    lam_tr = np.maximum(reg.predict(Xtr), 1e-3)
    lam_te = np.maximum(reg.predict(Xte), 1e-3)
    ks = np.arange(grade + 1)
    if dist == "poisson":
        P = pmf_poisson(ks[None, :], lam_te[:, None])
    elif dist == "nb":
        r = fit_nb_r(ytr, lam_tr)
        P = pmf_nb(ks[None, :], lam_te[:, None], r)
    else:  # gp
        a = fit_gp_lambda(ytr, lam_tr)
        P = pmf_gp(ks[None, :], lam_te[:, None], a)
    P = P / P.sum(axis=1, keepdims=True)
    return P, lam_te

def main():
    t0 = time.time()
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy()
    # juntar alvos por tempo (gols/cartões 1º/2º)
    ht = pd.read_parquet(HALFT)
    adv["dkey"] = adv["date"].astype(str).str[:10]
    adv = adv.merge(ht, left_on=["dkey", "home_team", "away_team"],
                    right_on=["date", "home_team", "away_team"], how="left", suffixes=("", "_ht"))

    # (mercado, coluna alvo mandante, alvo visitante, linha O/U principal, grade)
    MARKETS = [
        ("gols", "home_score", "away_score", 2.5, 12),
        ("finalizacoes", "home_cur_sb_shots", "away_cur_sb_shots", 22.5, 55),
        ("finalizacoes_gol", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", 7.5, 30),
        ("escanteios", "home_cur_sb_corners", "away_cur_sb_corners", 9.5, 25),
        ("cartoes", "home_cur_sb_cards", "away_cur_sb_cards", 3.5, 15),
        ("gols_1t", "home_goals_1t", "away_goals_1t", 0.5, 8),
        ("gols_2t", "home_goals_2t", "away_goals_2t", 1.5, 8),
        ("cartoes_1t", "home_cards_1t", "away_cards_1t", 1.5, 12),
        ("cartoes_2t", "home_cards_2t", "away_cards_2t", 2.5, 12),
    ]
    REGS = ["gbr", "hgb_pois", "hgb_sq"]
    DISTS = ["poisson", "nb", "gp"]

    done = set()
    rows = []
    if OUT.exists():
        prev = pd.read_csv(OUT); rows = prev.to_dict("records")
        done = set(zip(prev["mercado"], prev["lado"], prev["reg"], prev["dist"]))
        print(f"retomando: {len(rows)} linhas", flush=True)

    for mkt, ch, ca, line, grade in MARKETS:
        sub = adv.dropna(subset=[ch, ca]).copy().sort_values("date")
        if len(sub) < 200:
            print(f"[{mkt}] N={len(sub)} insuficiente — pulado", flush=True); continue
        n = int(len(sub) * 0.8)
        tr, te = sub.iloc[:n], sub.iloc[n:]
        Xtr, Xte = tr[FEATS], te[FEATS]
        for lado, col, ln in [("mandante", ch, line/2), ("visitante", ca, line/2), ("total", None, line)]:
            for reg in REGS:
                for dist in DISTS:
                    if (mkt, lado, reg, dist) in done:
                        continue
                    try:
                        if lado == "total":
                            Ph, _ = build_pmf(reg, dist, Xtr, tr[ch].astype(int).values, Xte, grade)
                            Pa, _ = build_pmf(reg, dist, Xtr, tr[ca].astype(int).values, Xte, grade)
                            # convolução -> total
                            Pt = np.zeros((len(te), 2*grade+1))
                            for i in range(len(te)):
                                Pt[i] = np.convolve(Ph[i], Pa[i])
                            yt = (te[ch].astype(int).values + te[ca].astype(int).values)
                            ll = count_logloss(yt, Pt)
                            over = Pt[:, int(np.floor(ln))+1:].sum(axis=1)
                            ece = ece_ou(yt, over, ln)
                            mae = float(np.mean(np.abs(yt - (Ph@np.arange(grade+1) + Pa@np.arange(grade+1)))))
                        else:
                            y = te[col].astype(int).values
                            P, lam = build_pmf(reg, dist, Xtr, tr[col].astype(int).values, Xte, grade)
                            ll = count_logloss(y, P)
                            over = P[:, int(np.floor(ln))+1:].sum(axis=1)
                            ece = ece_ou(y, over, ln)
                            mae = float(np.mean(np.abs(y - lam)))
                        rows.append({"mercado": mkt, "lado": lado, "reg": reg, "dist": dist,
                                     "n_train": len(tr), "n_test": len(te), "linha": ln,
                                     "count_logloss": ll, "ou_ece": ece, "mae": mae})
                    except Exception as e:
                        rows.append({"mercado": mkt, "lado": lado, "reg": reg, "dist": dist,
                                     "erro": str(e)[:80]})
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"[{mkt}/{lado}] feito ({len(rows)} linhas)", flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"FEITO em {(time.time()-t0)/60:.1f} min -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
