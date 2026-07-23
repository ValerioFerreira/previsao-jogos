#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/corners_halftime/candidate_a_transfer_glm.py
=============================================================
Candidato A da pesquisa de escanteios por tempo (1T/2T) de clube.

Nao existe rotulo real de escanteio por tempo no dataset (API-Football nao
separa "Corner" por tempo em eventos nem em estatisticas). A abordagem aqui e
"GLM de transferencia heuristica":

  1. Gols e cartoes POR TEMPO sao reais (club_halftime_targets.parquet). A
     fracao de gols/cartoes que cai no 2T e um proxy observavel do "ritmo/
     abertura do jogo no 2T" de cada partida.
  2. Aprende-se uma funcao "features pre-jogo -> fracao no 2T" separadamente
     para gols e para cartoes, via GLM Binomial de fato (LogisticRegression
     ponderada por contagem de eventos — ver nota em _HalfShareGLM sobre por
     que um logit-transform + Ridge ingenuo e enviesado aqui), usando o
     dataset inteiro (todas as competicoes com alvo por tempo disponivel —
     mais dados, funcao mais estavel).
  3. As duas previsoes sao combinadas (media) numa unica "fracao de ritmo 2T"
     e recalibradas por um offset aditivo que ancora a media da previsao num
     prior de literatura (ver LITERATURE_PRIOR_2T_SHARE abaixo).
  4. Essa fracao e usada para partir o TOTAL de escanteios do modelo de
     producao ja validado (corners_cascade_rfixo.joblib, cascata com chutes
     ortogonalizados) em 1T/2T por lado, com uma Binomial Negativa de
     dispersao fixa na metade do jogo.

