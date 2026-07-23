#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_metrics_model_vs_naive.py
==========================================
Vitrine de desempenho (PLANO 2) — parte 1: modelo vs estrategias MAL formuladas,
com ODDS REAIS (abertura+fechamento) do backtest out-of-sample 2025.

Le `data/built/backtest_valuebet_dataset.parquet` (8117 jogos, 26 ligas, odds
reais de 1x2 e O/U 2,5 + probs do modelo). Simula banca ficticia (stake fixo 1
unidade) por liga-alvo, comparando a decisao do MODELO contra apostas ingenuas
comuns do apostador (sempre no favorito, sempre empate, sempre over, over contra
a leitura do modelo, etc.).

HONESTIDADE: o ROI e reportado como e — apostar contra o vig tende a dar
prejuizo no longo prazo mesmo pro modelo. A mensagem NAO e "lucro garantido", e
"o modelo PERDE MENOS / decide melhor que essas apostas comuns". Nenhum numero
e inventado; tudo sai das odds reais.

Uso: python scripts/adhoc_metrics_model_vs_naive.py
Saida: data/reports/performance/model_vs_naive.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
OUT_DIR = ROOT / "data" / "reports" / "performance"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Ligas-alvo com boa cobertura de odds reais no backtest 2025 (as demais
# competicoes do pedido — Libertadores/Sul-Americana/Copa do Brasil/Champions,
# Serie B — nao estao neste backtest congelado; ver hitrates/walk-forward).
TARGET_LEAGUES = ["Brasileirao Serie A", "Premier League", "La Liga", "Serie A Italia"]

STAKE = 1.0


def _pick_odds(df: pd.DataFrame):
    """Prefere odds de fechamento (melhor cobertura); cai pra abertura se faltar."""
    out = df.copy()
    for side in ["H", "D", "A", "over", "under"]:
        close = out.get(f"odd_close_{side}")
        openo = out.get(f"odd_open_{side}")
        out[f"odd_{side}"] = close.where(close.notna(), openo)
    return out


def _bet_result(won: np.ndarray, odds: np.ndarray) -> dict:
    """Metrica de uma estrategia: n, hit_rate, ROI% (lucro liquido / staked)."""
    mask = ~np.isnan(odds)
    won = won[mask]
    odds = odds[mask]
    n = len(won)
    if n == 0:
        return {"n": 0, "hit_rate": None, "roi_pct": None}
    net = np.where(won, odds - 1.0, -1.0) * STAKE
    roi = net.sum() / (n * STAKE) * 100.0
    return {"n": int(n), "hit_rate": round(float(won.mean()) * 100, 1),
            "roi_pct": round(float(roi), 2)}


def strategies_for(df: pd.DataFrame) -> dict:
    d = _pick_odds(df)
    res = d["actual_result"].values                       # 'H'/'D'/'A'
    over = d["actual_over"].values.astype(bool)           # True se total>2.5

    p = d[["p_model_H", "p_model_D", "p_model_A"]].values
    model_side = np.array(["H", "D", "A"])[p.argmax(axis=1)]

    # favorito do mercado = menor odd 1x2 (linhas sem nenhuma odd 1x2 viram NaN
    # e sao descartadas por _bet_result).
    odds_1x2 = d[["odd_H", "odd_D", "odd_A"]].values
    all_nan = np.all(np.isnan(odds_1x2), axis=1)
    safe = np.where(np.isnan(odds_1x2), np.inf, odds_1x2)
    fav_idx = safe.argmin(axis=1)
    fav_side = np.array(["H", "D", "A"])[fav_idx]

    def odd_of(side_arr):
        return np.array([d[f"odd_{s}"].values[i] for i, s in enumerate(side_arr)])

    fav_odds = odd_of(fav_side)
    fav_odds = np.where(all_nan, np.nan, fav_odds)

    # azarao do mercado = maior odd 1x2
    dog_idx = np.where(np.isnan(odds_1x2), -np.inf, odds_1x2).argmax(axis=1)
    dog_side = np.array(["H", "D", "A"])[dog_idx]
    dog_odds = np.where(all_nan, np.nan, odd_of(dog_side))

    out = {}
    # --- 1x2 (mercado principal do apostador BR) ---
    out["modelo_1x2"] = _bet_result(model_side == res, odd_of(model_side))
    out["sempre_favorito"] = _bet_result(fav_side == res, fav_odds)
    out["sempre_azarao"] = _bet_result(dog_side == res, dog_odds)
    out["sempre_mandante"] = _bet_result(res == "H", d["odd_H"].values)
    out["sempre_empate"] = _bet_result(res == "D", d["odd_D"].values)

    # --- Over/Under 2,5 ---
    model_ou_over = d["p_model_over"].values > 0.5
    won_ou = np.where(model_ou_over, over, ~over)
    odd_ou = np.where(model_ou_over, d["odd_over"].values, d["odd_under"].values)
    out["modelo_over_under"] = _bet_result(won_ou, odd_ou)
    out["sempre_over_2_5"] = _bet_result(over, d["odd_over"].values)

    return out


def main() -> None:
    df = pd.read_parquet(DATASET)
    report = {"stake": STAKE, "fonte": "backtest out-of-sample 2025 (odds reais abertura/fechamento)",
              "aviso": "ROI reflete o resultado real contra o vig; nao ha promessa de lucro. "
                       "A leitura correta e RELATIVA: o modelo perde menos/decide melhor que as "
                       "apostas ingenuas.", "ligas": {}}

    groups = [(lg, df[df["tournament"] == lg]) for lg in TARGET_LEAGUES]
    groups.append(("Geral (ligas-alvo)", df[df["tournament"].isin(TARGET_LEAGUES)]))
    groups.append(("Todas as ligas (26)", df))  # pool maximo p/ ROI estavel

    for name, sub in groups:
        if len(sub) < 30:
            continue
        report["ligas"][name] = {"n_jogos": int(len(sub)), "estrategias": strategies_for(sub)}

    out_path = OUT_DIR / "model_vs_naive.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Salvo: {out_path}\n")

    # print legivel
    for lg, data in report["ligas"].items():
        print(f"=== {lg} (n={data['n_jogos']}) ===")
        for strat, m in data["estrategias"].items():
            print(f"  {strat:20s} n={m['n']:5d}  acerto={m['hit_rate']}%  ROI={m['roi_pct']}%")
        print()


if __name__ == "__main__":
    main()
