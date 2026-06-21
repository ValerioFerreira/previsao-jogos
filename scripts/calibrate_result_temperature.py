#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/calibrate_result_temperature.py
========================================
Refino de calibração do RESULTADO (H/D/A) do Dixon-Coles por TEMPERATURE SCALING.
A auditoria (audit_calibration.py) mostrou subconfiança em favoritos (prev 74.7/84.7%
vs real 78.8/89.2% na faixa 70-90%). Temperatura T<1 "afia" as probabilidades,
empurrando as altas para cima e as baixas para baixo — exatamente o conserto.

Protocolo SEM leakage (temporal, 3 fatias):
  - treino  (<= corte): ajusta o Dixon-Coles.
  - calib   (1a metade pos-corte): ajusta T minimizando log-loss.
  - teste   (2a metade pos-corte): compara cru vs calibrado.
Gate de promocao: calibrado tem de MELHORAR log-loss E ECE no teste, sem regressao.

Rodar da raiz:  api/.venv/Scripts/python.exe scripts/calibrate_result_temperature.py
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
    """Temperature scaling sobre probabilidades (log-prob como logit). T<1 afia."""
    logp = np.log(np.clip(P, 1e-12, 1.0))
    z = logp / T
    z -= z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def ece_multiclass(y_str, P, n_bins=10):
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


def hi_prob_gap(y_str, P, lo=0.7, hi=0.9):
    """Gap medio (prev-real) na faixa de favorito, pool das 3 classes."""
    pooled_p = np.concatenate([P[:, i] for i in range(3)])
    pooled_y = np.concatenate([(y_str == CLASSES[i]).astype(float) for i in range(3)])
    m = (pooled_p >= lo) & (pooled_p < hi)
    if m.sum() == 0:
        return None, 0
    return float(pooled_p[m].mean() - pooled_y[m].mean()), int(m.sum())


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    base_feats = [c for c in meta["base_feats"] if c in df.columns]

    df_adv = df[df["has_advanced_stats"] == 1]
    cutoff = df_adv.iloc[int(len(df_adv) * 0.8)]["date"]
    df_tr = df[df["date"] <= cutoff].reset_index(drop=True)
    post = df[(df["date"] > cutoff) & df["result"].notna()].sort_values("date").reset_index(drop=True)
    half = len(post) // 2
    df_cal, df_te = post.iloc[:half].copy(), post.iloc[half:].copy()
    print(f"Corte: {cutoff.date()} | treino {len(df_tr)} | calib {len(df_cal)} | teste {len(df_te)}")

    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc.fit(df_tr[base_feats], df_tr["home_score"], df_tr["away_score"])

    P_cal = dc.predict_proba_markets(df_cal[base_feats])["result"]
    P_te = dc.predict_proba_markets(df_te[base_feats])["result"]
    y_cal = np.array([CLASSES.index(v) for v in df_cal["result"].astype(str)])
    y_te_str = df_te["result"].astype(str).values
    y_te = np.array([CLASSES.index(v) for v in y_te_str])

    # ajusta T na calib (minimiza log-loss)
    res = minimize_scalar(lambda T: log_loss(y_cal, sharpen(P_cal, T), labels=[0, 1, 2]),
                          bounds=(0.3, 3.0), method="bounded")
    T = float(res.x)
    print(f"\nT ajustado na calib: {T:.3f}  ({'afia (subconfiante)' if T < 1 else 'suaviza (superconfiante)'})")

    # avalia no teste
    P_te_cal = sharpen(P_te, T)
    ll_raw = log_loss(y_te, P_te, labels=[0, 1, 2])
    ll_cal = log_loss(y_te, P_te_cal, labels=[0, 1, 2])
    ece_raw = ece_multiclass(y_te_str, P_te)
    ece_cal = ece_multiclass(y_te_str, P_te_cal)
    gap_raw, n_hi = hi_prob_gap(y_te_str, P_te)
    gap_cal, _ = hi_prob_gap(y_te_str, P_te_cal)

    print("\n=============== TESTE OOS: cru vs calibrado (T) ===============")
    print(f"log-loss : {ll_raw:.4f} -> {ll_cal:.4f}   ({100*(ll_raw-ll_cal)/ll_raw:+.2f}%)")
    print(f"ECE      : {100*ece_raw:.2f}% -> {100*ece_cal:.2f}%")
    print(f"gap favorito [70-90%] (n={n_hi}): {100*gap_raw:+.1f}% -> {100*gap_cal:+.1f}%")

    melhora_ll = ll_cal < ll_raw
    melhora_ece = ece_cal < ece_raw
    print("\nGATE:", "PASSA (melhora log-loss E ECE)" if (melhora_ll and melhora_ece)
          else f"NAO passa (log-loss {'ok' if melhora_ll else 'pior'}, ECE {'ok' if melhora_ece else 'pior'})")
    print("\nObs: T<1 confirma subconfiança. Se passa, promover = aplicar T nas probs de "
          "resultado do predictor (re-ajustando T na base inteira com o mesmo protocolo).")


if __name__ == "__main__":
    main()
