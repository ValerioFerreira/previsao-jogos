#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_score.py
==========================================
Fase 2 da pesquisa de escanteios 1T/2T: junta as previsoes dos candidatos
(A/B/C, formato longo padronizado fixture_id,market,lambda,pmf) com o
gabarito real (data/external/corners_halftime_ground_truth.parquet, via
StatsBomb open data) e calcula metricas comparaveis -- PMF log-loss, MAE,
vies -- por candidato e por market (home_1t/away_1t/home_2t/away_2t).

Roda so com os candidatos cujo CSV de previsao ja existe (nao trava esperando
os que ainda estao rodando).

Uso: python scripts/adhoc_corners_halftime_score.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "data" / "reports" / "corners_halftime"
GT_PATH = ROOT / "data" / "external" / "corners_halftime_ground_truth.parquet"

MARKET_TO_GT_COL = {
    "home_1t": "home_corners_1t",
    "away_1t": "away_corners_1t",
    "home_2t": "home_corners_2t",
    "away_2t": "away_corners_2t",
}

CANDIDATES = {
    "baseline_50_50": None,   # gerado sinteticamente abaixo, nao tem CSV
    "baseline_lit_55": None,  # idem
    "candidate_a": REPORTS_DIR / "candidate_a_predictions.csv",
    "candidate_b": REPORTS_DIR / "candidate_b_predictions.csv",
    "candidate_c": REPORTS_DIR / "candidate_c_predictions.csv",
}


def load_gt() -> pd.DataFrame:
    gt = pd.read_parquet(GT_PATH)
    return gt.set_index("fixture_id")


def load_predictions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["pmf"] = df["pmf"].apply(lambda s: np.array([float(x) for x in s.split(",")]))
    return df


def build_baseline(any_candidate_df: pd.DataFrame, frac_2t: float, r: float = 8.0) -> pd.DataFrame:
    """Baseline: pega o total (home_1t+home_2t) de qualquer candidato (todos
    preservam o mesmo total de producao por construcao) e aplica uma fracao
    2T FIXA (nao varia por jogo) -- e o que todo candidato tem que bater."""
    from scipy.stats import nbinom

    totals = (
        any_candidate_df[any_candidate_df["market"].isin(["home_1t", "home_2t"])]
        .groupby("fixture_id")["lambda"].sum().rename("home_total")
    )
    totals_away = (
        any_candidate_df[any_candidate_df["market"].isin(["away_1t", "away_2t"])]
        .groupby("fixture_id")["lambda"].sum().rename("away_total")
    )
    base = pd.concat([totals, totals_away], axis=1).reset_index()

    rows = []
    grid = np.arange(16)
    for _, row in base.iterrows():
        for side, total in (("home", row["home_total"]), ("away", row["away_total"])):
            for half, frac in (("1t", 1 - frac_2t), ("2t", frac_2t)):
                lam = max(total * frac, 0.05)
                p = r / (r + lam)
                pmf = nbinom.pmf(grid, n=r, p=p)
                pmf = pmf / pmf.sum()
                rows.append({"fixture_id": row["fixture_id"], "market": f"{side}_{half}", "lambda": lam, "pmf": pmf})
    return pd.DataFrame(rows)


def score_candidate(name: str, pred_df: pd.DataFrame, gt: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for market, gt_col in MARKET_TO_GT_COL.items():
        sub = pred_df[pred_df["market"] == market].set_index("fixture_id")
        joined = sub.join(gt[[gt_col]], how="inner")
        joined = joined.dropna(subset=[gt_col])
        if len(joined) == 0:
            continue
        actual = joined[gt_col].astype(int).clip(upper=15).values
        lambdas = joined["lambda"].values
        pmfs = np.stack(joined["pmf"].values)

        # PMF log-loss
        p_actual = pmfs[np.arange(len(actual)), actual]
        p_actual = np.clip(p_actual, 1e-9, 1.0)
        logloss = -np.mean(np.log(p_actual))

        mae = np.mean(np.abs(lambdas - actual))
        bias = np.mean(lambdas - actual)

        rows.append({
            "candidate": name, "market": market, "n": len(joined),
            "pmf_logloss": logloss, "mae": mae, "bias": bias,
            "mean_lambda": lambdas.mean(), "mean_actual": actual.mean(),
        })
    return pd.DataFrame(rows)


def main() -> None:
    gt = load_gt()
    print(f"Gabarito: {len(gt)} partidas (StatsBomb)")

    available = {}
    for name, path in CANDIDATES.items():
        if path is not None and path.exists():
            available[name] = load_predictions(path)
            print(f"  {name}: {path.name} carregado ({available[name]['fixture_id'].nunique()} fixtures)")
        elif path is not None:
            print(f"  {name}: AINDA NAO DISPONIVEL ({path.name} nao existe) -- pulando por enquanto")

    if not available:
        print("Nenhum candidato disponivel ainda.")
        return

    any_df = next(iter(available.values()))
    available["baseline_50_50"] = build_baseline(any_df, frac_2t=0.50)
    available["baseline_lit_55"] = build_baseline(any_df, frac_2t=0.55)

    all_scores = []
    for name, pred_df in available.items():
        scores = score_candidate(name, pred_df, gt)
        all_scores.append(scores)

    result = pd.concat(all_scores, ignore_index=True)
    out_csv = REPORTS_DIR / "score_comparison.csv"
    result.to_csv(out_csv, index=False)
    print(f"\nSalvo: {out_csv}\n")

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("=== Por market ===")
    print(result.pivot_table(index="candidate", columns="market", values="pmf_logloss"))

    print("\n=== Agregado (media simples entre os 4 markets) ===")
    agg = result.groupby("candidate")[["pmf_logloss", "mae", "bias"]].mean().sort_values("pmf_logloss")
    print(agg)


if __name__ == "__main__":
    main()
