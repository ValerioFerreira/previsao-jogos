#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_candidate_a_train.py
=====================================================
Runner do Candidato A (GLM de transferencia heuristica) da pesquisa de
escanteios por tempo (1T/2T) de clube. Ver
research_clubs/corners_halftime/candidate_a_transfer_glm.py para a logica.

Uso:
    python scripts/adhoc_corners_halftime_candidate_a_train.py
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

from research_clubs.corners_halftime.candidate_a_transfer_glm import (  # noqa: E402
    CandidateATransferModel,
    available_feature_cols,
    load_prediction_universe,
    load_training_frame,
    nb_pmf_grid,
    pmf_to_string,
    production_corners_totals,
    split_lambda_1t_2t,
    ARTIFACT_PATH,
    R_HALF_FIXED,
    LITERATURE_PRIOR_2T_SHARE,
)

OUT_CSV = ROOT / "data" / "reports" / "corners_halftime" / "candidate_a_predictions.csv"


def main():
    print("=" * 78)
    print(" Candidato A — GLM de transferencia heuristica (escanteios 1T/2T, clube)")
    print("=" * 78)

    # 1) treino do GLM de transferencia (dataset amplo, alvo real gols/cartoes)
    print("\n[1/5] Carregando dataset de treino (amplo, alvo real gols/cartoes por tempo)...")
    df_train = load_training_frame()
    feature_cols = available_feature_cols(df_train)
    print(f"  linhas de treino: {len(df_train)}")
    print(f"  features usadas ({len(feature_cols)}): {feature_cols}")
    gap_missing = [c for c in [
        "gap_corners_home_att", "gap_corners_home_def",
        "gap_corners_away_att", "gap_corners_away_def",
        "gap_corners_exp_home", "gap_corners_exp_away",
    ] if c not in feature_cols]
    if gap_missing:
        print(f"  AVISO: colunas GAP de escanteio nao existem no parquet, ignoradas: {gap_missing}")

    print("\n[2/5] Ajustando os 2 GLMs (gols_2t_share, cartoes_2t_share) + calibracao...")
    model = CandidateATransferModel(feature_cols)
    model.fit(df_train)
    print(f"  media da fracao 'ritmo' prevista (pre-calibracao, in-sample): {model.train_mean_blend_:.4f}")
    print(f"  prior de literatura (2T): {LITERATURE_PRIOR_2T_SHARE:.4f}")
    print(f"  offset de calibracao aplicado: {model.calibration_offset_:+.4f}")
    model.save(ARTIFACT_PATH)
    print(f"  artefato salvo em: {ARTIFACT_PATH}")

    # 2) universo de previsao (6 competicoes-alvo, todos os fixtures)
    print("\n[3/5] Carregando universo de previsao (6 competicoes-alvo)...")
    df_pred = load_prediction_universe()
    print(f"  fixtures no universo: {len(df_pred)}")

    frac_2t = model.predict_frac_2t(df_pred)
    print(f"  fracao 2T prevista — media={frac_2t.mean():.4f} min={frac_2t.min():.4f} max={frac_2t.max():.4f}")

    # 3) total de escanteios via cascata de producao (so leitura dos artefatos)
    print("\n[4/5] Rodando a cascata de producao (chutes -> escanteios) sobre o universo...")
    totals = production_corners_totals(df_pred)
    lam_home_total = totals["lambdas_home_total"]
    lam_away_total = totals["mus_away_total"]

    lam_home_1t, lam_home_2t = split_lambda_1t_2t(lam_home_total, frac_2t)
    lam_away_1t, lam_away_2t = split_lambda_1t_2t(lam_away_total, frac_2t)

    pmf_home_1t = nb_pmf_grid(lam_home_1t, R_HALF_FIXED)
    pmf_home_2t = nb_pmf_grid(lam_home_2t, R_HALF_FIXED)
    pmf_away_1t = nb_pmf_grid(lam_away_1t, R_HALF_FIXED)
    pmf_away_2t = nb_pmf_grid(lam_away_2t, R_HALF_FIXED)

    # 4) monta CSV longo
    print("\n[5/5] Montando CSV de saida (formato longo)...")
    fixture_ids = df_pred["fixture_id"].values
    rows = []
    series = [
        ("home_1t", lam_home_1t, pmf_home_1t),
        ("away_1t", lam_away_1t, pmf_away_1t),
        ("home_2t", lam_home_2t, pmf_home_2t),
        ("away_2t", lam_away_2t, pmf_away_2t),
    ]
    for market, lam_arr, pmf_arr in series:
        for i in range(len(fixture_ids)):
            rows.append({
                "fixture_id": fixture_ids[i],
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

    mean_home_split_sum = float(np.mean(lam_home_1t + lam_home_2t))
    mean_home_total_orig = float(np.mean(lam_home_total))
    mean_away_split_sum = float(np.mean(lam_away_1t + lam_away_2t))
    mean_away_total_orig = float(np.mean(lam_away_total))
    print(f"(b) mandante: media(home_1t_lambda + home_2t_lambda) = {mean_home_split_sum:.4f} "
          f"vs. media(lambda total original) = {mean_home_total_orig:.4f} "
          f"(diff={mean_home_split_sum - mean_home_total_orig:+.6f})")
    print(f"    visitante: media(away_1t_lambda + away_2t_lambda) = {mean_away_split_sum:.4f} "
          f"vs. media(mu total original) = {mean_away_total_orig:.4f} "
          f"(diff={mean_away_split_sum - mean_away_total_orig:+.6f})")

    print(f"(c) fracao media prevista de 2T: {frac_2t.mean():.4f} "
          f"(literatura/prior usado na calibracao: {LITERATURE_PRIOR_2T_SHARE:.4f})")

    print("\nCandidato A concluido.")


if __name__ == "__main__":
    main()
