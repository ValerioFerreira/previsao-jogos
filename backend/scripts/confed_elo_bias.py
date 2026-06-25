#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/confed_elo_bias.py  (#1 — diagnostico empirico da inflacao)
==================================================================
Phi (isolamento) sozinho nao distingue ilha FORTE (UEFA) de ilha FRACA inflada
(CONCACAF/Curacao). O sinal real da inflacao e o DEFICIT DE DESEMPENHO: quanto os
times de uma confederacao rendem ABAIXO do que o Elo preve quando enfrentam os
benchmarks fortes (UEFA/CONMEBOL).

Para cada confederacao C, nos jogos inter-confederacao vs {UEFA, CONMEBOL}:
  residuo = pontos_reais(0/0.5/1) - E_elo   (E_elo = score esperado do Elo, com mando)
  media < 0  => Elo de C INFLADO (rende menos do que promete) -> alvo do shrinkage.

Local, 0 requests. So mede; nao altera nada.
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

cm = json.load(open(ROOT / "api/model_artifacts/confed_map.json", encoding="utf-8"))
CONF = {k: v for k, v in cm.items() if not k.startswith("_")}
STRONG = {"UEFA", "CONMEBOL"}


def main():
    df = pd.read_csv(ROOT / "international_features_enriched_apifootball.csv", parse_dates=["date"])
    df = df.dropna(subset=["elo_home_winprob", "result"]).copy()
    df["hc"] = df["home_team"].map(CONF)
    df["ac"] = df["away_team"].map(CONF)
    df = df.dropna(subset=["hc", "ac"])
    df["home_pts"] = df["result"].map({"H": 1.0, "D": 0.5, "A": 0.0})

    for span, sub in [("TODO 2016+", df), ("ULT 3 ANOS", df[df.date >= df.date.max() - pd.Timedelta(days=3*365)])]:
        inter = sub[sub.hc != sub.ac]
        print(f"\n=== {span} | jogos inter-confed: {len(inter)} ===")
        print(f"  {'Conf':9s} {'jogos vs FORTE':>14s} {'E_elo medio':>11s} {'real medio':>10s} {'residuo (real-Elo)':>18s}")
        rows = []
        for C in ["CONCACAF", "CAF", "AFC", "OFC", "UEFA", "CONMEBOL"]:
            # jogos de C contra UEFA/CONMEBOL
            as_home = inter[(inter.hc == C) & (inter.ac.isin(STRONG))]
            as_away = inter[(inter.ac == C) & (inter.hc.isin(STRONG))]
            e = list(as_home["elo_home_winprob"]) + list(1 - as_away["elo_home_winprob"])
            real = list(as_home["home_pts"]) + list(1 - as_away["home_pts"])
            if not e:
                print(f"  {C:9s} {'0':>14s}"); continue
            e, real = np.array(e), np.array(real)
            rows.append((C, len(e), e.mean(), real.mean(), real.mean() - e.mean()))
            print(f"  {C:9s} {len(e):>14d} {e.mean():>11.3f} {real.mean():>10.3f} {real.mean()-e.mean():>+18.3f}")
        # leitura
        if span == "TODO 2016+":
            neg = [(C, b) for C, _, _, _, b in rows if C not in STRONG and b < 0]
            print("\n  -> Confederacoes com Elo INFLADO vs FORTE (residuo<0):",
                  ", ".join(f"{C} {b:+.3f}" for C, b in sorted(neg, key=lambda x: x[1])) or "nenhuma")


if __name__ == "__main__":
    main()
