#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_candidate_e_train.py
======================================================
Runner do Candidato E (fracao empirica por torneio com shrinkage
James-Stein/empirical Bayes) da pesquisa de escanteios por tempo (1T/2T) de
clube. Ver research_clubs/corners_halftime/candidate_e_tournament_shrinkage.py
para a logica.

Uso:
    python scripts/adhoc_corners_halftime_candidate_e_train.py
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

from research_clubs.corners_halftime.candidate_e_tournament_shrinkage import (  # noqa: E402
    K_GRID,
    TARGET_TOURNAMENTS,
    load_clean_gt,
    compute_tournament_stats,
    make_fit_predict_share,
    make_fit_predict_share_baseline,
    select_k_by_cv,
    oof_predictions,
    fit_final_tournament_fracs,
    predict_universe_frac2t,
    load_feature_universe,
    production_corners_distributions,
    binom_mixture,
    pmf_to_string,
    leave_one_tournament_out,
    bootstrap_delta_ci,
)

OUT_CSV = ROOT / "data" / "reports" / "corners_halftime" / "candidate_e_predictions.csv"
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "research_clubs" / "corners_halftime" / "artifacts"
META_OUT_PATH = ARTIFACT_DIR / "candidate_e_meta.json"

N_FOLDS = 5
N_SEEDS = 20

# faixa ampla ao redor de k* pra checar o criterio (c) -- ganho nao pode
# desaparecer so por causa de mais shrinkage (senao e overfitting no N
# pequeno por torneio, nao heterogeneidade real).
K_SENSITIVITY_NEIGHBORS = 3


