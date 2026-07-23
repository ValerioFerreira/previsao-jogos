#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/candidate_e_tournament_shrinkage.py
=====================================================================
Candidato E ("fração empírica por torneio com shrinkage") da pesquisa de
escanteios por tempo (1T/2T) de clube.

Os candidatos A/B/C (proxy gols/cartões -> fração 2T via GLM/simulação/GBM,
usando o feature set COMPLETO por jogo) empataram com o baseline ingênuo
(fração global constante) na avaliação com rótulo real StatsBomb. Este
candidato testa uma hipótese mais simples e ortogonal: será que existe
heterogeneidade real ENTRE TORNEIOS na fração de escanteios que cai no 2º
tempo -- mesmo sem nenhum sinal por-jogo? Ou seja, "Ligue 1 tem 2T mais
carregado que Serie A" (uma constante por liga), não "este jogo específico
tende a ter mais escanteios no 2T" (o que A/B/C tentaram e não conseguiram).

Método: fração empírica de escanteios-2T por torneio, com shrinkage
James-Stein / empirical Bayes em direção à fração GLOBAL, ponderado pelo
número de ESCANTEIOS observados no torneio (não jogos -- é o denominador
correto da proporção binomial):

    frac_torneio_empirica = sum(escanteios_2T no torneio) / sum(escanteios_totais no torneio)
    frac_global            = sum(escanteios_2T geral)     / sum(escanteios_totais geral)
    w                       = n_torneio / (n_torneio + k)
    frac_torneio_shrunk    = w * frac_torneio_empirica + (1 - w) * frac_global

`k` (força do shrinkage) é escolhido por CV (grid search), não fixo --
ver `select_k_by_cv`. Fold-safe: dentro de cada fold do k-fold, a fração
por torneio usada pra prever o teste vem só dos `train_ids` daquele fold
(nunca vaza informação do fold de teste).

Critério de decisão pré-registrado (ver scripts/adhoc_corners_halftime_
candidate_e_train.py) -- só "há heterogeneidade real" se, TODOS
simultaneamente:
  (a) IC bootstrap 95% do delta de log-loss (candidato k* vs. baseline
      fração global) não cruza zero;
  (b) melhora em >=60% dos 100 folds/seeds (5 folds x 20 seeds);
  (c) o ganho não desaparece quando k aumenta (tabela de sensibilidade --
      se só funciona com k próximo de 0, é overfitting/memorização do N
      pequeno por torneio, não heterogeneidade real).

Reusa (import, sem duplicar) de `candidate_c_gbm_transfer.py`:
`TARGET_TOURNAMENTS`, `load_feature_universe`, `production_corners_
distributions`, `binom_mixture`, `pmf_to_string`, `FRAC_2T_MIN`/`FRAC_2T_MAX`.
Reusa o harness inteiro (avaliação com rótulo real, N pequeno) de
`eval_halftime_smallN.py`: `grouped_stratified_kfold_repeated`,
`leave_one_tournament_out`, `bootstrap_delta_ci` (que por sua vez usa
`binom_mixture_pmf` internamente, r_total=8.5).

Não mexe em `model_artifacts_clubes/*.joblib`, `predictor.py`, nem em
nenhum arquivo `candidate_a/b/c/d_*`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_clubs.corners_halftime.candidate_c_gbm_transfer import (  # noqa: E402
    FRAC_2T_MIN,
    FRAC_2T_MAX,
    TARGET_TOURNAMENTS,
    load_feature_universe,
    production_corners_distributions,
    binom_mixture,
    pmf_to_string,
)
from research_clubs.corners_halftime.eval_halftime_smallN import (  # noqa: E402
    grouped_stratified_kfold_repeated,
    leave_one_tournament_out,
    bootstrap_delta_ci,
)

# ------------------------------------------------------------------ caminhos
EVAL_FRAME_PARQUET = ROOT / "data" / "external" / "corners_halftime_eval_frame.parquet"

# grid de k (forca do shrinkage) para o CV -- de "quase sem shrinkage" (k=0,
# equivale a fracao empirica pura por torneio) ate "shrinkage tao forte que
# equivale ao baseline global" (k=50000 >> qualquer n_torneio observado, que
# fica na casa de poucos milhares de escanteios).
K_GRID = [0, 1, 5, 10, 25, 50, 100, 200, 400, 800, 1500, 3000, 6000, 12000, 25000, 50000]


