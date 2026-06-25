#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/calibrate_mismatch.py
=============================
Corrige o vies favorito-zebra do RESULTADO afiando as probabilidades SO em jogos
desiguais (|elo_diff| > G), onde a auditoria (audit_rating_reliability.py) mostrou
o azarao superestimado em +1 a +2.4%. Jogos equilibrados ficam intactos — o que
evita a regressao que a temperatura GLOBAL causou (ECE 1.83%->2.33%).

Protocolo temporal sem leakage: treino DC (<=corte); calib (1a metade pos-corte);
teste (2a metade). T ajustado nos jogos-mismatch da calib (minimiza log-loss).
Gate: melhora log-loss E ECE no subconjunto mismatch do teste, sem regredir o teste
global. Varre alguns G para robustez.

Rodar da raiz:  api/.venv/Scripts/python.exe scripts/calibrate_mismatch.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
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


def sharpen(P, T):
    logp = np.log(np.clip(P, 1e-12, 1.0))
    z = logp / T
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def ece_mc(y_str, P, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    vals = []
    for i, c in enumerate(CLASSES):
        yb = (y_str == c).astype(float)
        pb = P[:, i]
        e = 0.0
        for b in range(n_bins):
            m = (pb >= edges[b]) & (pb < edges[b + 1])
            if m.mean() > 0:
                e += m.mean() * abs(yb[m].mean() - pb[m].mean())
        vals.append(e)
    return float(np.mean(vals))


def underdog_gap(df, P):
    home_weaker = (df["home_elo_pre"] < df["away_elo_pre"]).values
    p_u = np.where(home_weaker, P[:, 2], P[:, 0])
    won = np.where(home_weaker, (df["result"] == "H"), (df["result"] == "A")).astype(float)
    return 100 * (p_u.mean() - won.mean())


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    bf = [c for c in meta["base_feats"] if c in df.columns]
    df_adv = df[df["has_advanced_stats"] == 1]
    cutoff = df_adv.iloc[int(len(df_adv) * 0.8)]["date"]
    df_tr = df[df["date"] <= cutoff].reset_index(drop=True)
    post = df[(df["date"] > cutoff) & df["result"].notna()].sort_values("date").reset_index(drop=True)
    h = len(post) // 2
    cal, te = post.iloc[:h].reset_index(drop=True), post.iloc[h:].reset_index(drop=True)

    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc.fit(df_tr[bf], df_tr["home_score"], df_tr["away_score"])
    P_cal = dc.predict_proba_markets(cal[bf])["result"]
    P_te = dc.predict_proba_markets(te[bf])["result"]
    y_cal = np.array([CLASSES.index(v) for v in cal["result"].astype(str)])
    y_te_str = te["result"].astype(str).values
    y_te = np.array([CLASSES.index(v) for v in y_te_str])
    gap_cal = (cal["home_elo_pre"] - cal["away_elo_pre"]).abs().values
    gap_te = (te["home_elo_pre"] - te["away_elo_pre"]).abs().values

    print(f"Corte {cutoff.date()} | calib {len(cal)} | teste {len(te)}")
    print(f"GLOBAL cru: log-loss {log_loss(y_te, P_te, labels=[0,1,2]):.4f} | "
          f"ECE {100*ece_mc(y_te_str, P_te):.2f}% | gap azarao {underdog_gap(te, P_te):+.1f}%")

    for G in (100, 150, 200, 250):
        mcal, mte = gap_cal > G, gap_te > G
        if mcal.sum() < 30 or mte.sum() < 30:
            continue
        T = float(minimize_scalar(
            lambda t: log_loss(y_cal[mcal], sharpen(P_cal[mcal], t), labels=[0, 1, 2]),
            bounds=(0.3, 3.0), method="bounded").x)
        # aplica so nos mismatch do teste
        P_adj = P_te.copy()
        P_adj[mte] = sharpen(P_te[mte], T)

        # subconjunto mismatch
        ll_r = log_loss(y_te[mte], P_te[mte], labels=[0, 1, 2])
        ll_c = log_loss(y_te[mte], P_adj[mte], labels=[0, 1, 2])
        ec_r = ece_mc(y_te_str[mte], P_te[mte])
        ec_c = ece_mc(y_te_str[mte], P_adj[mte])
        g_r = underdog_gap(te[mte], P_te[mte])
        g_c = underdog_gap(te[mte], P_adj[mte])
        # global
        llg_r = log_loss(y_te, P_te, labels=[0, 1, 2])
        llg_c = log_loss(y_te, P_adj, labels=[0, 1, 2])
        ecg_c = ece_mc(y_te_str, P_adj)
        gate = (ll_c < ll_r) and (ec_c < ec_r) and (llg_c <= llg_r)
        print(f"\nG={G} (T={T:.3f}, n_mismatch_te={int(mte.sum())}):")
        print(f"  mismatch  log-loss {ll_r:.4f}->{ll_c:.4f} | ECE {100*ec_r:.2f}%->{100*ec_c:.2f}% | "
              f"gap azarao {g_r:+.1f}%->{g_c:+.1f}%")
        print(f"  global    log-loss {llg_r:.4f}->{llg_c:.4f} | ECE ->{100*ecg_c:.2f}%")
        print(f"  GATE: {'PASSA' if gate else 'NAO passa'}")


if __name__ == "__main__":
    main()
