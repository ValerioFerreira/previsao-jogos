#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/audit_rating_reliability.py
===================================
Audita a hipotese de "confiabilidade de rating": a previsao de RESULTADO degrada
para confrontos onde o rating de um lado e menos confiavel? Foi a explicacao
levantada para o +EV espurio em zebras (Curaçao 22.5% vs 5% do mercado).

Estratifica o teste (todos os jogos pos-corte com resultado, nao so os com stats)
por sinais de (in)confiabilidade e compara log-loss + a calibracao do AZARAO
(prob prevista do lado mais fraco vs frequencia real). Se o azarao de baixa
confiabilidade ganha MENOS do que o modelo preve, ha overconfidence a corrigir.

Sinais testados:
  - min_matches: min(jogos previos dos 2 lados) — quantidade de dados.
  - elo_min: Elo do lado mais fraco (minnow tem Elo baixo).
  - elo_gap: |elo_diff| — confrontos desiguais (onde a zebra aparece).

Rodar da raiz:  api/.venv/Scripts/python.exe scripts/audit_rating_reliability.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dixon_coles_model import DixonColesNBRegressor  # noqa: E402

CSV = ROOT / "international_features_enriched_apifootball.csv"
META = ROOT / "api" / "model_artifacts" / "meta.json"
CLASSES = ["A", "D", "H"]


def underdog_calib(df_te, P, mask):
    """Para os jogos do bucket: prob prevista do lado mais fraco (por Elo) vencer
    vs frequencia real. Gap>0 => azarao superestimado."""
    sub = df_te[mask]
    Ps = P[mask.values]
    if len(sub) == 0:
        return None
    # lado mais fraco por elo: se home_elo<away_elo, azarao = home (classe H, idx 2)
    home_weaker = (sub["home_elo_pre"] < sub["away_elo_pre"]).values
    p_under = np.where(home_weaker, Ps[:, 2], Ps[:, 0])  # H se home fraco, senao A
    won = np.where(home_weaker, (sub["result"] == "H"), (sub["result"] == "A")).astype(float)
    return float(p_under.mean()), float(won.mean()), len(sub)


def bucket_report(name, df_te, P, y_enc, signal, edges):
    print(f"\n--- estratificado por {name} ---")
    print(f"{'faixa':<16} {'n':>5} {'logloss':>8} {'azarao_prev':>11} {'azarao_real':>11} {'gap':>7}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (signal >= lo) & (signal < hi)
        n = int(mask.sum())
        if n < 20:
            continue
        ll = log_loss(y_enc[mask.values], P[mask.values], labels=[0, 1, 2])
        uc = underdog_calib(df_te, P, mask)
        lbl = f"[{lo:g},{hi:g})"
        if uc:
            pu, wu, _ = uc
            print(f"{lbl:<16} {n:>5} {ll:>8.4f} {100*pu:>10.1f}% {100*wu:>10.1f}% {100*(pu-wu):>+6.1f}%")
        else:
            print(f"{lbl:<16} {n:>5} {ll:>8.4f}")


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    base_feats = [c for c in meta["base_feats"] if c in df.columns]
    df_adv = df[df["has_advanced_stats"] == 1]
    cutoff = df_adv.iloc[int(len(df_adv) * 0.8)]["date"]
    df_tr = df[df["date"] <= cutoff].reset_index(drop=True)
    df_te = df[(df["date"] > cutoff) & df["result"].notna()].reset_index(drop=True)
    print(f"Corte: {cutoff.date()} | treino {len(df_tr)} | teste {len(df_te)}")

    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc.fit(df_tr[base_feats], df_tr["home_score"], df_tr["away_score"])
    P = dc.predict_proba_markets(df_te[base_feats])["result"]  # [A,D,H]
    y_enc = np.array([CLASSES.index(v) for v in df_te["result"].astype(str)])
    print(f"log-loss global teste: {log_loss(y_enc, P, labels=[0,1,2]):.4f}")

    min_matches = df_te[["home_matches_played_before", "away_matches_played_before"]].min(axis=1)
    elo_min = df_te[["home_elo_pre", "away_elo_pre"]].min(axis=1)
    elo_gap = (df_te["home_elo_pre"] - df_te["away_elo_pre"]).abs()

    bucket_report("min jogos previos", df_te, P, y_enc, min_matches, [0, 50, 100, 200, 400, 1200])
    bucket_report("Elo do lado mais fraco", df_te, P, y_enc, elo_min, [0, 1300, 1450, 1550, 1650, 2200])
    bucket_report("|elo_diff| (desigualdade)", df_te, P, y_enc, elo_gap, [0, 100, 200, 350, 500, 1500])

    print("\nLeitura: se o 'gap' do azarao for consistentemente POSITIVO num bucket de "
          "baixa confiabilidade (poucos jogos / Elo baixo), ha overconfidence a encolher.")


if __name__ == "__main__":
    main()
