#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_candidate_d_train.py
=======================================================
Runner do Candidato D (GLM supervisionado regularizado, rotulo REAL StatsBomb)
da pesquisa de escanteios por tempo (1T/2T) de clube. Ver
research_clubs/corners_halftime/candidate_d_supervised_glm.py para a logica e
o criterio de decisao pre-registrado (docstring do modulo).

Uso:
    python scripts/adhoc_corners_halftime_candidate_d_train.py
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

from research_clubs.corners_halftime.candidate_d_supervised_glm import (  # noqa: E402
    load_clean_frame,
    empirical_baseline_share,
    baseline_fit_predict_share,
    make_candidate_fit_predict_share,
    fit_final_model,
    C_GRID,
    R_TOTAL,
    FRAC_2T_MIN,
    FRAC_2T_MAX,
)
from research_clubs.corners_halftime.eval_halftime_smallN import (  # noqa: E402
    grouped_stratified_kfold_repeated,
    leave_one_tournament_out,
    bootstrap_delta_ci,
    binom_mixture_pmf,
)
from research_clubs.corners_halftime.candidate_a_transfer_glm import (  # noqa: E402
    load_prediction_universe,
    production_corners_totals,
    split_lambda_1t_2t,
    pmf_to_string,
)

OUT_CSV = ROOT / "data" / "reports" / "corners_halftime" / "candidate_d_predictions.csv"


