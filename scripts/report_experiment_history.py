#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/report_experiment_history.py
====================================
Gera analise_historico_vs_2016.md comparando:
  A = historia completa (1872+, = producao)
  B = so 2016+ (cold start, design de producao transplantado)
  C = so 2016+ construido de proposito (Elo provisional)

C isola "penalidade de design" (corrigivel) de "penalidade de dados" (irredutivel).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DIR = Path("scratch/experimento_historico")
A_CSV = "international_features_enriched_apifootball.csv"
B_CSV = DIR / "dataset_2016.csv"

METRICS = [
    ("result_logloss", "Resultado · log-loss", True),
    ("result_acc",     "Resultado · acuracia", False),
    ("result_ece",     "Resultado · ECE", True),
    ("result_brier",   "Resultado · Brier", True),
    ("gols_logloss",   "Gols · log-loss", True),
    ("gols_mae",       "Gols · MAE", True),
    ("gols_rmse",      "Gols · RMSE", True),
    ("btts_logloss",   "BTTS · log-loss", True),
    ("over25_logloss", "Over2.5 · log-loss", True),
    ("corners_home_logloss",  "Esc. mandante · log-loss", True),
    ("corners_away_logloss",  "Esc. visitante · log-loss", True),
    ("corners_total_logloss", "Esc. total · log-loss", True),
    ("corners_total_ece",     "Esc. total · ECE", True),
]


def f(v, key):
    if v is None:
        return "–"
    return f"{v*100:.2f}%" if ("ece" in key or "acc" in key) else f"{v:.5f}"


def main():
    A = json.loads((DIR / "metrics_full.json").read_text())
    B = json.loads((DIR / "metrics_b2016.json").read_text())
    Cp = DIR / "metrics_c2016.json"
    C = json.loads(Cp.read_text()) if Cp.exists() else None

    L = ["# Experimento — valor da historia (A) vs so 2016+ (B, C)", "",
         "> **A** = warmup com toda a martj42 (1872+) = producao.",
         "> **B** = so 2016+, design de producao transplantado (Elo frio).",
         "> **C** = so 2016+ construido de proposito (Elo provisional, K alto nos primeiros 25 jogos).",
         "> Mesmas 9.976 partidas, mesmos alvos, mesmo test-fold. Modelos re-treinados do zero em cada braco.", ""]
    L.append(f"- Test resultado/gols: corte {A.get('cutoff')} · {A.get('n_test')} jogos | "
             f"escanteios: {A.get('n_test_corners')} jogos")
    rH = lambda d: f"{d.get('r_H'):.1f}/{d.get('r_A'):.1f}" if d else "–"
    L.append(f"- r escanteios — A {rH(A)} · B {rH(B)} · C {rH(C)}")
    L.append("")
    head = "| Metrica | A (completa) | B (frio) | C (proposito) | melhor |"
    L.append(head); L.append("|---|---|---|---|---|")
    for k, lab, lower in METRICS:
        vals = {"A": A.get(k), "B": B.get(k), "C": (C.get(k) if C else None)}
        present = {kk: vv for kk, vv in vals.items() if vv is not None}
        best = (min if lower else max)(present, key=present.get)
        L.append(f"| {lab} | {f(vals['A'],k)} | {f(vals['B'],k)} | {f(vals['C'],k)} | {best} |")

    # gap recuperado por C (em result_logloss e gols_logloss)
    L.append("")
    L.append("## Quanto o design de proposito (C) recuperou do gap")
    L.append("")
    if C:
        for k, lab in [("result_logloss", "Resultado log-loss"), ("gols_logloss", "Gols log-loss"),
                       ("corners_total_logloss", "Esc. total log-loss")]:
            gap_B = B[k] - A[k]
            gap_C = C[k] - A[k]
            rec = (1 - gap_C / gap_B) * 100 if gap_B else 0
            L.append(f"- **{lab}:** gap B={gap_B:+.5f}, gap C={gap_C:+.5f} → C recuperou **{rec:.0f}%** do gap")

    # convergencia Elo
    L.append("")
    L.append("## Convergencia do Elo por ano (A vs B)")
    L.append("")
    a = pd.read_csv(A_CSV, usecols=["match_id", "date", "home_elo_pre", "elo_diff"], low_memory=False)
    b = pd.read_csv(B_CSV, usecols=["match_id", "home_elo_pre", "elo_diff"], low_memory=False)
    a["year"] = pd.to_datetime(a["date"]).dt.year
    m = a.merge(b, on="match_id", suffixes=("_A", "_B"))
    m["d"] = (m["home_elo_pre_A"] - m["home_elo_pre_B"]).abs()
    g = m.groupby("year").agg(n=("match_id", "size"), d=("d", "mean"),
                              corr=("elo_diff_A", lambda s: np.corrcoef(s, m.loc[s.index, "elo_diff_B"])[0, 1]))
    L.append("| Ano | Jogos | Δ|Elo| A-B | corr(elo_diff) |")
    L.append("|---|---|---|---|")
    for yr, r in g.iterrows():
        L.append(f"| {yr} | {int(r['n'])} | {r['d']:.1f} | {r['corr']:.3f} |")

    (DIR / "analise_historico_vs_2016.md").write_text("\n".join(L), encoding="utf-8")
    print("Relatorio:", DIR / "analise_historico_vs_2016.md")
    print("\n".join(L[L.index(head) - 1:]))


if __name__ == "__main__":
    main()
