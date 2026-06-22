#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_timedecay.py
===============================
Fase A do peso temporal: mede se ponderar jogos recentes (sample_weight com
decaimento por dias) reduz o vies temporal documentado (modelo subestima o
presente) SEM piorar a calibracao. Nao toca producao.

Para cada alvo de contagem, treina o regressor de lambda (GBR, mesma receita da
producao) COM e SEM decaimento, varrendo a meia-vida H, e mede no test-fold
recente: vies (media prevista - real), log-loss, ECE de uma linha O/U.

Peso: w = 0.5^((ancora - data)/H), ancora = data max do treino. H em anos.
O r de dispersao e estimado sem peso (dispersao nao e a alavanca do vies).
Diagnostico: varre H no teste para ver SE ajuda e a forma; a escolha final de H
para promocao usara split de validacao (Fase B) — aqui o objetivo e existir efeito.
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
from sklearn.metrics import log_loss

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
BASE_FEATS, FULL_FEATS = META["base_feats"], META["full_feats"]
H_YEARS = [None, 5, 3, 2, 1]   # None = sem decaimento
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
    return float(minimize(obj, [5.0], bounds=[(0.1, 1000.0)], method="L-BFGS-B").x[0])


def decay_weights(dates, anchor, H_years):
    if H_years is None:
        return np.ones(len(dates))
    dd = (anchor - dates).dt.days.values.astype(float)
    return 0.5 ** (dd / (H_years * 365.0))


def nb_pmf(lam, r, maxc):
    k = np.arange(maxc + 1)
    out = np.zeros((len(lam), maxc + 1))
    for i, l in enumerate(lam):
        pm = nbinom.pmf(k, n=r, p=r / (r + l))
        out[i] = pm / pm.sum()
    return out


def ece_over(prob, actual, line):
    y = (actual > line).astype(int)
    p = prob[:, int(line) + 1:].sum(axis=1)
    bins = np.linspace(0, 1, 11)
    e = 0.0
    for i in range(10):
        m = (p >= bins[i]) & (p < bins[i + 1])
        if m.mean() > 0:
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return e


def run_target(df, name, target, feats, adv_only, maxc):
    d = df.copy()
    if adv_only:
        d = d[d["has_advanced_stats"] == 1]
    d = d.dropna(subset=[target] if isinstance(target, str) else target).reset_index(drop=True)
    if not isinstance(target, str):
        d["_y"] = d[target[0]].astype(int) + d[target[1]].astype(int)
        y = "_y"
    else:
        d["_y"] = d[target].astype(int)
        y = "_y"
    d = d.sort_values("date").reset_index(drop=True)
    cut = d.iloc[int(len(d) * 0.8)]["date"]
    tr, te = d[d["date"] <= cut], d[d["date"] > cut]
    anchor = tr["date"].max()
    line = max(0.5, np.floor(d["_y"].mean()) + 0.5)
    yt = te["_y"].values
    real = float(yt.mean())

    rows = []
    for H in H_YEARS:
        w = decay_weights(tr["date"], anchor, H)
        m = gbr(); m.fit(tr[feats], tr["_y"].values, reg__sample_weight=w)
        lam_tr = np.maximum(m.predict(tr[feats]), 0.05)
        lam_te = np.maximum(m.predict(te[feats]), 0.05)
        r = opt_r(tr["_y"].values, lam_tr)
        prob = nb_pmf(lam_te, r, maxc)
        bias = float(lam_te.mean() - real)
        ll = float(-np.mean(np.log(prob[np.arange(len(te)), np.clip(yt, 0, maxc)] + 1e-15)))
        ece = float(ece_over(prob, yt, line))
        rows.append((H, bias, ll, ece))
    return name, real, line, rows


def main():
    df = pd.read_csv("international_features_enriched_apifootball.csv", parse_dates=["date"], low_memory=False)
    targets = [
        ("Gols total", "total_goals", BASE_FEATS, False, 24),
        ("Escanteios mandante", "home_cur_sb_corners", FULL_FEATS, True, 25),
        ("Escanteios visitante", "away_cur_sb_corners", FULL_FEATS, True, 25),
        ("Cartoes total", ("home_cur_sb_cards", "away_cur_sb_cards"), FULL_FEATS, True, 30),
        ("Chutes total", ("home_cur_sb_shots", "away_cur_sb_shots"), FULL_FEATS, True, 60),
    ]
    out_lines = ["# Experimento — Peso Temporal (time decay) — Fase A", "",
                 "Vies = media prevista (lambda) - media real no test-fold recente (negativo = subestima).",
                 "H = meia-vida em anos (None = sem decaimento). Linha O/U entre parenteses.", ""]
    for nm, tgt, feats, adv, mc in targets:
        name, real, line, rows = run_target(df, nm, tgt, feats, adv, mc)
        out_lines.append(f"## {name}  (real medio {real:.2f}, linha O{line})")
        out_lines.append("| H (anos) | Vies | LogLoss | ECE |")
        out_lines.append("|---|---|---|---|")
        base_bias = rows[0][1]
        for H, bias, ll, ece in rows:
            tag = " (sem decay)" if H is None else ""
            out_lines.append(f"| {H if H else 'inf'}{tag} | {bias:+.3f} | {ll:.4f} | {ece:.2%} |")
        out_lines.append("")
        print(f"{name}: vies sem decay {base_bias:+.3f} -> " +
              " ".join(f"H{H}={b:+.3f}" for H, b, _, _ in rows if H))
    Path("scratch/experimento_historico/timedecay_faseA.md").write_text("\n".join(out_lines), encoding="utf-8")
    print("\nRelatorio: scratch/experimento_historico/timedecay_faseA.md")
    print("\n".join(out_lines))


if __name__ == "__main__":
    main()
