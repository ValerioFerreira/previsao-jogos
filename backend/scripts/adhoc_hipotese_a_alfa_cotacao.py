#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_hipotese_a_alfa_cotacao.py
=========================================
Hipotese A (v2, honesta) -- "alfa de cotacao": quanto vale, em ROI, escolher a
MELHOR casa de apostas real (coluna `Max` do football-data.co.uk, `book=="Max"`
em backtest_odds_normalized.parquet) vs a PIOR casa individual real disponivel
(minimo entre as casas rastreadas -- B365/BW/LB/PS/BFD/BMGM/BV/CL/PS/BFE,
excluindo os agregados "Max"/"Avg"/"market") para a mesma selecao.

Diferenca central pra v1 (DESCARTADA, ver scripts/_deprecated/): aqui as odds
sao 100% REAIS (nao fabricadas a partir da probabilidade do modelo), e a
selecao usada e o pick do MODELO DE PRODUCAO real (Predictor.predict_from_row
via o artefato congelado 2025frozen), nao um sigmoid ad-hoc.

Isto mede uma vantagem ESTRUTURAL DE MERCADO (dispersao de preco entre casas
existe quase por definicao), separada da habilidade de SELECAO do modelo
(isso e a Hipotese B, script separado). Reporta N real, IC 95% via bootstrap
(mesmo metodo de scripts/adhoc_w3_bootstrap.py) -- nenhum numero pontual sem
intervalo.

Uso: python scripts/adhoc_hipotese_a_alfa_cotacao.py
Saida: data/reports/hipotese_a_alfa_cotacao.csv + prints legiveis
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_DIR = ROOT / "data" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AGG_BOOKS = {"Max", "Avg", "market"}  # nao sao casas individuais
N_BOOT = 20000
SEED = 20260728
MIN_N_REPORT = 30  # piso pra reportar uma linha (nao esconde, so avisa se abaixo)


def bootstrap_ci(net_returns: np.ndarray, n_boot: int, rng: np.random.Generator):
    n = len(net_returns)
    idx = rng.integers(0, n, size=(n_boot, n))
    roi_boot = 100.0 * net_returns[idx].sum(axis=1) / n
    lo, hi = np.percentile(roi_boot, [2.5, 97.5])
    return float(lo), float(hi)


def best_worst_for(odds_sub: pd.DataFrame, key5, market: str, side: str):
    """odds_sub ja filtrado por market/closing=False (abertura). Retorna
    (melhor_preco_real, pior_preco_real_individual) ou (nan, nan)."""
    rows = odds_sub[(odds_sub["_key5"] == key5) & (odds_sub["side"] == side)]
    if rows.empty:
        return np.nan, np.nan
    best_row = rows[rows["book"] == "Max"]
    best = float(best_row["value"].iloc[0]) if len(best_row) else np.nan
    indiv = rows[~rows["book"].isin(AGG_BOOKS)]
    worst = float(indiv["value"].min()) if len(indiv) else np.nan
    return best, worst


