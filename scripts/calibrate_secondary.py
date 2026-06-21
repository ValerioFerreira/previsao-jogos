#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/calibrate_secondary.py
==============================
Refino de calibração dos mercados com MAIS folga na auditoria: Over 2.5 (ECE 3.71%)
e Escanteios-visitante (ECE 6.31%). Mesmo protocolo temporal sem leakage (treino <=
corte; calib = 1a metade pos-corte; teste = 2a metade) e o mesmo gate: o calibrado
tem de melhorar a metrica-alvo no teste sem regressao.

- Over 2.5 (DC): temperature scaling BINARIO (1 parametro).
- Escanteios-visitante (CornersNB): calibracao ISOTONICA da probabilidade de over,
  agrupada nas linhas servidas (5.5..10.5) — corrige vies monotonico do CDF (a
  temperatura so mexe na dispersao; isotonica tambem corrige vies de media).

Rodar da raiz:  api/.venv/Scripts/python.exe scripts/calibrate_secondary.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dixon_coles_model import DixonColesNBRegressor  # noqa: E402
from corners_nb_model import CornersNB  # noqa: E402
import compare_corners as cc  # noqa: E402

CSV = ROOT / "international_features_enriched_apifootball.csv"
META = ROOT / "api" / "model_artifacts" / "meta.json"
AWAY_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5]


def ece_binary(y, p, n_bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, n_bins + 1)
    e = 0.0
    for i in range(n_bins):
        m = (p >= edges[i]) & (p < edges[i + 1])
        if m.mean() > 0:
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return e


def sharpen_binary(p, T):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    a, b = p ** (1 / T), (1 - p) ** (1 / T)
    return a / (a + b)


def over_pairs(pmf, actual, lines):
    """Agrupa (prob_over, desfecho_over) de varias linhas. pmf (N,M+1)."""
    ps, ys = [], []
    for L in lines:
        ps.append(pmf[:, int(L) + 1:].sum(axis=1))
        ys.append((actual > L).astype(float))
    return np.concatenate(ps), np.concatenate(ys)


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    # ===================== OVER 2.5 (Dixon-Coles) =====================
    base_feats = [c for c in meta["base_feats"] if c in df.columns]
    df_adv = df[df["has_advanced_stats"] == 1]
    cutoff = df_adv.iloc[int(len(df_adv) * 0.8)]["date"]
    df_tr = df[df["date"] <= cutoff].reset_index(drop=True)
    post = df[(df["date"] > cutoff) & df["over_2_5"].notna()].sort_values("date").reset_index(drop=True)
    h = len(post) // 2
    cal, te = post.iloc[:h], post.iloc[h:]

    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc.fit(df_tr[base_feats], df_tr["home_score"], df_tr["away_score"])
    p_cal = dc.predict_proba_markets(cal[base_feats])["over_2_5"]
    p_te = dc.predict_proba_markets(te[base_feats])["over_2_5"]
    y_cal = cal["over_2_5"].astype(float).values
    y_te = te["over_2_5"].astype(float).values

    T = float(minimize_scalar(lambda t: log_loss(y_cal, sharpen_binary(p_cal, t), labels=[0, 1]),
                              bounds=(0.3, 3.0), method="bounded").x)
    p_te_c = sharpen_binary(p_te, T)
    ll_r, ll_c = log_loss(y_te, p_te, labels=[0, 1]), log_loss(y_te, p_te_c, labels=[0, 1])
    ec_r, ec_c = ece_binary(y_te, p_te), ece_binary(y_te, p_te_c)
    print("================= OVER 2.5 (temperature binario) =================")
    print(f"corte {cutoff.date()} | calib {len(cal)} | teste {len(te)} | T={T:.3f}")
    print(f"log-loss: {ll_r:.4f} -> {ll_c:.4f} | ECE: {100*ec_r:.2f}% -> {100*ec_c:.2f}%")
    print("GATE:", "PASSA" if (ll_c < ll_r and ec_c < ec_r) else
          f"NAO passa (LL {'ok' if ll_c<ll_r else 'pior'}, ECE {'ok' if ec_c<ec_r else 'pior'})")

    # ============== ESCANTEIOS-VISITANTE (CornersNB + isotonica) ==============
    feats = [c for c in cc.numeric_features(df) if c not in cc.LEAK_OR_ID]
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_corners", "away_cur_sb_corners"]).copy()
    adv = adv.sort_values("date").reset_index(drop=True)
    cut2 = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr2 = adv[adv["date"] <= cut2].reset_index(drop=True)
    post2 = adv[adv["date"] > cut2].reset_index(drop=True)
    h2 = len(post2) // 2
    cal2, te2 = post2.iloc[:h2].reset_index(drop=True), post2.iloc[h2:].reset_index(drop=True)

    model = CornersNB(max_corners=cc.M_C, feats=feats).fit(
        tr2[feats], tr2["home_cur_sb_corners"].astype(int).values, tr2["away_cur_sb_corners"].astype(int).values)
    pa_cal = model.predict_distributions(cal2[feats])["away"]
    pa_te = model.predict_distributions(te2[feats])["away"]
    ya_cal = cal2["away_cur_sb_corners"].astype(int).values
    ya_te = te2["away_cur_sb_corners"].astype(int).values

    # isotonica na prob-over agrupada nas linhas servidas
    pc, yc = over_pairs(pa_cal, ya_cal, AWAY_LINES)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(pc, yc)
    pt, yt = over_pairs(pa_te, ya_te, AWAY_LINES)
    pt_c = iso.predict(pt)
    ll_r2, ll_c2 = log_loss(yt, np.clip(pt, 1e-12, 1 - 1e-12), labels=[0, 1]), log_loss(yt, np.clip(pt_c, 1e-12, 1 - 1e-12), labels=[0, 1])
    ec_r2, ec_c2 = ece_binary(yt, pt), ece_binary(yt, pt_c)
    print("\n========= ESCANTEIOS-VISITANTE (isotonica, linhas 5.5-10.5) =========")
    print(f"corte {cut2.date()} | calib {len(cal2)} | teste {len(te2)} | pares O/U teste {len(yt)}")
    print(f"log-loss(O/U): {ll_r2:.4f} -> {ll_c2:.4f} | ECE(O/U pool): {100*ec_r2:.2f}% -> {100*ec_c2:.2f}%")
    print("GATE:", "PASSA" if (ll_c2 < ll_r2 and ec_c2 < ec_r2) else
          f"NAO passa (LL {'ok' if ll_c2<ll_r2 else 'pior'}, ECE {'ok' if ec_c2<ec_r2 else 'pior'})")


if __name__ == "__main__":
    main()
