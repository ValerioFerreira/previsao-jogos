#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/candidate_d_supervised_glm.py
=================================================================
Candidato D da pesquisa de escanteios por tempo (1T/2T) de clube.

Diferenca central em relacao aos candidatos A/B/C: aqueles usavam PROXIES
(gols/cartoes por tempo, ou heuristicas de hazard/GBM) porque nao havia rotulo
real de escanteio por tempo no dataset de producao (API-Football nao separa
"Corner" por tempo). O Candidato D e treinado DIRETO no rotulo REAL, coletado
via StatsBomb Open Data (`data/external/corners_halftime_eval_frame.parquet`,
subconjunto `sample_type=="clean"`, N=1516 antes de excluir a linha invalida
-- ver `load_clean_frame()`).

E um GLM Binomial supervisionado (mesma classe `_HalfShareGLM` de
`candidate_a_transfer_glm.py`: LogisticRegression ponderada por contagem de
eventos, pipeline SimpleImputer(mediana)+StandardScaler) regularizado via `C`
escolhido por CV aninhada (nested CV) -- a diferenca do Candidato A e que aqui
o alvo do fit e `k_2t/n_total` de ESCANTEIOS REAIS (nao gols/cartoes como
proxy de ritmo).

Dado o N pequeno (~1515) e a baixa profundidade temporal (4 torneios, quase
todos temporada 2015/16 -- ver auditoria em
`scripts/adhoc_corners_halftime_audit_gt.py`), a avaliacao usa k-fold
ESTRATIFICADO POR TORNEIO repetido (NAO split temporal -- nao ha profundidade
temporal real pra validar isso de forma confiavel) via
`eval_halftime_smallN.grouped_stratified_kfold_repeated`, mais
leave-one-tournament-out e um IC bootstrap do delta de log-loss vs. o
baseline empirico (fracao constante `k_2t.sum()/n_total.sum()` recalculada em
cada fold de treino, sem vazamento).

CRITERIO DE DECISAO PRE-REGISTRADO (escrito ANTES de rodar qualquer avaliacao
-- ver `scripts/adhoc_corners_halftime_candidate_d_train.py` para a execucao):

    "Sinal defensavel" so se, SIMULTANEAMENTE:
      (a) IC bootstrap 95% (1000 reamostragens, pareado por partida,
          out-of-fold) do delta de log-loss (candidato - baseline empirico)
          NAO cruza zero -- upper bound (`ci_hi`) < 0, i.e. candidato
          consistentemente melhor;
      (b) candidato melhora (delta<0) em >=60% dos (seed,fold) do k-fold
          repetido (5 folds x 20 seeds = 100 comparacoes pareadas);
      (c) leave-one-tournament-out NAO inverte o sinal: candidato nao pode
          ter pmf_logloss maior ou igual ao baseline em NENHUM dos 4
          torneios retidos (La Liga / Serie A Italia / Premier League /
          Ligue 1 -- Indian Super League nao tem linhas `clean`).

    Se qualquer criterio falhar -> veredito "sem sinal defensavel",
    documentado como resultado valido da pesquisa (nao e um bug).