def main():
    print("=" * 80)
    print(" HIPOTESE A (v2) -- ALFA DE COTACAO COM ODDS REAIS")
    print("=" * 80)

    if not PREDICTIONS.exists():
        raise SystemExit(f"{PREDICTIONS} nao existe -- rode backtest_generate_predictions.py primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)
    odds["_key5"] = list(zip(odds["source"], odds["div"], odds["date"],
                              odds["home_team_raw"], odds["away_team_raw"]))
    # Preferir fechamento (melhor cobertura -- mesmo padrao de adhoc_metrics_model_vs_naive.py
    # ::_pick_odds); cai pra abertura se faltar. Algumas fontes (ex. BRA no new_leagues_data.xlsx)
    # SO publicam a coluna "closing" (achado real desta sessao) -- filtrar so abertura zerava
    # Brasileirao inteiro.
    odds = odds.sort_values("closing").drop_duplicates(
        subset=["_key5", "market", "side", "book"], keep="last")

    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    matched_ok["_key5"] = list(zip(matched_ok["source"], matched_ok["div"], matched_ok["date"],
                                    matched_ok["home_team_raw"], matched_ok["away_team_raw"]))
    fx_to_key5 = dict(zip(matched_ok["fixture_id"], matched_ok["_key5"]))

    preds["prediction"] = preds["prediction_json"].map(json.loads)
    print(f"Previsoes do modelo congelado: {len(preds)} | odds normalizadas (abertura): {len(odds)}")

    bets = []
    for r in preds.itertuples(index=False):
        key5 = fx_to_key5.get(r.fixture_id)
        if key5 is None:
            continue
        pred = r.prediction
        home, away = r.home_team, r.away_team
        hg, ag = r.home_score, r.away_score
        actual_1x2 = "H" if hg > ag else ("A" if ag > hg else "D")
        total = hg + ag

        # --- 1x2: pick = argmax do modelo (agora inclui empate, ao contrario da v1) ---
        probs = pred.get("vencedor", {}).get("probabilidades", {})
        p_home = probs.get(home)
        p_draw = probs.get("Empate")
        p_away = probs.get(away)
        if p_home is not None and p_draw is not None and p_away is not None:
            pick = ["H", "D", "A"][int(np.argmax([p_home, p_draw, p_away]))]
            best, worst = best_worst_for(odds, key5, "1x2", pick)
            if not (np.isnan(best) or np.isnan(worst)):
                win = pick == actual_1x2
                bets.append(dict(fixture_id=r.fixture_id, tournament=r.tournament, market="1x2",
                                  pick=pick, win=win, best=best, worst=worst,
                                  ret_best=(best - 1.0) if win else -1.0,
                                  ret_worst=(worst - 1.0) if win else -1.0))

        # --- O/U 2.5 ---
        p_over = pred.get("over_2_5", {}).get("prob_sim")
        if p_over is not None:
            pick_ou = "over" if p_over >= 50.0 else "under"
            best, worst = best_worst_for(odds, key5, "ou25", pick_ou)
            if not (np.isnan(best) or np.isnan(worst)):
                win = (total > 2.5) == (pick_ou == "over")
                bets.append(dict(fixture_id=r.fixture_id, tournament=r.tournament, market="ou25",
                                  pick=pick_ou, win=win, best=best, worst=worst,
                                  ret_best=(best - 1.0) if win else -1.0,
                                  ret_worst=(worst - 1.0) if win else -1.0))

    bets_df = pd.DataFrame(bets)
    print(f"\nApostas com melhor E pior preco real disponiveis: {len(bets_df)}")
    if bets_df.empty:
        raise SystemExit("Nenhuma aposta com odds casadas -- nada a reportar.")

    rng = np.random.default_rng(SEED)
    rows_out = []

    def analyze(label: str, sub: pd.DataFrame):
        n = len(sub)
        roi_best = 100.0 * sub["ret_best"].sum() / n
        roi_worst = 100.0 * sub["ret_worst"].sum() / n
        alfa = roi_best - roi_worst
        alfa_boot = 100.0 * (sub["ret_best"].to_numpy() - sub["ret_worst"].to_numpy())
        lo, hi = bootstrap_ci(alfa_boot / 100.0, N_BOOT, rng)  # reaproveita a mesma funcao (net_returns generico)
        flag = "" if n >= MIN_N_REPORT else "  [AMOSTRA PEQUENA -- interpretar com cautela]"
        print(f"  {label:35s} N={n:4d}  ROI_melhor={roi_best:+7.2f}%  ROI_pior={roi_worst:+7.2f}%  "
              f"Alfa={alfa:+7.2f}%  IC95%=[{lo:+6.2f}%,{hi:+6.2f}%]{flag}")
        rows_out.append(dict(label=label, n=n, roi_melhor_casa=round(roi_best, 3),
                              roi_pior_casa=round(roi_worst, 3), alfa=round(alfa, 3),
                              alfa_ic95_lo=round(lo, 3), alfa_ic95_hi=round(hi, 3)))

    print("\n--- Por mercado ---")
    for market, g in bets_df.groupby("market"):
        analyze(f"mercado={market}", g)

    print("\n--- Por mercado x liga ---")
    for (market, tourn), g in bets_df.groupby(["market", "tournament"]):
        analyze(f"{market} / {tourn}", g)

    print("\n--- Pooled (tudo) ---")
    analyze("TODOS", bets_df)

    out_df = pd.DataFrame(rows_out)
    out_path = OUT_DIR / "hipotese_a_alfa_cotacao.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\nSalvo: {out_path}")
    print("\nNOTA: alfa de cotacao mede dispersao ESTRUTURAL de mercado (comparar casas), "
          "nao a habilidade de selecao do modelo -- isso e medido na Hipotese B (script separado).")


if __name__ == "__main__":
    main()
