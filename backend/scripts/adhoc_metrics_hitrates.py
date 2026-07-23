#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_metrics_hitrates.py
====================================
Vitrine de desempenho (PLANO 2) — parte 2: taxas de acerto por liga vs o
BENCHMARK DE MERCADO (probabilidade implicita de-vigada das odds de fechamento
= a previsao do proprio mercado, padrao-ouro) e vs benchmark de literatura.

Fontes:
  - `data/built/backtest_valuebet_dataset.parquet` — p_model_* e p_fair_close_*
    (mercado de fechamento de-vigado) + resultado real, no MESMO conjunto de
    jogos → head-to-head modelo vs mercado (acuracia, log-loss, Brier, ECE).
  - `data/built/backtest_predictions.parquet` — prediction_json completo →
    placar exato (top-1), Ambas Marcam (BTTS).

HONESTIDADE: o mercado de fechamento e eficiente; se ele ganhar em log-loss, a
narrativa e "empatamos com o mercado em precisao e ainda somos transparentes",
nunca "batemos o mercado". Todos os numeros saem dos dados reais.

Uso: python scripts/adhoc_metrics_hitrates.py
Saida: data/reports/performance/hitrates.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_clubs.protocol import (  # noqa: E402
    multiclass_logloss, brier_multiclass, ece_multiclass,
)

VALUEBET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
OUT_DIR = ROOT / "data" / "reports" / "performance"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_LEAGUES = ["Brasileirao Serie A", "Premier League", "La Liga", "Serie A Italia"]

# Benchmark de literatura (o que se espera de um bom modelo nestes mercados).
LIT = {
    "acc_1x2": "~50-55% (mercado/modelos academicos)",
    "placar_exato": "~10-13%",
    "ece": "<2% = bem calibrado",
}
RESULT_IDX = {"H": 0, "D": 1, "A": 2}


def _metrics_1x2(sub: pd.DataFrame, pcols) -> dict:
    y = sub["actual_result"].map(RESULT_IDX).values
    P = sub[pcols].values.astype(float)
    P = P / P.sum(axis=1, keepdims=True)
    pred = P.argmax(axis=1)
    return {
        "n": int(len(y)),
        "acuracia": round(float((pred == y).mean()) * 100, 1),
        "log_loss": round(multiclass_logloss(y, P), 4),
        "brier": round(brier_multiclass(y, P), 4),
        "ece": round(ece_multiclass(y, P) * 100, 2),
    }


def _draws(sub: pd.DataFrame) -> dict:
    y = sub["actual_result"].values
    P = sub[["p_model_H", "p_model_D", "p_model_A"]].values.astype(float)
    pred = np.array(["H", "D", "A"])[P.argmax(axis=1)]
    n_real = int((y == "D").sum())
    n_pred = int((pred == "D").sum())
    # acerto entre os que o modelo cravou empate
    hit = int(((pred == "D") & (y == "D")).sum())
    return {
        "empates_reais": n_real,
        "empates_previstos_pelo_modelo": n_pred,
        "acertos_quando_previu_empate": hit,
        "prob_media_empate_modelo": round(float(P[:, 1].mean()) * 100, 1),
        "freq_real_empate": round(n_real / len(y) * 100, 1),
    }


def _exact_and_btts(pred_df: pd.DataFrame) -> dict:
    exact_hit = 0
    exact_n = 0
    btts_hit = 0
    btts_n = 0
    for _, row in pred_df.iterrows():
        try:
            j = json.loads(row["prediction_json"])
        except (TypeError, ValueError):
            continue
        hs, as_ = row["home_score"], row["away_score"]
        if pd.isna(hs) or pd.isna(as_):
            continue
        top = j.get("placar_exato", {}).get("top", [])
        if top:
            exact_n += 1
            t0 = top[0]
            if int(t0["mandante"]) == int(hs) and int(t0["visitante"]) == int(as_):
                exact_hit += 1
        bt = j.get("ambas_marcam", {})
        if "prob_sim" in bt:
            btts_n += 1
            pred_sim = bt["prob_sim"] >= 50
            real_sim = (hs > 0) and (as_ > 0)
            if pred_sim == real_sim:
                btts_hit += 1
    return {
        "placar_exato_top1_acerto_pct": round(exact_hit / exact_n * 100, 1) if exact_n else None,
        "placar_exato_n": exact_n,
        "btts_acerto_pct": round(btts_hit / btts_n * 100, 1) if btts_n else None,
        "btts_n": btts_n,
    }