Nao mexe em model_artifacts_clubes/*.joblib (so LE) nem em predictor.py.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parents[2]  # backend/

# ------------------------------------------------------------------ caminhos
FEATURES_PARQUET = ROOT / "data" / "built" / "club_features_enriched.parquet"
HALFTIME_TARGETS_PARQUET = ROOT / "data" / "built" / "club_halftime_targets.parquet"

ART_DIR = ROOT / "model_artifacts_clubes"
META_PATH = ART_DIR / "meta.json"
SHOTS_MODEL_PATH = ART_DIR / "shots_nb.joblib"
ORTHO_WEIGHTS_PATH = ART_DIR / "style_ortho_weights.joblib"
CORNERS_MODEL_PATH = ART_DIR / "corners_cascade_rfixo.joblib"

ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "candidate_a.joblib"

# --------------------------------------------------------------- universo
TARGET_TOURNAMENTS = [
    "La Liga", "Champions League", "Bundesliga", "Ligue 1",
    "Premier League", "Serie A Italia",
]

# --------------------------------------------------------------- features
# Base pedida na tarefa. As colunas GAP de escanteio (gap_corners_*) sao
# checadas dinamicamente em `available_feature_cols()` — na revisao de
# 2026-07-23 elas NAO existem em club_features_enriched.parquet (o GAP
# ratings de chutes/escanteios so entra como feature EM TEMPO DE INFERENCIA,
# via predictor.py::build_row() a partir de meta["gap_ratings_state"] — nao
# foi materializado como coluna estatica no dataset de treino). Por isso o
# candidato roda so com o restante da lista; ver aviso no relatorio final.
BASE_FEATURE_COLS = [
    "elo_diff", "elo_home_winprob", "real_home_advantage", "neutral",
    "tournament_weight", "is_competitive",
]
OPTIONAL_GAP_CORNER_COLS = [
    "gap_corners_home_att", "gap_corners_home_def",
    "gap_corners_away_att", "gap_corners_away_def",
    "gap_corners_exp_home", "gap_corners_exp_away",
]

# --------------------------------------------------------- prior de literatura
# Busca (WebSearch, 2026-07-23) em footystats/thestatsdontlie/scoreroom/etc.:
# consenso qualitativo consistente de que o 2T tem MAIS escanteios que o 1T
# (jogo mais aberto, times atras pressionando), mas nenhuma fonte retornou um
# numero agregado unico e verificavel (as paginas sao por liga/time, sem um
# "X% do total cai no 2T" consolidado). Assumimos 0.55 (55% no 2T) como prior
# central, moderado e consistente com esse consenso qualitativo — e uma
# suposicao documentada, nao um numero validado externamente. Serve apenas
# para ancorar a MEDIA da fracao prevista pelo GLM; a variacao por jogo vem
# inteiramente do proxy gols/cartoes.
LITERATURE_PRIOR_2T_SHARE = 0.55
FRAC_2T_MIN, FRAC_2T_MAX = 0.35, 0.70

# --------------------------------------------------------- dispersao NB (meio-jogo)
# O cascade de producao usa r_H=10.0/r_A=8.5 para o jogo INTEIRO. Um meio-jogo
# tem media ~metade da contagem e, empiricamente, contagens de Poisson/NB mais
# baixas costumam ter dispersao relativa maior (mais "ruido" perto de zero).
# Escolhemos um r fixo mais baixo, r=8.0, igual para os 4 series (mandante/
# visitante x 1T/2T) — mais conservador (distribuicao um pouco mais espalhada)
# do que simplesmente reusar r_H/r_A do jogo inteiro. Decisao documentada, sem
# MLE (nao ha alvo real pra ajustar isso de verdade).
R_HALF_FIXED = 8.0
MAX_K = 15


def available_feature_cols(df: pd.DataFrame) -> list[str]:
    """Base + colunas GAP de escanteio, so as que existem de fato no df."""
    cols = list(BASE_FEATURE_COLS)
    gap_present = [c for c in OPTIONAL_GAP_CORNER_COLS if c in df.columns]
    cols.extend(gap_present)
    return cols


# ============================================================ GLM Binomial (logit)
class _HalfShareGLM:
    """GLM Binomial de verdade (link logit) pra fracao no 2T, via
    LogisticRegression ponderada por contagem de eventos (imputacao mediana +
    padronizacao, como convencao do resto do repo).

    IMPORTANTE (achado durante o desenvolvimento, tentativa anterior descartada):
    a primeira versao fazia logit(share) por jogo e regredia por Ridge/erro
    quadratico. Isso e ENVIESADO aqui porque a fracao vem de uma contagem
    pequena — ex. total_goals=1 -> share e EXATAMENTE 0 ou 1 (nao ha "meio
    gol"). O logit desses extremos e enorme em magnitude (perto do clip
    numerico) e domina a media em erro-quadratico-em-logit; testado, deu
    media prevista 0.75-0.79 vs a media real das fracoes ~0.56-0.65 — um gap
    grande demais (Jensen: sigmoid(media(logit)) != media(sigmoid(logit))).

    A forma correta de tratar fracao-de-contagem e um GLM Binomial de fato
    (MLE em log-verossimilhanca binomial, nao erro-quadratico em logit). Sem
    statsmodels no ambiente, replica-se isso com sklearn: cada jogo com
    n eventos totais e k no 2T vira 2 observacoes de LogisticRegression —
    (y=1, peso=k) e (y=0, peso=n-k). Maximizar log-verossimilhanca ponderada
    dessa forma e algebricamente identico ao GLM Binomial (peso = replicacao
    de observacoes), e corrige o vies (ver sanity check no runner).
    """

    def __init__(self, feature_cols: list[str], C: float = 1.0):
        self.feature_cols = feature_cols
        self.C = C
        self.pipeline_: Pipeline | None = None

    def fit(self, X: pd.DataFrame, k_2t: np.ndarray, n_total: np.ndarray):
        k = np.asarray(k_2t, dtype=float)
        n = np.asarray(n_total, dtype=float)
        failures = np.maximum(n - k, 0.0)

        X_cols = X[self.feature_cols].reset_index(drop=True)
        X_expanded = pd.concat([X_cols, X_cols], ignore_index=True)
        y_expanded = np.concatenate([np.ones(len(X_cols)), np.zeros(len(X_cols))])
        w_expanded = np.concatenate([k, failures])

        self.pipeline_ = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("logreg", LogisticRegression(C=self.C, max_iter=2000, random_state=42)),
        ])
        self.pipeline_.fit(X_expanded, y_expanded, logreg__sample_weight=w_expanded)
        return self

    def predict_share(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipeline_.predict_proba(X[self.feature_cols])[:, 1]


# ============================================================ modelo do candidato
class CandidateATransferModel:
    """Encapsula os 2 GLMs (gols/cartoes) + calibracao pro prior de literatura."""

    def __init__(self, feature_cols: list[str]):
        self.feature_cols = feature_cols
        self.goals_glm = _HalfShareGLM(feature_cols)
        self.cards_glm = _HalfShareGLM(feature_cols)
        self.calibration_offset_: float = 0.0
        self.train_mean_blend_: float | None = None

    def fit(self, df_train: pd.DataFrame) -> "CandidateATransferModel":
        total_goals = (
            df_train["home_goals_1t"] + df_train["home_goals_2t"]
            + df_train["away_goals_1t"] + df_train["away_goals_2t"]
        )
        goals_2t = df_train["home_goals_2t"] + df_train["away_goals_2t"]
        # jogos 0x0 nao carregam sinal de ritmo real (0 tentativas) — excluidos
        # do FIT do GLM de gols.
        mask_goals = total_goals > 0
        self.goals_glm.fit(
            df_train.loc[mask_goals],
            k_2t=goals_2t.loc[mask_goals].values,
            n_total=total_goals.loc[mask_goals].values,
        )

        total_cards = (
            df_train["home_cards_1t"] + df_train["home_cards_2t"]
            + df_train["away_cards_1t"] + df_train["away_cards_2t"]
        )
        cards_2t = df_train["home_cards_2t"] + df_train["away_cards_2t"]
        mask_cards = (df_train["has_card_events"] == 1) & (total_cards > 0)
        self.cards_glm.fit(
            df_train.loc[mask_cards],
            k_2t=cards_2t.loc[mask_cards].values,
            n_total=total_cards.loc[mask_cards].values,
        )

        # calibracao: ancora a MEDIA da fracao de ritmo (gols+cartoes, todas
        # as linhas com features, independente do mask de alvo) no prior de
        # literatura.
        blended = self._blend(df_train)
        self.train_mean_blend_ = float(np.mean(blended))
        self.calibration_offset_ = LITERATURE_PRIOR_2T_SHARE - self.train_mean_blend_
        return self

    def _blend(self, df: pd.DataFrame) -> np.ndarray:
        g = self.goals_glm.predict_share(df)
        c = self.cards_glm.predict_share(df)
        return (g + c) / 2.0

    def predict_frac_2t(self, df: pd.DataFrame) -> np.ndarray:
        blended = self._blend(df)
        frac = blended + self.calibration_offset_
        return np.clip(frac, FRAC_2T_MIN, FRAC_2T_MAX)

    def save(self, filepath: Path = ARTIFACT_PATH):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: Path = ARTIFACT_PATH) -> "CandidateATransferModel":
        return joblib.load(filepath)


# ============================================================ carga de dados
def load_training_frame() -> pd.DataFrame:
    """Dataset AMPLO (todas as competicoes com alvo por tempo real) — usado
    so pra aprender a funcao 'features -> fracao 2T' via proxy gols/cartoes.
    Mais dados = funcao de transferencia mais estavel."""
    feats = pd.read_parquet(FEATURES_PARQUET)
    ht = pd.read_parquet(HALFTIME_TARGETS_PARQUET)
    df = feats.merge(ht, on="fixture_id", how="inner")
    return df


def load_prediction_universe() -> pd.DataFrame:
    """Universo de previsao: as 6 competicoes-alvo, TODOS os fixtures (com ou
    sem alvo real por tempo — nao precisamos do alvo pra prever)."""
    feats = pd.read_parquet(FEATURES_PARQUET)
    return feats[feats["tournament"].isin(TARGET_TOURNAMENTS)].reset_index(drop=True)


# ================================================ cascata de producao (so leitura)
def production_corners_totals(df: pd.DataFrame) -> dict:
    """Reproduz a cascata de producao (chutes ortogonalizados -> escanteios)
    EXATAMENTE como predictor.py faz na inferencia ao vivo, mas em lote sobre
    um dataframe historico com as features ja materializadas. So LEITURA dos
    artefatos existentes — nenhum modelo e retreinado ou alterado aqui.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from ortho_sinais import apply_ortho_residuals  # noqa: E402
    from corner_interactions import add_corner_interactions  # noqa: E402

    with open(META_PATH, encoding="utf-8") as f:
        json.load(f)  # so pra validar que o meta existe/le em utf-8 (contrato da tarefa)

    ortho_weights = joblib.load(ORTHO_WEIGHTS_PATH)
    shots_model = joblib.load(SHOTS_MODEL_PATH)
    corners_model = joblib.load(CORNERS_MODEL_PATH)

    X_resid = apply_ortho_residuals(df, ortho_weights)
    shots_dist = shots_model.predict_distributions(X_resid)
    X_resid = X_resid.copy()
    X_resid["pred_home_shots"] = shots_dist["lambdas"]
    X_resid["pred_away_shots"] = shots_dist["mus"]

    X_corners = add_corner_interactions(X_resid)
    corners_dist = corners_model.predict_distributions(X_corners)
    return {
        "lambdas_home_total": np.asarray(corners_dist["lambdas"], dtype=float),
        "mus_away_total": np.asarray(corners_dist["mus"], dtype=float),
    }


# ================================================================== PMF NB
def nb_pmf_grid(lambdas: np.ndarray, r: float, max_k: int = MAX_K) -> np.ndarray:
    """PMF Binomial Negativa renormalizada na grade 0..max_k (N, max_k+1).
    Mesma receita de corners_nb_model.py::CornersNB._marginal_pmf, so que numa
    grade menor (meio-jogo tem contagens tipicamente bem abaixo de 15)."""
    lambdas = np.maximum(np.asarray(lambdas, dtype=float), 0.05)
    k = np.arange(max_k + 1)
    p = r / (r + lambdas)
    pmf = nbinom.pmf(k[None, :], n=r, p=p[:, None])
    pmf = pmf / pmf.sum(axis=1, keepdims=True)
    return pmf


def pmf_to_string(pmf_row: np.ndarray) -> str:
    return ",".join(f"{v:.6f}" for v in pmf_row)


def split_lambda_1t_2t(lambda_total: np.ndarray, frac_2t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lam_2t = lambda_total * frac_2t
    lam_1t = lambda_total * (1.0 - frac_2t)
    return lam_1t, lam_2t