def main():
    print("=" * 78)
    print(" Candidato D — GLM supervisionado regularizado (rotulo REAL, escanteios 1T/2T)")
    print("=" * 78)

    # ------------------------------------------------------------ 1) dados
    print("\n[1/8] Carregando o subconjunto 'clean' (rotulo REAL StatsBomb)...")
    gt_df = load_clean_frame()
    print(f"  N = {len(gt_df)}")
    print(f"  por torneio:\n{gt_df['tournament'].value_counts().to_string()}")
    baseline_global = empirical_baseline_share(gt_df)
    print(f"  baseline empirico (frame inteiro): {baseline_global:.6f}")

    # ------------------------------------------------------------ 2) validacao primaria
    print("\n[2/8] Validacao primaria in-distribution "
          "(grouped_stratified_kfold_repeated, 5 folds x 20 seeds)...")
    cand_fps = make_candidate_fit_predict_share(gt_df, c_grid=C_GRID, inner_folds=5, inner_seeds=3)
    base_fps = baseline_fit_predict_share(gt_df)

    res_cand = grouped_stratified_kfold_repeated(gt_df, cand_fps, n_folds=5, n_seeds=20)
    res_base = grouped_stratified_kfold_repeated(gt_df, base_fps, n_folds=5, n_seeds=20)

    merged = res_cand.merge(
        res_base, on=["seed", "fold"], suffixes=("_cand", "_base")
    )
    merged["delta"] = merged["pmf_logloss_cand"] - merged["pmf_logloss_base"]
    delta_mean_kfold = float(merged["delta"].mean())
    frac_better = float((merged["delta"] < 0).mean())
    print(f"  delta medio (candidato - baseline) de pmf_logloss: {delta_mean_kfold:+.6f}")
    print(f"  fracao de (seed,fold) com delta<0 (candidato melhor): {frac_better:.4f} "
          f"({int((merged['delta'] < 0).sum())}/{len(merged)})")
    criterion_b = frac_better >= 0.60
    print(f"  criterio (b) [>=60%]: {'PASSA' if criterion_b else 'FALHA'}")

    # ------------------------------------------------------------ 3) IC bootstrap
    print("\n[3/8] IC bootstrap do delta de log-loss (split externo 5-fold seed=0, out-of-fold)...")
    from sklearn.model_selection import StratifiedKFold
    fixture_ids = gt_df.index.values
    tournaments = gt_df["tournament"].values
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)

    frac_candidate_parts = []
    frac_baseline_parts = []
    for train_idx, test_idx in skf.split(fixture_ids, tournaments):
        train_ids = fixture_ids[train_idx]
        test_ids = fixture_ids[test_idx]
        frac_candidate_parts.append(cand_fps(train_ids, test_ids))
        frac_baseline_parts.append(base_fps(train_ids, test_ids))
    frac_candidate = pd.concat(frac_candidate_parts).sort_index()
    frac_baseline = pd.concat(frac_baseline_parts).sort_index()
    print(f"  cobertura out-of-fold: candidato={len(frac_candidate)}, baseline={len(frac_baseline)}, "
          f"gt_df={len(gt_df)}")

    boot = bootstrap_delta_ci(gt_df, frac_candidate, frac_baseline, n_boot=1000, seed=42)
    print(f"  mean_delta={boot['mean_delta']:+.6f}  ci95=[{boot['ci_lo']:+.6f}, {boot['ci_hi']:+.6f}]  "
          f"crosses_zero={boot['crosses_zero']}")
    criterion_a = (not boot["crosses_zero"]) and (boot["ci_hi"] < 0)
    print(f"  criterio (a) [IC 95% nao cruza zero, ci_hi<0]: {'PASSA' if criterion_a else 'FALHA'}")

    # ------------------------------------------------------------ 4) leave-one-tournament-out
    print("\n[4/8] Leave-one-tournament-out...")
    loto_cand = leave_one_tournament_out(gt_df, cand_fps)
    loto_base = leave_one_tournament_out(gt_df, base_fps)
    loto = loto_cand.merge(loto_base, on="held_out_tournament", suffixes=("_cand", "_base"))
    loto["delta"] = loto["pmf_logloss_cand"] - loto["pmf_logloss_base"]
    print(loto[["held_out_tournament", "n_test_cand", "pmf_logloss_cand", "pmf_logloss_base", "delta"]]
          .to_string(index=False))
    criterion_c = bool((loto["delta"] < 0).all())
    n_inverted = int((loto["delta"] >= 0).sum())
    print(f"  criterio (c) [candidato melhor em TODOS os torneios retidos]: "
          f"{'PASSA' if criterion_c else 'FALHA'} ({n_inverted} torneio(s) invertido(s)/empatado(s))")

    # ------------------------------------------------------------ 5) veredito
    print("\n[5/8] Veredito pre-registrado")
    print("-" * 78)
    print(f"  (a) IC bootstrap nao cruza zero: {criterion_a}  "
          f"(mean_delta={boot['mean_delta']:+.6f}, ci95=[{boot['ci_lo']:+.6f}, {boot['ci_hi']:+.6f}])")
    print(f"  (b) >=60% dos folds/seeds melhoram: {criterion_b}  ({frac_better:.1%})")
    print(f"  (c) leave-one-tournament-out nunca inverte: {criterion_c}  "
          f"({4 - n_inverted}/4 torneios melhores)")
    sinal_defensavel = criterion_a and criterion_b and criterion_c
    print(f"\n  VEREDITO: {'HA SINAL DEFENSAVEL' if sinal_defensavel else 'SEM SINAL DEFENSAVEL'}")
    print("-" * 78)

    # ------------------------------------------------------------ 6) modelo final
    print("\n[6/8] Ajustando modelo final (nested CV no 'clean' inteiro, 5 folds x 20 seeds)...")
    model, best_C_final, diag = fit_final_model(gt_df, c_grid=C_GRID, inner_folds=5, inner_seeds=20)
    print(f"  C final escolhido: {best_C_final}")
    print(f"  diagnostico por C:\n{diag.to_string(index=False)}")

    print("\n[7/8] Previsao no universo completo (6 competicoes-alvo) + cascata de producao...")
    df_pred = load_prediction_universe()
    print(f"  fixtures no universo: {len(df_pred)}")

    frac_2t = model.predict_share(df_pred)
    print(f"  fracao 2T prevista (clipada em [{FRAC_2T_MIN}, {FRAC_2T_MAX}]) — "
          f"media={frac_2t.mean():.4f} min={frac_2t.min():.4f} max={frac_2t.max():.4f}")

    totals = production_corners_totals(df_pred)
    lam_home_total = totals["lambdas_home_total"]
    lam_away_total = totals["mus_away_total"]

    lam_home_1t, lam_home_2t = split_lambda_1t_2t(lam_home_total, frac_2t)
    lam_away_1t, lam_away_2t = split_lambda_1t_2t(lam_away_total, frac_2t)

    # PMFs via mistura Binomial sobre a NB do TOTAL (mesma formula usada em
    # toda a validacao, eval_halftime_smallN.binom_mixture_pmf) -- garante
    # correspondencia exata entre o que foi validado e o que e entregue.
    pmf_home_2t = binom_mixture_pmf(lam_home_total, R_TOTAL, frac_2t)
    pmf_home_1t = binom_mixture_pmf(lam_home_total, R_TOTAL, 1.0 - frac_2t)
    pmf_away_2t = binom_mixture_pmf(lam_away_total, R_TOTAL, frac_2t)
    pmf_away_1t = binom_mixture_pmf(lam_away_total, R_TOTAL, 1.0 - frac_2t)

    print("\n[8/8] Montando CSV de saida (formato longo)...")
    fixture_ids_pred = df_pred["fixture_id"].values
    rows = []
    series = [
        ("home_1t", lam_home_1t, pmf_home_1t),
        ("away_1t", lam_away_1t, pmf_away_1t),
        ("home_2t", lam_home_2t, pmf_home_2t),
        ("away_2t", lam_away_2t, pmf_away_2t),
    ]
    for market, lam_arr, pmf_arr in series:
        for i in range(len(fixture_ids_pred)):
            rows.append({
                "fixture_id": fixture_ids_pred[i],
                "market": market,
                "lambda": float(lam_arr[i]),
                "pmf": pmf_to_string(pmf_arr[i]),
            })
    out_df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT_CSV, index=False)
    print(f"  CSV salvo em: {OUT_CSV} ({len(out_df)} linhas, {len(fixture_ids_pred)} fixtures x 4 markets)")

    # ------------------------------------------------------------ sanity check
    print("\n" + "=" * 78)
    print(" SANITY CHECK")
    print("=" * 78)
    print(f"(a) fixtures processados: {len(fixture_ids_pred)}")
    print(f"(b) len(csv) == len(universo)*4: {len(out_df) == len(fixture_ids_pred) * 4}")

    mean_home_split_sum = float(np.mean(lam_home_1t + lam_home_2t))
    mean_home_total_orig = float(np.mean(lam_home_total))
    mean_away_split_sum = float(np.mean(lam_away_1t + lam_away_2t))
    mean_away_total_orig = float(np.mean(lam_away_total))
    print(f"(c) mandante: media(home_1t_lambda + home_2t_lambda) = {mean_home_split_sum:.4f} "
          f"vs. media(lambda total original) = {mean_home_total_orig:.4f} "
          f"(diff={mean_home_split_sum - mean_home_total_orig:+.6f})")
    print(f"    visitante: media(away_1t_lambda + away_2t_lambda) = {mean_away_split_sum:.4f} "
          f"vs. media(mu total original) = {mean_away_total_orig:.4f} "
          f"(diff={mean_away_split_sum - mean_away_total_orig:+.6f})")

    pmf_sums = np.concatenate([
        pmf_home_1t.sum(axis=1), pmf_away_1t.sum(axis=1),
        pmf_home_2t.sum(axis=1), pmf_away_2t.sum(axis=1),
    ])
    max_dev = float(np.max(np.abs(pmf_sums - 1.0)))
    print(f"(d) maior desvio |soma(pmf)-1.0| entre todas as PMFs: {max_dev:.2e} "
          f"({'OK' if max_dev < 1e-6 else 'FALHA'})")

    print(f"\nVeredito final: {'HA SINAL DEFENSAVEL' if sinal_defensavel else 'SEM SINAL DEFENSAVEL'}")
    print("Candidato D concluido.")


if __name__ == "__main__":
    main()