def main() -> None:
    vb = pd.read_parquet(VALUEBET)
    pred = pd.read_parquet(PREDICTIONS)

    report = {
        "fonte": "backtest out-of-sample 2025 (modelo congelado) + odds reais de fechamento",
        "benchmark_literatura": LIT,
        "nota_benchmark_mercado": "p_fair_close = probabilidade implicita de-vigada das odds de "
        "fechamento (a previsao do proprio mercado). Mercado eficiente e dificil de bater em "
        "log-loss; o objetivo honesto e EMPATAR com ele em precisao sendo transparente.",
        "ligas": {},
    }

    groups = [(lg, lg) for lg in TARGET_LEAGUES]
    groups.append(("Geral (ligas-alvo)", None))

    for name, lg in groups:
        vsub = vb[vb["tournament"] == lg] if lg else vb[vb["tournament"].isin(TARGET_LEAGUES)]
        psub = pred[pred["tournament"] == lg] if lg else pred[pred["tournament"].isin(TARGET_LEAGUES)]
        if len(vsub) < 30:
            continue

        # head-to-head modelo vs mercado (so linhas com odds de fechamento completas)
        mkt_ok = vsub[["p_fair_close_H", "p_fair_close_D", "p_fair_close_A"]].notna().all(axis=1)
        vsub_mkt = vsub[mkt_ok]

        entry = {
            "n_jogos": int(len(vsub)),
            "modelo_1x2": _metrics_1x2(vsub, ["p_model_H", "p_model_D", "p_model_A"]),
            "mercado_1x2": _metrics_1x2(vsub_mkt, ["p_fair_close_H", "p_fair_close_D", "p_fair_close_A"]) if len(vsub_mkt) >= 30 else None,
            "modelo_1x2_no_conjunto_do_mercado": _metrics_1x2(vsub_mkt, ["p_model_H", "p_model_D", "p_model_A"]) if len(vsub_mkt) >= 30 else None,
            "empates": _draws(vsub),
            "placar_e_btts": _exact_and_btts(psub),
        }
        report["ligas"][name] = entry

    out_path = OUT_DIR / "hitrates.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Salvo: {out_path}\n")

    for lg, e in report["ligas"].items():
        m = e["modelo_1x2"]
        mk = e.get("mercado_1x2")
        print(f"=== {lg} (n={e['n_jogos']}) ===")
        print(f"  modelo 1x2:  acc={m['acuracia']}%  logloss={m['log_loss']}  brier={m['brier']}  ECE={m['ece']}%")
        if mk:
            mm = e["modelo_1x2_no_conjunto_do_mercado"]
            print(f"  mercado 1x2: acc={mk['acuracia']}%  logloss={mk['log_loss']}  brier={mk['brier']}  ECE={mk['ece']}%  (modelo no mesmo conj.: acc={mm['acuracia']}% logloss={mm['log_loss']})")
        d = e["empates"]
        print(f"  empates: reais={d['empates_reais']}  previstos={d['empates_previstos_pelo_modelo']}  P(empate) media={d['prob_media_empate_modelo']}% vs freq real {d['freq_real_empate']}%")
        pb = e["placar_e_btts"]
        print(f"  placar exato top-1: {pb['placar_exato_top1_acerto_pct']}%  |  BTTS: {pb['btts_acerto_pct']}%")
        print()


if __name__ == "__main__":
    main()
