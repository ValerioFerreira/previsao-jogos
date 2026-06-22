#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/experiment_shots_feature_goals.py
=========================================
Passo 2 / #4 — testa injetar a EXPECTATIVA DE CHUTES (output do ShotsNB) como feature
no Dixon-Coles de gols. O DC roda em base_feats (SEM box-score), entao a previsao de
chutes (que usa o historico de chutes) traz sinal de volume ofensivo que o DC nao tem.

Imputacao indicativa (proposta do usuario): onde nao ha box-score, pred_shots vira a
mediana + feature binaria has_boxscore_signal=0, para o modelo nao distorcer o peso.

Split temporal 80/20. DC base vs DC + [pred_shots, has_boxscore_signal]. Gate:
log-loss/ECE de resultado E gols melhoram OOS, sem regressao. Nao toca producao.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api")); sys.path.insert(0, "scripts")
from dixon_coles_model import DixonColesNBRegressor
from shots_nb_model import ShotsNB
warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

META = json.load(open(ROOT / "api/model_artifacts/meta.json", encoding="utf-8"))
BASE, FULL = META["base_feats"], META["full_feats"]


def multiclass_ece(y, P, classes, n_bins=10):
    pred = np.array([classes[i] for i in P.argmax(1)]); conf = P.max(1)
    correct = (pred == np.asarray(y)).astype(float); bins = np.linspace(0, 1, n_bins + 1); e = 0.0; n = len(y)
    for i in range(n_bins):
        m = (conf >= bins[i]) & (conf < bins[i + 1])
        if m.sum() > 0: e += (m.sum() / n) * abs(correct[m].mean() - conf[m].mean())
    return e


def evaluate(df, feats, label):
    df = df.sort_values("date").reset_index(drop=True)
    cut = df.iloc[int(len(df) * 0.8)]["date"]
    tr, te = df[df["date"] <= cut], df[df["date"] > cut]
    dc = DixonColesNBRegressor(max_goals=12)
    dc.fit(tr[feats], tr["home_score"].values, tr["away_score"].values)
    pm = dc.predict_proba_markets(te[feats]); M = dc.max_goals; J = pm["joint"]
    td = np.zeros((len(te), 2 * M + 1))
    for x in range(M + 1):
        for y in range(M + 1): td[:, x + y] += J[:, x, y]
    td /= td.sum(1, keepdims=True)
    actual = te["total_goals"].values
    gll = float(-np.mean(np.log(td[np.arange(len(te)), np.clip(actual, 0, 2 * M).astype(int)] + 1e-15)))
    bias = float((td @ np.arange(2 * M + 1)).mean() - actual.mean())
    classes = ["A", "D", "H"]
    rll = float(log_loss(te["result"].values, pm["result"], labels=classes))
    rece = float(multiclass_ece(te["result"].values, pm["result"], classes))
    print(f"[{label}] result_logloss {rll:.4f} | result_ECE {rece:.2%} | gols_logloss {gll:.4f} | vies {bias:+.3f}")
    return {"rll": rll, "rece": rece, "gll": gll, "bias": bias}


def main():
    df = pd.read_csv(ROOT / "international_features_enriched_apifootball.csv", parse_dates=["date"])
    df = df.dropna(subset=["home_score", "away_score"]).copy()
    print("computando pred_shots (ShotsNB) para todos os jogos...")
    shots = ShotsNB.load(str(ROOT / "api/model_artifacts/shots_nb.joblib"))
    d = shots.predict_distributions(df[FULL])
    kt = np.arange(2 * shots.max_corners + 1)
    df["pred_shots"] = d["total"] @ kt
    df["has_boxscore_signal"] = df["has_advanced_stats"].fillna(0).astype(int)
    # imputacao indicativa: onde nao ha sinal, pred_shots = mediana global
    med = df.loc[df.has_boxscore_signal == 1, "pred_shots"].median()
    df.loc[df.has_boxscore_signal == 0, "pred_shots"] = med
    print(f"jogos {len(df)} | com box-score {int(df.has_boxscore_signal.sum())} | pred_shots medio {df.pred_shots.mean():.1f}")
    base = evaluate(df, BASE, "BASE")
    ext = evaluate(df, BASE + ["pred_shots", "has_boxscore_signal"], "BASE+chutes")
    print("\n=== VEREDITO ===")
    print(f"  result_logloss: {base['rll']:.4f} -> {ext['rll']:.4f}  ({'melhora' if ext['rll']<base['rll'] else 'PIORA/igual'})")
    print(f"  result_ECE: {base['rece']:.2%} -> {ext['rece']:.2%}")
    print(f"  gols_logloss: {base['gll']:.4f} -> {ext['gll']:.4f}  ({'melhora' if ext['gll']<base['gll'] else 'PIORA/igual'})")
    ok = ext["rll"] < base["rll"] - 1e-4 and ext["gll"] <= base["gll"] + 1e-3 and ext["rece"] <= base["rece"] + 0.003
    print("  PROMOVER?", "SIM" if ok else "NAO (sem ganho liquido)")


if __name__ == "__main__":
    main()