def main():
    print("=" * 78)
    print(" Candidato E -- fracao empirica por torneio com shrinkage (escanteios 1T/2T, clube)")
    print("=" * 78)

    # ---------------------------------------------------------- (1) contexto
    print("\n[1/10] Carregando GT limpo (sample_type=='clean')...")
    gt_df = load_clean_gt()
    print(f"  N={len(gt_df)}  torneios={sorted(gt_df['tournament'].unique().tolist())}")
    frac_whole, n_whole, global_frac_whole = compute_tournament_stats(gt_df)
    print(f"  fracao GLOBAL (base inteira, so contexto): {global_frac_whole:.4f}")
    print("  fracao por torneio (base inteira, SEM shrinkage, SEM fold-safety -- so contexto):")
    for tour in sorted(frac_whole):
        print(f"    {tour:20s} frac={frac_whole[tour]:.4f}  n_escanteios={n_whole[tour]:.0f}")

    # ---------------------------------------------------------- (2) grid de k
    print(f"\n[2/10] Grid search de k ({len(K_GRID)} valores, {N_FOLDS}x{N_SEEDS}={N_FOLDS*N_SEEDS} splits por k)...")
    grid_df = select_k_by_cv(gt_df, K_GRID, n_folds=N_FOLDS, n_seeds=N_SEEDS)
    print(grid_df.to_string(index=False, float_format=lambda v: f"{v:.6f}"))

    # ---------------------------------------------------------- (3) escolhe k*
    best_row = grid_df.loc[grid_df["mean_logloss"].idxmin()]
    k_star = float(best_row["k"])
    print(f"\n[3/10] k* escolhido (menor mean_logloss no grid): k*={k_star:g} "
          f"(delta_vs_baseline={best_row['delta_vs_baseline']:+.6f}, "
          f"frac_folds_better={best_row['frac_folds_better']:.3f})")

    sorted_ks = sorted(K_GRID)
    k_idx = sorted_ks.index(k_star) if k_star in sorted_ks else None
    neighbor_ks = []
    if k_idx is not None:
        lo = max(0, k_idx - K_SENSITIVITY_NEIGHBORS)
        hi = min(len(sorted_ks), k_idx + K_SENSITIVITY_NEIGHBORS + 1)
        neighbor_ks = sorted_ks[lo:hi]
    sens_df = grid_df[grid_df["k"].isin(neighbor_ks)].sort_values("k")
    print("  tabela de sensibilidade ao redor de k* (criterio c -- o ganho nao pode so existir em k~0):")
    print(sens_df.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
    all_improve = bool((grid_df["delta_vs_baseline"] < 0).all())
    n_improve = int((grid_df["delta_vs_baseline"] < 0).sum())
    print(f"  numero de k's no grid inteiro com delta_vs_baseline < 0: {n_improve}/{len(grid_df)}")
    criterion_c_pass = bool((sens_df["delta_vs_baseline"] < 0).sum() >= max(2, len(sens_df) - 1))
    print(f"  criterio (c) [ganho nao desaparece com mais shrinkage]: {'PASSA' if criterion_c_pass else 'FALHA'}")

    # ---------------------------------------------------------- (4) full 5x20 k* vs baseline
    print(f"\n[4/10] Resultado completo {N_FOLDS}x{N_SEEDS}={N_FOLDS*N_SEEDS} folds/seeds -- k*={k_star:g} vs. baseline...")
    frac_folds_better = float(best_row["frac_folds_better"])
    criterion_b_pass = frac_folds_better >= 0.60
    print(f"  frac_folds_better (candidato k* < baseline): {frac_folds_better:.3f}")
    print(f"  criterio (b) [melhora em >=60% dos {N_FOLDS*N_SEEDS} folds/seeds]: {'PASSA' if criterion_b_pass else 'FALHA'}")

    # ---------------------------------------------------------- (5) leave-one-tournament-out
    print("\n[5/10] Leave-one-tournament-out -- k* vs. baseline (espera-se colapso ~identico)...")
    loto_cand = leave_one_tournament_out(gt_df, make_fit_predict_share(gt_df, k_star))
    loto_base = leave_one_tournament_out(gt_df, make_fit_predict_share_baseline(gt_df))
    loto_cmp = loto_cand[["held_out_tournament", "n_test", "pmf_logloss"]].rename(
        columns={"pmf_logloss": "pmf_logloss_candidate"})
    loto_cmp["pmf_logloss_baseline"] = loto_base["pmf_logloss"].to_numpy()
    loto_cmp["diff"] = loto_cmp["pmf_logloss_candidate"] - loto_cmp["pmf_logloss_baseline"]
    print(loto_cmp.to_string(index=False, float_format=lambda v: f"{v:.6f}"))
    loto_max_abs_diff = float(loto_cmp["diff"].abs().max())
    print(f"  maior |diff| absoluto entre candidato e baseline no LOTO: {loto_max_abs_diff:.6f} "
          f"({'colapso confirmado' if loto_max_abs_diff < 1e-3 else 'ATENCAO: nao colapsou como esperado'})")

    # ---------------------------------------------------------- (6) oof + bootstrap
    print("\n[6/10] Previsoes out-of-fold (candidato k* e baseline) + IC bootstrap do delta...")
    oof_cand = oof_predictions(gt_df, make_fit_predict_share(gt_df, k_star), n_folds=N_FOLDS, seed=42)
    oof_base = oof_predictions(gt_df, make_fit_predict_share_baseline(gt_df), n_folds=N_FOLDS, seed=42)
    boot = bootstrap_delta_ci(gt_df, oof_cand, oof_base, n_boot=1000, seed=42)
    print(f"  mean_delta={boot['mean_delta']:+.6f}  IC95%=[{boot['ci_lo']:+.6f}, {boot['ci_hi']:+.6f}]  "
          f"crosses_zero={boot['crosses_zero']}  frac_boot_candidate_better={boot['frac_seeds_candidate_better']:.3f}")
    criterion_a_pass = bool(not boot["crosses_zero"] and boot["mean_delta"] < 0)
    print(f"  criterio (a) [IC bootstrap 95% do delta nao cruza zero, favoravel ao candidato]: "
          f"{'PASSA' if criterion_a_pass else 'FALHA'}")

    # ---------------------------------------------------------- (7) veredito
    print("\n[7/10] Veredito do criterio pre-registrado (TODOS simultaneos)...")
    print(f"  (a) IC bootstrap nao cruza zero (favoravel):  {'PASSA' if criterion_a_pass else 'FALHA'}")
    print(f"  (b) melhora em >=60% dos {N_FOLDS*N_SEEDS} folds/seeds:      {'PASSA' if criterion_b_pass else 'FALHA'}")
    print(f"  (c) ganho nao desaparece com mais shrinkage:  {'PASSA' if criterion_c_pass else 'FALHA'}")
    veredito_heterogeneidade = bool(criterion_a_pass and criterion_b_pass and criterion_c_pass)
    veredito_str = ("HA HETEROGENEIDADE REAL ENTRE TORNEIOS (candidato E promissor)"
                     if veredito_heterogeneidade else
                     "SEM HETEROGENEIDADE DEFENSAVEL (candidato E nao bate o baseline global sob o criterio pre-registrado)")
    print(f"\n  >>> VEREDITO: {veredito_str}")

    # ---------------------------------------------------------- (8) ajuste final + universo de producao
    print(f"\n[8/10] Ajuste final (base 'clean' inteira, k*={k_star:g}) + previsao do universo de producao...")
    shrunk_by_t, global_frac_final = fit_final_tournament_fracs(gt_df, k_star)
    print("  fracoes finais por torneio (shrunk, k*):")
    for tour in sorted(shrunk_by_t):
        print(f"    {tour:20s} frac_shrunk={shrunk_by_t[tour]:.4f}  frac_empirica={frac_whole.get(tour, float('nan')):.4f}")
    print(f"  fracao global (fallback p/ torneios sem GT 'clean'): {global_frac_final:.4f}")

    fallback_tournaments = [t for t in TARGET_TOURNAMENTS if t not in shrunk_by_t]
    print(f"  torneios-alvo SEM GT 'clean' (usam fallback frac_global): {fallback_tournaments}")

    print("  carregando universo de features de producao...")
    df_all = load_feature_universe()
    df_pred = df_all[df_all["tournament"].isin(TARGET_TOURNAMENTS)].reset_index(drop=True)
    print(f"  fixtures no universo-alvo: {len(df_pred)}")

    frac2t = predict_universe_frac2t(df_pred, shrunk_by_t, global_frac_final)
    print(f"  fracao 2T aplicada -- media={frac2t.mean():.4f} min={frac2t.min():.4f} max={frac2t.max():.4f}")

    print("  cascata de producao (chutes -> escanteios, so leitura) + mistura binomial...")
    cd = production_corners_distributions(df_pred)
    lam_home_total = np.asarray(cd["lambdas"], dtype=float)
    lam_away_total = np.asarray(cd["mus"], dtype=float)
    home_total_pmf = np.asarray(cd["home"], dtype=float)
    away_total_pmf = np.asarray(cd["away"], dtype=float)

    lam_home_2t = lam_home_total * frac2t
    lam_home_1t = lam_home_total * (1.0 - frac2t)
    lam_away_2t = lam_away_total * frac2t
    lam_away_1t = lam_away_total * (1.0 - frac2t)

    pmf_home_2t = binom_mixture(home_total_pmf, frac2t)
    pmf_home_1t = binom_mixture(home_total_pmf, 1.0 - frac2t)
    pmf_away_2t = binom_mixture(away_total_pmf, frac2t)
    pmf_away_1t = binom_mixture(away_total_pmf, 1.0 - frac2t)

    # ---------------------------------------------------------- (9) salva CSV + meta
    print("\n[9/10] Montando CSV de saida (formato longo) + meta.json...")
    fixture_ids = df_pred["fixture_id"].to_numpy()
    series = [
        ("home_1t", lam_home_1t, pmf_home_1t),
        ("away_1t", lam_away_1t, pmf_away_1t),
        ("home_2t", lam_home_2t, pmf_home_2t),
        ("away_2t", lam_away_2t, pmf_away_2t),
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

    meta_out = {
        "k_grid": K_GRID,
        "k_star": k_star,
        "grid_results": grid_df.to_dict(orient="records"),
        "sensitivity_table_around_k_star": sens_df.to_dict(orient="records"),
        "tournament_fracs_whole_dataset_context": frac_whole,
        "tournament_n_escanteios_whole_dataset": n_whole,
        "global_frac_whole_dataset": global_frac_whole,
        "tournament_fracs_final_shrunk": shrunk_by_t,
        "global_frac_final": global_frac_final,
        "fallback_tournaments": fallback_tournaments,
        "leave_one_tournament_out": loto_cmp.to_dict(orient="records"),
        "loto_max_abs_diff_candidate_vs_baseline": loto_max_abs_diff,
        "bootstrap_delta_ci": boot,
        "criteria": {
            "a_bootstrap_ci_excludes_zero_favorable": criterion_a_pass,
            "b_improves_in_ge_60pct_folds_seeds": criterion_b_pass,
            "b_frac_folds_better": frac_folds_better,
            "c_gain_survives_more_shrinkage": criterion_c_pass,
        },
        "veredito_heterogeneidade_real": veredito_heterogeneidade,
        "veredito": veredito_str,
        "n_fixtures_predicted": int(len(df_pred)),
        "target_tournaments": TARGET_TOURNAMENTS,
        "frac2t_mean": float(frac2t.mean()), "frac2t_min": float(frac2t.min()), "frac2t_max": float(frac2t.max()),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with open(META_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(meta_out, f, ensure_ascii=False, indent=2, default=str)
    print(f"  meta salvo em: {META_OUT_PATH}")

    # ---------------------------------------------------------- (10) sanity check
    print("\n" + "=" * 78)
    print(" SANITY CHECK")
    print("=" * 78)
    mean_home_split_sum = float(np.mean(lam_home_1t + lam_home_2t))
    mean_home_total_orig = float(np.mean(lam_home_total))
    mean_away_split_sum = float(np.mean(lam_away_1t + lam_away_2t))
    mean_away_total_orig = float(np.mean(lam_away_total))
    print(f"(a) fixtures processados: {len(fixture_ids)}")
    print(f"(b) mandante: media(home_1t_lambda + home_2t_lambda) = {mean_home_split_sum:.4f} "
          f"vs. media(lambda total original) = {mean_home_total_orig:.4f} "
          f"(diff={mean_home_split_sum - mean_home_total_orig:+.6f})")
    print(f"    visitante: media(away_1t_lambda + away_2t_lambda) = {mean_away_split_sum:.4f} "
          f"vs. media(mu total original) = {mean_away_total_orig:.4f} "
          f"(diff={mean_away_split_sum - mean_away_total_orig:+.6f})")

    print(f"\n>>> VEREDITO FINAL: {veredito_str}")
    print("\nCandidato E concluido.")


if __name__ == "__main__":
    main()
