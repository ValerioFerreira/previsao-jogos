#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_candidate_c_train.py
======================================================
Runner do Candidato C (GBM de transferencia, feature set completo) da
pesquisa de escanteios por tempo (1T/2T) de clube. Ver
research_clubs/corners_halftime/candidate_c_gbm_transfer.py para a logica.

Uso:
    python scripts/adhoc_corners_halftime_candidate_c_train.py
"""
from __future__ import annotations

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

from research_clubs.corners_halftime.candidate_c_gbm_transfer import (  # noqa: E402
    pmf_to_string,
    train_and_predict,
)

OUT_CSV = ROOT / "data" / "reports" / "corners_halftime" / "candidate_c_predictions.csv"


def main():
    print("=" * 78)
    print(" Candidato C -- GBM de transferencia, feature set completo (escanteios 1T/2T, clube)")
    print("=" * 78)

    result = train_and_predict()

    print("\nMontando CSV de saida (formato longo)...")
    fixture_ids = result["fixture_id"]
    series = [
        ("home_1t", result["lam_home_1t"], result["pmf_home_1t"]),
        ("away_1t", result["lam_away_1t"], result["pmf_away_1t"]),
        ("home_2t", result["lam_home_2t"], result["pmf_home_2t"]),
        ("away_2t", result["lam_away_2t"], result["pmf_away_2t"]),
    ]
    rows = []
    for market, lam_arr, pmf_arr in series:
        for i in range(len(fixture_ids)):
            rows.append({
                "fixture_id": int(fixture_ids[i]),
                "market": market,
                "lambda": float(lam_arr[i]),
                "pmf": pmf_to_string(pmf_arr[i]),
            })
    out_df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT_CSV, index=False)
    print(f"  CSV salvo em: {OUT_CSV} ({len(out_df)} linhas, {len(fixture_ids)} fixtures x 4 markets)")

    # ------------------------------------------------------------ sanity check
    print("\n" + "=" * 78)
    print(" SANITY CHECK")
    print("=" * 78)
    print(f"(a) fixtures processados: {len(fixture_ids)}")

    mean_home_split_sum = float(np.mean(result["lam_home_1t"] + result["lam_home_2t"]))
    mean_home_total_orig = float(np.mean(result["lam_home_total_orig"]))
    mean_away_split_sum = float(np.mean(result["lam_away_1t"] + result["lam_away_2t"]))
    mean_away_total_orig = float(np.mean(result["lam_away_total_orig"]))
    print(f"(b) mandante: media(home_1t_lambda + home_2t_lambda) = {mean_home_split_sum:.4f} "
          f"vs. media(lambda total original) = {mean_home_total_orig:.4f} "
          f"(diff={mean_home_split_sum - mean_home_total_orig:+.6f})")
    print(f"    visitante: media(away_1t_lambda + away_2t_lambda) = {mean_away_split_sum:.4f} "
          f"vs. media(mu total original) = {mean_away_total_orig:.4f} "
          f"(diff={mean_away_split_sum - mean_away_total_orig:+.6f})")
    total_split_sum = mean_home_split_sum + mean_away_split_sum
    total_orig = mean_home_total_orig + mean_away_total_orig
    print(f"    total (mandante+visitante): split={total_split_sum:.4f} vs. original={total_orig:.4f} "
          f"(diff={total_split_sum - total_orig:+.6f})")

    print(f"\n(c) R^2 fora-da-amostra (holdout temporal 15%): "
          f"goals_2t_share={result['r2_goals']:.4f}  cards_2t_share={result['r2_cards']:.4f}")
    print(f"    pesos da combinacao: gols={result['w_goals']:.3f}  cartoes={result['w_cards']:.3f}")
    print(f"    fracao 2T combinada -- media={result['p2t'].mean():.4f} "
          f"min={result['p2t'].min():.4f} max={result['p2t'].max():.4f}")

    print("\n    top 10 features -- goals_2t_share:")
    for feat, imp in result["top_features_goals"]:
        print(f"      {feat:40s} {imp:.4f}")
    print("\n    top 10 features -- cards_2t_share:")
    for feat, imp in result["top_features_cards"]:
        print(f"      {feat:40s} {imp:.4f}")

    print("\nCandidato C concluido.")


if __name__ == "__main__":
    main()
