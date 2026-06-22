#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/experiment.py
================================
O GATE — testa se as features de Player-Level Power Ranking rivalizam/complementam
o Elo na previsao de RESULTADO (H/D/A). Extensivo:
  - 4 conjuntos de features: ELO | CURRENT (Elo+forma+h2h) | PLAYER | CURRENT+PLAYER
  - 2 subconjuntos: completo | alta-cobertura (min_cov>=0.7)
  - 2 modelos: HistGradientBoosting (lida c/ NaN) e Regressao Logistica
  - validacao: 5-fold CV repetido (3x) + split temporal (80/20 por data)
  - metricas: log-loss, ECE multiclasse, acuracia
Imprime tabelas comparativas. Sem promover nada — so medir.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "player_ranking" / "data" / "processed"
CLASSES = ["A", "D", "H"]

PLAYER_FEATS = ["diff_pr_rating", "diff_pr_rating_adj", "diff_pr_minutes_mean",
                "diff_pr_topleague_share", "diff_pr_leagueweight_mean", "diff_pr_depth",
                "diff_pr_goals90", "diff_pr_shots90", "diff_pr_keypass90"]
ELO_FEATS = ["elo_diff"]
CURRENT_FEATS = ["elo_diff", "diff_gd_l5", "h2h_home_gd_mean", "tournament_weight", "neutral"]

FEATURE_SETS = {
    "ELO": ELO_FEATS,
    "CURRENT (Elo+forma+h2h)": CURRENT_FEATS,
    "PLAYER": PLAYER_FEATS,
    "CURRENT+PLAYER": CURRENT_FEATS + PLAYER_FEATS,
}


def ece_mc(y_str, P, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    vals = []
    for i, c in enumerate(CLASSES):
        yb = (np.asarray(y_str) == c).astype(float)
        pb = P[:, i]
        e = 0.0
        for b in range(n_bins):
            m = (pb >= edges[b]) & (pb < edges[b + 1])
            if m.mean() > 0:
                e += m.mean() * abs(yb[m].mean() - pb[m].mean())
        vals.append(e)
    return float(np.mean(vals))


def make_model(kind):
    if kind == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                              min_samples_leaf=20, random_state=42)
    return Pipeline([("imp", SimpleImputer(strategy="median")),
                     ("sc", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=2000, C=1.0))])


def eval_cv(df, feats, kind):
    X = df[feats].to_numpy(dtype=float)
    y = df["result"].astype(str).to_numpy()
    skf = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=42)
    lls, eces, accs = [], [], []
    for tr, te in skf.split(X, y):
        model = make_model(kind)
        model.fit(X[tr], y[tr])
        P = model.predict_proba(X[te])
        # alinhar colunas a CLASSES
        cls = list(model.classes_)
        Pa = np.zeros((len(te), 3))
        for j, c in enumerate(CLASSES):
            if c in cls:
                Pa[:, j] = P[:, cls.index(c)]
        Pa = Pa / Pa.sum(axis=1, keepdims=True)
        lls.append(log_loss(y[te], Pa, labels=CLASSES))
        eces.append(ece_mc(y[te], Pa))
        accs.append(accuracy_score(y[te], [CLASSES[i] for i in Pa.argmax(1)]))
    return np.mean(lls), np.std(lls), np.mean(eces), np.mean(accs)


def eval_temporal(df, feats, kind, frac=0.8):
    d = df.sort_values("date")
    n = int(len(d) * frac)
    tr, te = d.iloc[:n], d.iloc[n:]
    Xtr, Xte = tr[feats].to_numpy(float), te[feats].to_numpy(float)
    ytr, yte = tr["result"].astype(str).to_numpy(), te["result"].astype(str).to_numpy()
    model = make_model(kind)
    model.fit(Xtr, ytr)
    P = model.predict_proba(Xte)
    cls = list(model.classes_)
    Pa = np.zeros((len(te), 3))
    for j, c in enumerate(CLASSES):
        if c in cls:
            Pa[:, j] = P[:, cls.index(c)]
    Pa = Pa / Pa.sum(axis=1, keepdims=True)
    return log_loss(yte, Pa, labels=CLASSES), ece_mc(yte, Pa), accuracy_score(yte, [CLASSES[i] for i in Pa.argmax(1)]), len(te)


