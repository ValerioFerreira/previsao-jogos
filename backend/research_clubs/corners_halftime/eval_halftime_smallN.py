#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/eval_halftime_smallN.py
===========================================================
Harness de avaliação compartilhado pros candidatos D/E (rótulo REAL StatsBomb,
N pequeno ~1516 "clean" -- quase tudo 1 temporada-calendário só, split
temporal classico de research_clubs/protocol.py::temporal_folds NAO e
informativo aqui). Reusa pmf_logloss/pmf_mae/coverage80 de protocol.py.

Fornece:
  - grouped_stratified_kfold_repeated: avaliacao primaria in-distribution.
  - leave_one_tournament_out: teste de generalizacao cross-liga.
  - bootstrap_delta_ci: IC do delta de log-loss candidato-vs-baseline.

Um "fit_predict_share" e uma funcao (train_df, test_df) -> Series frac_2t
prevista pro test_df, indexada por fixture_id. O harness cuida da mistura
Binomial com o total ja validado (lambda_total do modelo de producao,
presente nas colunas home_total/away_total do gt_df) e do calculo de metricas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import nbinom, binom

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research_clubs.protocol import pmf_logloss, pmf_mae, coverage80  # noqa: E402

MAX_CORNERS = 15


def binom_mixture_pmf(total_lambda: np.ndarray, r_total: float, frac: np.ndarray, max_k: int = MAX_CORNERS) -> np.ndarray:
    """PMF do meio-jogo via mistura Binomial sobre a PMF NB do total:
    P(half=k) = sum_n P(total=n) * Binomial(k; n, frac).
    Mais correto que só escalar o lambda (preserva a soma exata e a forma
    discreta do total ja validado em producao)."""
    N = len(total_lambda)
    grid_total = np.arange(max_k * 2 + 1)
    p_nb = r_total / (r_total + total_lambda)
    pmf_total = nbinom.pmf(grid_total[None, :], n=r_total, p=p_nb[:, None])
    pmf_total = pmf_total / pmf_total.sum(axis=1, keepdims=True)

    pmf_half = np.zeros((N, max_k + 1))
    for n in grid_total:
        if n == 0:
            pmf_half[:, 0] += pmf_total[:, n]
            continue
        k_vals = np.arange(min(n, max_k) + 1)
        binom_pmf = binom.pmf(k_vals[None, :], n=n, p=frac[:, None])
        pmf_half[:, :len(k_vals)] += pmf_total[:, n:n + 1] * binom_pmf
    pmf_half = pmf_half / pmf_half.sum(axis=1, keepdims=True)
    return pmf_half


def build_pmfs_for_matches(gt_df: pd.DataFrame, frac_2t: pd.Series, r_total: float = 8.5) -> dict[str, np.ndarray]:
    """gt_df precisa ter home_total_lambda/away_total_lambda (do modelo de
    producao) indexado por fixture_id, na mesma ordem de frac_2t.index."""
    idx = frac_2t.index
    sub = gt_df.loc[idx]
    frac = frac_2t.values
    out = {}
    for side in ("home", "away"):
        total_lambda = sub[f"{side}_total_lambda"].values
        pmf_2t = binom_mixture_pmf(total_lambda, r_total, frac)
        pmf_1t = binom_mixture_pmf(total_lambda, r_total, 1 - frac)
        out[f"{side}_1t"] = pmf_1t
        out[f"{side}_2t"] = pmf_2t
    return out


def score_pmfs(gt_df: pd.DataFrame, fixture_ids: pd.Index, pmfs: dict[str, np.ndarray]) -> dict[str, float]:
    sub = gt_df.loc[fixture_ids]
    market_cols = {"home_1t": "home_corners_1t", "away_1t": "away_corners_1t",
                   "home_2t": "home_corners_2t", "away_2t": "away_corners_2t"}
    loglosses, maes = [], []
    for market, col in market_cols.items():
        y = sub[col].clip(upper=MAX_CORNERS).values.astype(int)
        loglosses.append(pmf_logloss(y, pmfs[market]))
        maes.append(pmf_mae(y, pmfs[market]))
    return {"pmf_logloss": float(np.mean(loglosses)), "mae": float(np.mean(maes))}


