#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_era_goals.py
===============================
Passo 1 / #5 — testa se uma FEATURE DE ERA (year>=2022, "era VAR/super-acrescimos")
no Dixon-Coles colapsa o vies estrutural de gols (-0.11, invariante ao decay) SEM
piorar log-loss/ECE OOS. Confirmado que year/era NAO esta em base_feats hoje.

Split temporal 80/20 (treina passado, testa recente). Compara DC base vs DC+era.
Gate: vies -> ~0 E log-loss/ECE de resultado/gols nao pioram. Nao toca producao.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api")); sys.path.insert(0, "scripts")
from dixon_coles_model import DixonColesNBRegressor
warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def multiclass_ece(y_true, P, classes, n_bins=10):
    pred = np.array([classes[i] for i in P.argmax(1)])
    conf = P.max(1)
    correct = (pred == np.asarray(y_true)).astype(float)
    bins = np.linspace(0, 1, n_bins + 1); e = 0.0; n = len(y_true)
    for i in range(n_bins):
        m = (conf >= bins[i]) & (conf < bins[i + 1])
        if m.sum() > 0:
            e += (m.sum() / n) * abs(correct[m].mean() - conf[m].mean())
    return e

META = json.load(open(ROOT / "api/model_artifacts/meta.json", encoding="utf-8"))
BASE = META["base_feats"]


def evaluate(df, feats, label):
    df = df.sort_values("date").reset_index(drop=True)
    cut = df.iloc[int(len(df) * 0.8)]["date"]
    tr, te = df[df["date"] <= cut], df[df["date"] > cut]
    dc = DixonColesNBRegressor(max_goals=12)
    dc.fit(tr[feats], tr["home_score"].values, tr["away_score"].values)
    pm = dc.predict_proba_markets(te[feats])
    # total de gols da matriz conjunta
    M = dc.max_goals; J = pm["joint"]
    td = np.zeros((len(te), 2 * M + 1))
    for x in range(M + 1):
        for y in range(M + 1):
            td[:, x + y] += J[:, x, y]
    td /= td.sum(1, keepdims=True)
    e_tot = td @ np.arange(2 * M + 1)
    actual = te["total_goals"].values
    bias = float(e_tot.mean() - actual.mean())
    gll = float(-np.mean(np.log(td[np.arange(len(te)), np.clip(actual, 0, 2 * M).astype(int)] + 1e-15)))
    classes = ["A", "D", "H"]; P = pm["result"]; y = te["result"].values
    rll = float(log_loss(y, P, labels=classes))
    rece = float(multiclass_ece(y, P, classes))
    print(f"[{label}] vies_gols {bias:+.3f} | gols_logloss {gll:.4f} | result_logloss {rll:.4f} | result_ECE {rece:.2%} | n_test {len(te)}")
    return {"bias": bias, "gll": gll, "rll": rll, "rece": rece}


def main():
    df = pd.read_csv(ROOT / "international_features_enriched_apifootball.csv", parse_dates=["date"])
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    df["era_pos2022"] = (df["date"].dt.year >= 2022).astype(int)
    print(f"jogos: {len(df)} | era_pos2022=1: {int(df['era_pos2022'].sum())}")
    base = evaluate(df, BASE, "BASE")
    era = evaluate(df, BASE + ["era_pos2022"], "BASE+era")
    print("\n=== VEREDITO ===")
    print(f"  vies: {base['bias']:+.3f} -> {era['bias']:+.3f}")
    print(f"  gols_logloss: {base['gll']:.4f} -> {era['gll']:.4f}  ({'melhora' if era['gll']<=base['gll'] else 'PIORA'})")
    print(f"  result_logloss: {base['rll']:.4f} -> {era['rll']:.4f}  ({'melhora' if era['rll']<=base['rll']+1e-4 else 'PIORA'})")
    print(f"  result_ECE: {base['rece']:.2%} -> {era['rece']:.2%}")
    ok = abs(era["bias"]) < abs(base["bias"]) and era["gll"] <= base["gll"] + 1e-3 and era["rll"] <= base["rll"] + 2e-3
    print("  PROMOVER?", "SIM (vies cai sem regressao)" if ok else "NAO (sem ganho liquido)")


if __name__ == "__main__":
    main()