Nao mexe em model_artifacts_clubes/*.joblib nem em predictor.py (so LE, via
`production_corners_totals`/`load_prediction_universe` importados de
candidate_a_transfer_glm). Nao mexe em candidate_a/b/c nem em
eval_halftime_smallN -- so importa deles.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", category=FutureWarning)

from research_clubs.corners_halftime.candidate_a_transfer_glm import (  # noqa: E402
    _HalfShareGLM,
    TARGET_TOURNAMENTS,
    BASE_FEATURE_COLS,
    load_prediction_universe,
    production_corners_totals,
    split_lambda_1t_2t,
    pmf_to_string,
)
from research_clubs.corners_halftime.eval_halftime_smallN import (  # noqa: E402
    binom_mixture_pmf,
    build_pmfs_for_matches,
    score_pmfs,
    grouped_stratified_kfold_repeated,
    leave_one_tournament_out,
    bootstrap_delta_ci,
)

# --------------------------------------------------------------- caminhos/consts
EVAL_FRAME_PATH = ROOT / "data" / "external" / "corners_halftime_eval_frame.parquet"

FEATURE_COLS = list(BASE_FEATURE_COLS)
C_GRID = [0.001, 0.01, 0.1, 1.0]
R_TOTAL = 8.5

# Faixa de clipe da fracao prevista de 2T. Aplicada SEMPRE dentro de
# `CandidateDSupervisedGLM.predict_share` (CV, nested selection e previsao
# final usam o mesmo metodo) -- nao so na previsao final. Motivo: sem clip,
# uma previsao extrema (frac perto de 0/1) pode zerar numericamente a
# probabilidade Binomial do valor observado e blindar o eps=1e-12 de
# `pmf_logloss`, gerando um outlier de log-loss (~27.6) que domina a media de
# um fold inteiro -- o mesmo padrao que o Candidato A ja usa (clip dentro do
# unico metodo de predicao, nunca uma chamada "crua").
FRAC_2T_MIN, FRAC_2T_MAX = 0.30, 0.75


# ============================================================ dados (rotulo real)
def load_clean_frame() -> pd.DataFrame:
    """Le o eval frame (StatsBomb), filtra sample_type=='clean', deriva
    k_2t/n_total (rotulo REAL de escanteio por tempo) e exclui linhas com
    n_total==0 (divisao por zero em frac_2t = k_2t/n_total; confirmado 1 linha
    -- fixture_id=185804, Ligue 1 -- logada explicitamente abaixo)."""
    df = pd.read_parquet(EVAL_FRAME_PATH)
    df = df[df["sample_type"] == "clean"].copy()

    df["k_2t"] = df["home_corners_2t"] + df["away_corners_2t"]
    df["n_total"] = (
        df["home_corners_1t"] + df["home_corners_2t"]
        + df["away_corners_1t"] + df["away_corners_2t"]
    )

    zero_mask = df["n_total"] == 0
    n_zero = int(zero_mask.sum())
    if n_zero > 0:
        zero_ids = df.index[zero_mask].tolist()
        print(f"  [load_clean_frame] excluindo {n_zero} linha(s) com n_total==0: "
              f"fixture_id={zero_ids}")
        df = df.loc[~zero_mask].copy()

    keep_cols = [
        "tournament", "k_2t", "n_total",
        "home_corners_1t", "home_corners_2t", "away_corners_1t", "away_corners_2t",
        "home_total_lambda", "away_total_lambda",
    ] + FEATURE_COLS
    df = df[keep_cols]
    df.index.name = "fixture_id"
    return df


def empirical_baseline_share(train_df: pd.DataFrame) -> float:
    """Baseline empirico ponderado: fracao agregada de escanteios no 2T,
    k_2t.sum()/n_total.sum() -- NAO a media simples das fracoes por-jogo
    (que pesaria jogos com poucos escanteios igual a jogos com muitos)."""
    return float(train_df["k_2t"].sum() / train_df["n_total"].sum())


def baseline_fit_predict_share(gt_df: pd.DataFrame):
    """Factory de fit_predict_share(train_ids, test_ids) -> pd.Series pro
    baseline: constante recalculada a partir de train_ids (sem vazamento),
    repetida para todo test_ids."""

    def _fit_predict(train_ids, test_ids) -> pd.Series:
        share = empirical_baseline_share(gt_df.loc[train_ids])
        return pd.Series(share, index=test_ids, name="frac_2t")

    return _fit_predict


# ============================================================ modelo do candidato
class CandidateDSupervisedGLM:
    """Wrapper fino sobre `_HalfShareGLM`, treinado no rotulo REAL de
    escanteio por tempo (k_2t/n_total), nao num proxy. O clip de
    [FRAC_2T_MIN, FRAC_2T_MAX] mora aqui dentro -- ver nota no topo do
    modulo."""

    def __init__(self, feature_cols: list[str] = FEATURE_COLS, C: float = 1.0):
        self.feature_cols = feature_cols
        self.C = C
        self.glm_ = _HalfShareGLM(feature_cols, C=C)

    def fit(self, df_train: pd.DataFrame) -> "CandidateDSupervisedGLM":
        self.glm_.fit(
            df_train,
            k_2t=df_train["k_2t"].values,
            n_total=df_train["n_total"].values,
        )
        return self

    def predict_share(self, df: pd.DataFrame) -> np.ndarray:
        raw = self.glm_.predict_share(df)
        return np.clip(raw, FRAC_2T_MIN, FRAC_2T_MAX)


# ============================================================ selecao de C (nested CV)
def select_C_nested(
    train_df: pd.DataFrame,
    c_grid: list[float] = C_GRID,
    n_inner_folds: int = 5,
    n_inner_seeds: int = 3,
) -> tuple[float, pd.DataFrame]:
    """CV aninhada: pra cada C do grid, roda k-fold estratificado-por-torneio
    repetido DENTRO de train_df (nunca ve o fold de teste externo). Escolhe o
    C de menor pmf_logloss medio; empate -> menor C (mais regularizado)."""
    rows = []
    for C in c_grid:
        def _fit_predict(train_ids, test_ids, C=C):
            model = CandidateDSupervisedGLM(FEATURE_COLS, C=C).fit(train_df.loc[train_ids])
            frac = model.predict_share(train_df.loc[test_ids])
            return pd.Series(frac, index=test_ids, name="frac_2t")

        res = grouped_stratified_kfold_repeated(
            train_df, _fit_predict, n_folds=n_inner_folds, n_seeds=n_inner_seeds
        )
        rows.append({"C": C, "mean_pmf_logloss": float(res["pmf_logloss"].mean())})

    diag = pd.DataFrame(rows).sort_values(["mean_pmf_logloss", "C"], ascending=[True, True])
    best_C = float(diag.iloc[0]["C"])
    return best_C, diag


def make_candidate_fit_predict_share(
    gt_df: pd.DataFrame,
    c_grid: list[float] = C_GRID,
    inner_folds: int = 5,
    inner_seeds: int = 3,
):
    """Factory usada como fit_predict_share no loop EXTERNO (outer). Dentro
    dela, seleciona C via nested CV usando SO o train_ids externo -- o
    test_ids externo nunca entra na selecao de C nem no fit final."""

    def _fit_predict(train_ids, test_ids) -> pd.Series:
        train_df = gt_df.loc[train_ids]
        best_C, _diag = select_C_nested(train_df, c_grid, inner_folds, inner_seeds)
        model = CandidateDSupervisedGLM(FEATURE_COLS, C=best_C).fit(train_df)
        frac = model.predict_share(gt_df.loc[test_ids])
        return pd.Series(frac, index=test_ids, name="frac_2t")

    return _fit_predict


def fit_final_model(
    gt_df_full: pd.DataFrame,
    c_grid: list[float] = C_GRID,
    inner_folds: int = 5,
    inner_seeds: int = 20,
) -> tuple[CandidateDSupervisedGLM, float, pd.DataFrame]:
    """Selecao final de C via nested CV no `clean` inteiro (mais seeds pra
    robustez do C escolhido) -> refit em TODAS as linhas validas."""
    best_C, diag = select_C_nested(gt_df_full, c_grid, inner_folds, inner_seeds)
    model = CandidateDSupervisedGLM(FEATURE_COLS, C=best_C).fit(gt_df_full)
    return model, best_C, diag
