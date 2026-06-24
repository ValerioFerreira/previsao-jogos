#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/sweep_experiments.py
============================
Sweep de experimentos sobre o modelo de GOLS (Dixon-Coles NB), em dados existentes,
com split temporal OOS. Avalia variações de PESO e de FEATURES por log-loss/ECE.

NÃO toca produção — fita modelos novos a cada config e mede OOS. Gera relatório em
data/reports/sweep_experiments.md.

Experimentos:
  1. baseline (sem peso).
  2. time-decay: peso = 0.5^(idade_dias / meia_vida), varrendo meia-vida.
  3. peso por competição: downweight amistosos / upweight competitivos / tournament_weight.
  4. chutes->gols: base_feats + features de chutes (e só chutes a gol) — testa se chutes
     informam gols além do que o Elo+base já capturam (re-teste honesto da prop #4).
  5. condicional: para PREVER jogos de torneio grande (majors), pesar mais os majors
     no treino ajuda? (avaliação no subconjunto de majors do teste).
"""
from __future__ import annotations
import sys, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CSV = ROOT / "international_features_enriched_apifootball.csv"
META = ROOT / "api" / "model_artifacts" / "meta.json"
REPORT = ROOT / "data" / "reports" / "sweep_experiments.md"

CUTS = ["2024-06-01", "2025-01-01"]   # 2 folds temporais (treino<cut, teste>=cut)
RESULT_ORDER = ["A", "D", "H"]        # predict_proba_markets['result'] -> [A,D,H]

SHOT_FEATS = [
    "home_sb_shots_l5", "away_sb_shots_l5", "diff_sb_shots_l5",
    "home_sb_shots_on_target_l5", "away_sb_shots_on_target_l5", "diff_sb_shots_on_target_l5",
    "home_sb_shots_against_l5", "away_sb_shots_against_l5",
    "home_sb_shots_on_target_against_l5", "away_sb_shots_on_target_against_l5",
]


def ece(y_true01, p, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1); e = 0.0
    for i in range(n_bins):
        m = (p >= edges[i]) & (p < edges[i + 1])
        if m.mean() > 0:
            e += m.mean() * abs(y_true01[m].mean() - p[m].mean())
    return e


def eval_model(m, te, feats):
    Xte = te[feats]
    dc = m.predict_proba_markets(Xte)
    res = dc["result"]                       # (N,3) [A,D,H]
    ymap = {"A": 0, "D": 1, "H": 2}
    yi = te["result"].map(ymap).values
    p_true = res[np.arange(len(te)), yi]
    res_ll = float(-np.mean(np.log(p_true + 1e-15)))
    conf = res.max(axis=1); correct = (res.argmax(axis=1) == yi).astype(float)
    res_ece = ece(correct, conf)
    # total de gols
    joint = dc["joint"]; M = m.max_goals
    tg = te["total_goals"].clip(0, 2 * M).astype(int).values
    Pt = np.zeros((len(te), 2 * M + 1))
    for n in range(len(te)):
        for x in range(M + 1):
            for y in range(M + 1):
                Pt[n, x + y] += joint[n, x, y]
    Pt /= Pt.sum(axis=1, keepdims=True)
    goals_nll = float(-np.mean(np.log(Pt[np.arange(len(te)), tg] + 1e-15)))
    pov = Pt[:, 3:].sum(axis=1)               # P(total >= 3) = over 2.5
    over_true = (te["total_goals"].values > 2.5).astype(float)
    over_brier = float(np.mean((pov - over_true) ** 2))
    over_ece = ece(over_true, pov)
    mae = float(np.mean(np.abs((dc_lam(m, Xte)) - te["total_goals"].values)))
    return dict(res_ll=res_ll, res_ece=res_ece, goals_nll=goals_nll,
                over_brier=over_brier, over_ece=over_ece, mae=mae)


def dc_lam(m, X):
    return np.maximum(m.model_home_.predict(X), 1e-4) + np.maximum(m.model_away_.predict(X), 1e-4)


def make_weight(name, tr):
    age = (tr["date"].max() - tr["date"]).dt.days.values.astype(float)
    if name.startswith("decay"):
        hl = float(name.split("_")[1])
        return np.power(0.5, age / hl)
    if name == "friendly0.5":
        return np.where(tr["is_friendly"].values == 1, 0.5, 1.0)
    if name == "friendly0.25":
        return np.where(tr["is_friendly"].values == 1, 0.25, 1.0)
    if name == "competitive_up":
        return np.where(tr["is_competitive"].values == 1, 1.0, 0.5)
    if name == "tournament_weight":
        return tr["tournament_weight"].values.astype(float)
    if name == "majors_up":
        return np.where(tr["is_major_final"].values == 1, 3.0, 1.0)
    return None


def fit_eval(tr, te, feats, weight_name):
    m = DixonColesNBRegressor()
    w = make_weight(weight_name, tr) if weight_name else None
    m.fit(tr[feats], tr["home_score"].values, tr["away_score"].values, sample_weight=w)
    return eval_model(m, te, feats)


def run_config(df, base_feats, feats, weight_name, test_filter=None):
    accs = []
    for cut in CUTS:
        cut = pd.Timestamp(cut)
        tr = df[df["date"] < cut]
        te = df[df["date"] >= cut]
        if test_filter is not None:
            te = te[test_filter(te)]
        if len(te) < 30 or len(tr) < 200:
            continue
        accs.append(fit_eval(tr, te, feats, weight_name))
    if not accs:
        return None
    return {k: float(np.mean([a[k] for a in accs])) for k in accs[0]}, int(np.mean([1])), len(accs)


def main():
    meta = json.load(open(META, encoding="utf-8"))
    base_feats = meta["base_feats"]
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    df = df.dropna(subset=["home_score", "away_score", "result", "total_goals"]).copy()
    shot_feats = [c for c in SHOT_FEATS if c in df.columns]
    feats_with_shots = base_feats + [c for c in shot_feats if c not in base_feats]
    shot_on_only = [c for c in shot_feats if "on_target" in c]
    feats_with_shotsontgt = base_feats + [c for c in shot_on_only if c not in base_feats]

    print(f"N total: {len(df)} | base_feats: {len(base_feats)} | shot_feats add: {len(shot_feats)}")

    experiments = [
        ("baseline", base_feats, None, None),
        ("decay_180", base_feats, "decay_180", None),
        ("decay_365", base_feats, "decay_365", None),
        ("decay_730", base_feats, "decay_730", None),
        ("decay_1095", base_feats, "decay_1095", None),
        ("decay_1460", base_feats, "decay_1460", None),
        ("friendly_w0.5", base_feats, "friendly0.5", None),
        ("friendly_w0.25", base_feats, "friendly0.25", None),
        ("competitive_up", base_feats, "competitive_up", None),
        ("tournament_weight", base_feats, "tournament_weight", None),
        ("shots->goals (base+chutes)", feats_with_shots, None, None),
        ("shots_on_tgt->goals", feats_with_shotsontgt, None, None),
    ]

    rows = []
    for name, feats, wname, tf in experiments:
        print(f">> {name} ...")
        out = run_config(df, base_feats, feats, wname, tf)
        if out:
            metrics, _, nfold = out
            rows.append((name, metrics, nfold))

    # Condicional: prever MAJORS — baseline vs upweight majors (avaliado só em majors)
    major_filter = lambda d: d["is_major_final"].values == 1
    cond = []
    for name, wname in [("majors: baseline", None), ("majors: majors_up x3", "majors_up")]:
        out = run_config(df, base_feats, base_feats, wname, major_filter)
        if out:
            cond.append((name, out[0], out[2]))

    base = next((m for n, m, _ in rows if n == "baseline"), None)
    def delta(metrics, key):
        if not base: return ""
        d = metrics[key] - base[key]
        return f" ({d:+.4f})"

    lines = ["# Sweep de Experimentos — Modelo de Gols (Dixon-Coles NB)", ""]
    lines.append(f"- Split temporal OOS, folds em: {CUTS} (treino<cut, teste>=cut), métricas médias.")
    lines.append(f"- N total: {len(df)} | menor = melhor para log-loss/NLL/ECE/Brier/MAE.")
    lines.append("")
    lines.append("| Experimento | Result LL | Result ECE | Goals NLL | Over2.5 Brier | Over2.5 ECE | MAE gols |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, m, nf in rows:
        lines.append(f"| {name} | {m['res_ll']:.4f}{delta(m,'res_ll')} | {m['res_ece']:.4f} | "
                     f"{m['goals_nll']:.4f}{delta(m,'goals_nll')} | {m['over_brier']:.4f} | "
                     f"{m['over_ece']:.4f} | {m['mae']:.3f} |")
    lines.append("")
    lines.append("## Condicional: prever jogos de torneio grande (majors)")
    lines.append("| Config (teste=majors) | Result LL | Goals NLL | MAE gols |")
    lines.append("|---|---|---|---|")
    for name, m, nf in cond:
        lines.append(f"| {name} | {m['res_ll']:.4f} | {m['goals_nll']:.4f} | {m['mae']:.3f} |")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n>> Relatório salvo em {REPORT}")


if __name__ == "__main__":
    main()