def grouped_stratified_kfold_repeated(gt_df: pd.DataFrame, fit_predict_share, n_folds: int = 5, n_seeds: int = 20) -> pd.DataFrame:
    """gt_df: indexado por fixture_id, com coluna 'tournament' e colunas de
    rotulo/total. fit_predict_share(train_ids, test_ids) -> Series frac_2t
    indexada pelos test_ids."""
    rows = []
    fixture_ids = gt_df.index.values
    tournaments = gt_df["tournament"].values
    from sklearn.model_selection import StratifiedKFold
    for seed in range(n_seeds):
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for fold_i, (train_idx, test_idx) in enumerate(skf.split(fixture_ids, tournaments)):
            train_ids = fixture_ids[train_idx]
            test_ids = fixture_ids[test_idx]
            frac_pred = fit_predict_share(train_ids, test_ids)
            pmfs = build_pmfs_for_matches(gt_df, frac_pred)
            metrics = score_pmfs(gt_df, frac_pred.index, pmfs)
            rows.append({"seed": seed, "fold": fold_i, "n_test": len(test_ids), **metrics})
    return pd.DataFrame(rows)


def leave_one_tournament_out(gt_df: pd.DataFrame, fit_predict_share) -> pd.DataFrame:
    rows = []
    for tour in gt_df["tournament"].unique():
        test_ids = gt_df.index[gt_df["tournament"] == tour].values
        train_ids = gt_df.index[gt_df["tournament"] != tour].values
        if len(test_ids) < 10 or len(train_ids) < 50:
            continue
        frac_pred = fit_predict_share(train_ids, test_ids)
        pmfs = build_pmfs_for_matches(gt_df, frac_pred)
        metrics = score_pmfs(gt_df, frac_pred.index, pmfs)
        rows.append({"held_out_tournament": tour, "n_test": len(test_ids), **metrics})
    return pd.DataFrame(rows)


def bootstrap_delta_ci(gt_df: pd.DataFrame, frac_candidate: pd.Series, frac_baseline: pd.Series,
                        n_boot: int = 1000, seed: int = 42) -> dict:
    """IC bootstrap (percentil 2.5/97.5) do delta de log-loss medio
    (candidato - baseline) por partida, reamostrando partidas com reposicao."""
    common_idx = frac_candidate.index.intersection(frac_baseline.index)
    pmfs_c = build_pmfs_for_matches(gt_df, frac_candidate.loc[common_idx])
    pmfs_b = build_pmfs_for_matches(gt_df, frac_baseline.loc[common_idx])

    sub = gt_df.loc[common_idx]
    market_cols = {"home_1t": "home_corners_1t", "away_1t": "away_corners_1t",
                   "home_2t": "home_corners_2t", "away_2t": "away_corners_2t"}

    per_match_logloss_c = np.zeros(len(common_idx))
    per_match_logloss_b = np.zeros(len(common_idx))
    for market, col in market_cols.items():
        y = sub[col].clip(upper=MAX_CORNERS).values.astype(int)
        p_c = np.clip(pmfs_c[market][np.arange(len(y)), y], 1e-9, 1.0)
        p_b = np.clip(pmfs_b[market][np.arange(len(y)), y], 1e-9, 1.0)
        per_match_logloss_c += -np.log(p_c) / 4
        per_match_logloss_b += -np.log(p_b) / 4

    delta = per_match_logloss_c - per_match_logloss_b
    rng = np.random.default_rng(seed)
    n = len(delta)
    boot_means = np.array([rng.choice(delta, size=n, replace=True).mean() for _ in range(n_boot)])
    return {
        "mean_delta": float(delta.mean()),
        "ci_lo": float(np.percentile(boot_means, 2.5)),
        "ci_hi": float(np.percentile(boot_means, 97.5)),
        "crosses_zero": bool(np.percentile(boot_means, 2.5) <= 0 <= np.percentile(boot_means, 97.5)),
        "frac_seeds_candidate_better": float((boot_means < 0).mean()),
    }
