#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/audit_calibration.py
============================
Auditoria de calibração OUT-OF-SAMPLE dos mercados servidos pelo Dixon-Coles
(resultado H/D/A, BTTS, over 2.5) — o que ainda não tinha medida sem matplotlib.
Os mercados de contagem têm scripts próprios (validate_corners_nb_calibration.py etc.).

Metodologia (igual às validações do projeto): split TEMPORAL — treina o DC na
janela <= corte e avalia no futuro. Reporta log-loss, Brier, ECE e, sobretudo, a
RELIABILITY POR FAIXA de probabilidade — o teste favorito-zebra: o modelo está
superestimando os desfechos de baixa probabilidade (zebras)? Foi o que o
value_report sugeriu (edges enormes em azaroes de odd alta = erro do modelo).

Rodar da raiz:  api/.venv/Scripts/python.exe scripts/audit_calibration.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, brier_score_loss

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dixon_coles_model import DixonColesNBRegressor  # noqa: E402

CSV = ROOT / "international_features_enriched_apifootball.csv"
META = ROOT / "api" / "model_artifacts" / "meta.json"


def ece(y_true, y_prob, n_bins=10):
    """Expected Calibration Error (binário)."""
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    val = 0.0
    for i in range(n_bins):
        m = (y_prob >= edges[i]) & (y_prob < edges[i + 1])
        if m.mean() > 0:
            val += m.mean() * abs(y_true[m].mean() - y_prob[m].mean())
    return val


def reliability_table(y_true, y_prob, n_bins=10):
    """Tabela faixa-a-faixa: n, prob média prevista, freq real, gap."""
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    rows = []
    for i in range(n_bins):
        m = (y_prob >= edges[i]) & (y_prob < edges[i + 1])
        if m.sum() == 0:
            continue
        rows.append((edges[i], edges[i + 1], int(m.sum()),
                     float(y_prob[m].mean()), float(y_true[m].mean())))
    return rows


def main():
    if not CSV.exists():
        raise SystemExit(f"Dataset nao encontrado: {CSV}")
    meta = json.loads(META.read_text(encoding="utf-8"))
    base_feats = [c for c in meta["base_feats"]]

    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    base_feats = [c for c in base_feats if c in df.columns]

    # corte temporal: 80% dos jogos com stats avancadas (mesmo das validacoes)
    df_adv = df[df["has_advanced_stats"] == 1]
    cutoff = df_adv.iloc[int(len(df_adv) * 0.8)]["date"]
    df_tr = df[df["date"] <= cutoff].reset_index(drop=True)
    # teste: todos os jogos com resultado apos o corte (maximiza N para resultado/gols)
    df_te = df[(df["date"] > cutoff) & df["result"].notna()].reset_index(drop=True)
    print(f"Corte: {cutoff.date()} | treino: {len(df_tr)} | teste: {len(df_te)} | features base: {len(base_feats)}")

    print("\n>> Treinando Dixon-Coles na janela de treino...")
    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42)
    dc.fit(df_tr[base_feats], df_tr["home_score"], df_tr["away_score"])

    probs = dc.predict_proba_markets(df_te[base_feats])
    p_res = probs["result"]          # (N,3) -> [A, D, H]
    p_btts = probs["btts"]
    p_over = probs["over_2_5"]

    y_res = df_te["result"].astype(str).values   # 'H'/'D'/'A'
    y_btts = df_te["btts"].astype(float).values
    y_over = df_te["over_2_5"].astype(float).values
    classes = ["A", "D", "H"]
    y_enc = np.array([classes.index(v) for v in y_res])

    # --- metricas agregadas
    ll_res = log_loss(y_enc, p_res, labels=[0, 1, 2])
    ece_res = np.mean([ece((y_res == c).astype(int), p_res[:, i]) for i, c in enumerate(classes)])
    print("\n================= CALIBRACAO OOS (Dixon-Coles) =================")
    print(f"Resultado H/D/A : log-loss {ll_res:.4f} | ECE(multiclasse) {100*ece_res:.2f}%")
    print(f"BTTS            : Brier {brier_score_loss(y_btts, p_btts):.4f} | ECE {100*ece(y_btts, p_btts):.2f}%")
    print(f"Over 2.5        : Brier {brier_score_loss(y_over, p_over):.4f} | ECE {100*ece(y_over, p_over):.2f}%")

    # --- teste favorito-zebra: pool das 3 classes (prob prevista x freq real)
    pooled_prob = p_res.reshape(-1)
    pooled_true = np.concatenate([(y_res == c).astype(int) for c in classes][::-1])  # alinhar [A,D,H]
    # reconstruir alinhado corretamente: para cada classe i, y_bin = (y_res==classes[i])
    pooled_prob = np.concatenate([p_res[:, i] for i in range(3)])
    pooled_true = np.concatenate([(y_res == classes[i]).astype(int) for i in range(3)])
    print("\n--- Reliability do RESULTADO por faixa de prob (pool H/D/A) ---")
    print(f"{'faixa':<12} {'n':>5} {'prev':>7} {'real':>7} {'gap':>7}")
    for lo, hi, n, pm, fr in reliability_table(pooled_true, pooled_prob, n_bins=10):
        flag = "  <-- zebra superestimada" if (pm < 0.30 and pm - fr > 0.03) else ""
        print(f"[{lo:.1f}-{hi:.1f})   {n:>5} {100*pm:>6.1f}% {100*fr:>6.1f}% {100*(pm-fr):>+6.1f}%{flag}")

    print("\nLeitura: gap>0 numa faixa baixa = modelo da probabilidade DEMAIS ao desfecho "
          "(zebra superestimada) -> fonte de '+EV' espurio em odd alta no value_report.")


if __name__ == "__main__":
    main()