def run_block(df, label):
    print(f"\n{'='*78}\nSUBCONJUNTO: {label}  (N={len(df)})\n{'='*78}")
    if len(df) < 40:
        print("(N insuficiente para avaliar — pulando)")
        return
    base_rate = df["result"].value_counts(normalize=True).to_dict()
    print("distribuicao resultado:", {k: round(v, 3) for k, v in base_rate.items()})
    for kind, kname in [("hgb", "HistGradientBoosting"), ("lr", "LogisticRegression")]:
        print(f"\n--- modelo: {kname} ---")
        print(f"{'feature set':<26} {'CV logloss':>16} {'CV ECE':>8} {'CV acc':>8} | "
              f"{'TEMP ll':>8} {'TEMP ECE':>9} {'TEMP acc':>8}")
        for name, feats in FEATURE_SETS.items():
            feats = [f for f in feats if f in df.columns]
            ll, sd, ece, acc = eval_cv(df, feats, kind)
            tll, tece, tacc, ntest = eval_temporal(df, feats, kind)
            print(f"{name:<26} {ll:>7.4f}±{sd:<7.4f} {100*ece:>6.1f}% {100*acc:>6.1f}% | "
                  f"{tll:>8.4f} {100*tece:>7.1f}% {100*tacc:>6.1f}%")


def analyze_redundancy(df):
    """Correlacao das features de player-ranking com elo_diff: se forem altas, o
    player so 'espelha' o Elo (sem informacao nova)."""
    print(f"\n{'='*78}\nREDUNDANCIA vs ELO (corr de Pearson com elo_diff, alta cobertura)\n{'='*78}")
    sub = df[(df["min_cov"] >= 0.7) & df["elo_diff"].notna()]
    for f in PLAYER_FEATS:
        if f in sub.columns:
            s = sub[[f, "elo_diff"]].dropna()
            if len(s) > 20:
                print(f"  {f:<28} corr={s[f].corr(s['elo_diff']):+.3f}  (n={len(s)})")


def analyze_importance(df):
    """Importancia por permutacao das features de player no modelo CURRENT+PLAYER."""
    from sklearn.inspection import permutation_importance
    sub = df[df["min_cov"] >= 0.7].copy()
    if len(sub) < 60:
        print("\n(importancia: N insuficiente na alta cobertura)")
        return
    feats = [f for f in (CURRENT_FEATS + PLAYER_FEATS) if f in sub.columns]
    X, y = sub[feats].to_numpy(float), sub["result"].astype(str).to_numpy()
    n = int(len(sub) * 0.75)
    model = make_model("hgb").fit(X[:n], y[:n])
    r = permutation_importance(model, X[n:], y[n:], n_repeats=15, random_state=42,
                               scoring="neg_log_loss")
    print(f"\n{'='*78}\nIMPORTANCIA (permutacao, queda de log-loss) — CURRENT+PLAYER, alta cobertura\n{'='*78}")
    order = np.argsort(r.importances_mean)[::-1]
    for i in order:
        tag = "  <PLAYER>" if feats[i] in PLAYER_FEATS else ""
        print(f"  {feats[i]:<28} {r.importances_mean[i]:+.4f} ± {r.importances_std[i]:.4f}{tag}")


def main():
    df = pd.read_parquet(PROC / "dataset_player_ranking.parquet")
    if "neutral" in df.columns:
        df["neutral"] = df["neutral"].astype(float)
    run_block(df, "COMPLETO")
    run_block(df[df["min_cov"] >= 0.5].copy(), "COBERTURA >=0.5")
    run_block(df[df["min_cov"] >= 0.7].copy(), "ALTA COBERTURA (min_cov>=0.7)")
    # jogos equilibrados (onde o Elo e fraco): a melhor chance do player-form
    if "elo_diff" in df.columns:
        bal = df[(df["min_cov"] >= 0.7) & (df["elo_diff"].abs() <= 100)].copy()
        run_block(bal, "EQUILIBRADOS |elo_diff|<=100 & alta cobertura")
    analyze_redundancy(df)
    analyze_importance(df)


if __name__ == "__main__":
    main()