# ============================================================ dados (GT)
def load_clean_gt() -> pd.DataFrame:
    """corners_halftime_eval_frame.parquet, filtrado a sample_type=='clean'
    (N=1516, 4 torneios -- La Liga/Serie A Italia/Premier League/Ligue 1).
    Indexado por fixture_id (ja e o indice nativo do parquet)."""
    df = pd.read_parquet(EVAL_FRAME_PARQUET)
    df = df[df["sample_type"] == "clean"].copy()
    if df.index.name != "fixture_id":
        df = df.reset_index().set_index("fixture_id")
    return df


# ============================================================ estatisticas por torneio
def _corner_sums(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(total_2t, total_all) por LINHA (mandante+visitante somados)."""
    total_2t = df["home_corners_2t"] + df["away_corners_2t"]
    total_all = (df["home_corners_1t"] + df["home_corners_2t"]
                 + df["away_corners_1t"] + df["away_corners_2t"])
    return total_2t, total_all


def compute_tournament_stats(train_df: pd.DataFrame) -> tuple[dict[str, float], dict[str, float], float]:
    """Retorna (frac_by_tournament, n_by_tournament, global_frac) computados
    SÓ sobre train_df -- n_by_tournament é o total de escanteios observados
    no torneio (denominador correto da proporcao binomial, nao numero de
    jogos)."""
    total_2t, total_all = _corner_sums(train_df)
    global_all = float(total_all.sum())
    global_frac = float(total_2t.sum()) / global_all if global_all > 0 else 0.5

    frac_by_t: dict[str, float] = {}
    n_by_t: dict[str, float] = {}
    for tour in train_df["tournament"].unique():
        mask = train_df["tournament"] == tour
        t_all = float(total_all[mask].sum())
        t_2t = float(total_2t[mask].sum())
        n_by_t[tour] = t_all
        frac_by_t[tour] = (t_2t / t_all) if t_all > 0 else global_frac
    return frac_by_t, n_by_t, global_frac


def shrink_fracs(frac_by_t: dict[str, float], n_by_t: dict[str, float],
                  global_frac: float, k: float) -> dict[str, float]:
    """Shrinkage James-Stein / empirical Bayes: w = n / (n + k)."""
    out = {}
    for tour, frac in frac_by_t.items():
        n = n_by_t[tour]
        denom = n + k
        w = (n / denom) if denom > 0 else 0.0
        out[tour] = w * frac + (1.0 - w) * global_frac
    return out


# ============================================================ fit_predict_share (harness)
def make_fit_predict_share(gt_df: pd.DataFrame, k: float,
                            clip: tuple[float, float] = (FRAC_2T_MIN, FRAC_2T_MAX)) -> Callable:
    """Fold-safe: fracoes por torneio (e a fracao global usada tanto pro
    shrinkage quanto como fallback) sao recomputadas SÓ com gt_df.loc[train_ids]
    a cada chamada. Torneio do teste ausente no treino (leave-one-tournament-out)
    -> cai no fallback global (colapso esperado)."""
    def fit_predict(train_ids: np.ndarray, test_ids: np.ndarray) -> pd.Series:
        train_df = gt_df.loc[train_ids]
        frac_by_t, n_by_t, global_frac = compute_tournament_stats(train_df)
        shrunk = shrink_fracs(frac_by_t, n_by_t, global_frac, k)
        test_tours = gt_df.loc[test_ids, "tournament"]
        preds = test_tours.map(shrunk)
        preds = preds.fillna(global_frac)
        preds = preds.clip(lower=clip[0], upper=clip[1])
        return preds
    return fit_predict


def make_fit_predict_share_baseline(gt_df: pd.DataFrame,
                                     clip: tuple[float, float] = (FRAC_2T_MIN, FRAC_2T_MAX)) -> Callable:
    """Baseline: fracao GLOBAL constante (w=0 sempre -- ignora o torneio),
    tambem fold-safe (computada só com o treino do fold)."""
    def fit_predict(train_ids: np.ndarray, test_ids: np.ndarray) -> pd.Series:
        train_df = gt_df.loc[train_ids]
        total_2t, total_all = _corner_sums(train_df)
        s = float(total_all.sum())
        global_frac = float(total_2t.sum()) / s if s > 0 else 0.5
        global_frac = min(max(global_frac, clip[0]), clip[1])
        return pd.Series(global_frac, index=test_ids)
    return fit_predict


# ============================================================ selecao de k por CV
def select_k_by_cv(gt_df: pd.DataFrame, k_grid: list[float] = K_GRID,
                    n_folds: int = 5, n_seeds: int = 20) -> pd.DataFrame:
    """Grid search de k. Roda o MESMO conjunto de 5x20=100 splits
    (StratifiedKFold por tournament, deterministico por seed) pro baseline e
    pra cada k -- permite comparacao pareada fold-a-fold (frac_folds_better)."""
    baseline_df = grouped_stratified_kfold_repeated(
        gt_df, make_fit_predict_share_baseline(gt_df), n_folds=n_folds, n_seeds=n_seeds)
    baseline_ll = baseline_df["pmf_logloss"].to_numpy()

    rows = []
    for k in k_grid:
        cand_df = grouped_stratified_kfold_repeated(
            gt_df, make_fit_predict_share(gt_df, k), n_folds=n_folds, n_seeds=n_seeds)
        cand_ll = cand_df["pmf_logloss"].to_numpy()
        delta = cand_ll - baseline_ll
        rows.append({
            "k": k,
            "mean_logloss": float(cand_ll.mean()),
            "baseline_mean_logloss": float(baseline_ll.mean()),
            "delta_vs_baseline": float(delta.mean()),
            "frac_folds_better": float((delta < 0).mean()),
        })
    return pd.DataFrame(rows)


# ============================================================ out-of-fold (p/ bootstrap)
def oof_predictions(gt_df: pd.DataFrame, fit_predict_share: Callable,
                     n_folds: int = 5, seed: int = 42) -> pd.Series:
    """Previsoes out-of-fold (uma unica particao k-fold, seed fixa) pra todo
    o dataset -- usadas no bootstrap_delta_ci pareado por partida."""
    fixture_ids = gt_df.index.values
    tournaments = gt_df["tournament"].values
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    parts = []
    for train_idx, test_idx in skf.split(fixture_ids, tournaments):
        train_ids = fixture_ids[train_idx]
        test_ids = fixture_ids[test_idx]
        parts.append(fit_predict_share(train_ids, test_ids))
    return pd.concat(parts).sort_index()


# ============================================================ ajuste final + predicao do universo
def fit_final_tournament_fracs(gt_df: pd.DataFrame, k: float) -> tuple[dict[str, float], float]:
    """Ajuste final na base 'clean' INTEIRA (sem folds) -- usado só pra
    gerar as previsoes de producao, nao pra avaliacao."""
    frac_by_t, n_by_t, global_frac = compute_tournament_stats(gt_df)
    shrunk = shrink_fracs(frac_by_t, n_by_t, global_frac, k)
    shrunk = {t: float(min(max(v, FRAC_2T_MIN), FRAC_2T_MAX)) for t, v in shrunk.items()}
    return shrunk, global_frac


def predict_universe_frac2t(df_features: pd.DataFrame, shrunk_by_t: dict[str, float],
                             global_frac: float) -> np.ndarray:
    """Torneios do universo de producao que NAO tem treino 'clean' (ex.:
    Champions League, Bundesliga) caem no fallback frac_global."""
    preds = df_features["tournament"].map(shrunk_by_t)
    preds = preds.fillna(global_frac)
    preds = preds.clip(lower=FRAC_2T_MIN, upper=FRAC_2T_MAX)
    return preds.to_numpy(dtype=float)


__all__ = [
    "K_GRID", "TARGET_TOURNAMENTS",
    "load_clean_gt", "compute_tournament_stats", "shrink_fracs",
    "make_fit_predict_share", "make_fit_predict_share_baseline",
    "select_k_by_cv", "oof_predictions",
    "fit_final_tournament_fracs", "predict_universe_frac2t",
    "load_feature_universe", "production_corners_distributions",
    "binom_mixture", "pmf_to_string",
    "grouped_stratified_kfold_repeated", "leave_one_tournament_out", "bootstrap_delta_ci",
]
