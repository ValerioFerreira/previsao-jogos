#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/gbm_models.py
============================
Candidatos GBM da Linha B: CatBoost/LightGBM/XGBoost multiclasse (H/D/A) sobre
conjuntos de features de RATINGS (pi/Berrar/GAP/Elo) — a combinação SOTA dos
Soccer Prediction Challenges (CatBoost + pi-ratings, RPS 0,1925).

As funções fit_predict_* seguem a interface do protocol.evaluate_result_model:
fit_predict(train_df, test_df) -> probs (n_test, 3) na ordem H/D/A.

IMPORTANTE (point-in-time): as colunas de rating são calculadas UMA vez sobre o
dataset inteiro, mas cada linha usa só o rating PRÉ-jogo — não há vazamento em
usá-las num split temporal (o rating da linha i só depende de jogos < i).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ratings import compute_pi_ratings, compute_berrar_ratings

RESULT_ORDER = ["H", "D", "A"]

PI_FEATS = ["pi_home_h", "pi_home_a", "pi_away_h", "pi_away_a",
            "pi_home_mean", "pi_away_mean", "pi_exp_gd"]
BR_FEATS = ["br_home_off", "br_home_def", "br_away_off", "br_away_def",
            "br_exp_gh", "br_exp_ga"]
ELO_FEATS = ["home_elo_pre", "away_elo_pre", "elo_diff", "elo_home_winprob"]
CTX_FEATS = ["neutral", "is_continental", "is_cup", "is_knockout", "season_progress",
             "home_days_rest", "away_days_rest"]


def add_rating_features(df: pd.DataFrame) -> pd.DataFrame:
    """Anexa pi-ratings e Berrar ratings (pré-jogo) ao dataframe ordenado por data."""
    df = df.sort_values("date").reset_index(drop=True)
    pi = compute_pi_ratings(df)
    br = compute_berrar_ratings(df)
    return pd.concat([df, pi, br], axis=1)


def _make_xy(df: pd.DataFrame, feats: list[str]):
    y = df["result"].map({c: i for i, c in enumerate(RESULT_ORDER)}).to_numpy()
    X = df[feats].to_numpy(dtype=float)
    return X, y


def fit_predict_catboost(train_df, test_df, feats=None, **params):
    from catboost import CatBoostClassifier
    feats = feats or (PI_FEATS + ELO_FEATS)
    X, y = _make_xy(train_df, feats)
    Xt, _ = _make_xy(test_df, feats)
    p = dict(loss_function="MultiClass", iterations=800, depth=6, learning_rate=0.03,
             l2_leaf_reg=3.0, random_seed=42, verbose=0, allow_writing_files=False,
             thread_count=-1)
    p.update(params)
    m = CatBoostClassifier(**p)
    m.fit(X, y)
    return m.predict_proba(Xt)


def fit_predict_lgbm(train_df, test_df, feats=None, **params):
    import lightgbm as lgb
    feats = feats or (PI_FEATS + ELO_FEATS)
    X, y = _make_xy(train_df, feats)
    Xt, _ = _make_xy(test_df, feats)
    p = dict(objective="multiclass", num_class=3, n_estimators=600, num_leaves=31,
             learning_rate=0.03, min_child_samples=50, subsample=0.9,
             colsample_bytree=0.9, random_state=42, n_jobs=-1, verbosity=-1)
    p.update(params)
    m = lgb.LGBMClassifier(**p)
    m.fit(X, y)
    return m.predict_proba(Xt)


def fit_predict_xgb(train_df, test_df, feats=None, **params):
    from xgboost import XGBClassifier
    feats = feats or (PI_FEATS + ELO_FEATS)
    X, y = _make_xy(train_df, feats)
    Xt, _ = _make_xy(test_df, feats)
    p = dict(objective="multi:softprob", num_class=3, n_estimators=600, max_depth=5,
             learning_rate=0.03, subsample=0.9, colsample_bytree=0.9,
             random_state=42, n_jobs=-1, verbosity=0)
    p.update(params)
    m = XGBClassifier(**p)
    m.fit(X, y)
    return m.predict_proba(Xt)


def fit_predict_ordered_logit(train_df, test_df, feats=None):
    """Ordered logit (A < D < H) sobre ratings — baseline da literatura (pi-ratings paper)."""
    from sklearn.linear_model import LogisticRegression
    feats = feats or PI_FEATS
    # mapeia p/ escala ordinal 0=A,1=D,2=H e ajusta dois logits acumulados
    ord_map = {"A": 0, "D": 1, "H": 2}
    y = train_df["result"].map(ord_map).to_numpy()
    X = train_df[feats].to_numpy(dtype=float)
    Xt = test_df[feats].to_numpy(dtype=float)
    # P(y>=1), P(y>=2) com logísticas separadas (aproximação prática do ordered logit)
    p1 = LogisticRegression(max_iter=1000).fit(X, (y >= 1).astype(int)).predict_proba(Xt)[:, 1]
    p2 = LogisticRegression(max_iter=1000).fit(X, (y >= 2).astype(int)).predict_proba(Xt)[:, 1]
    p2 = np.minimum(p1, p2)  # monotonicidade
    pa = 1.0 - p1
    pd_ = p1 - p2
    ph = p2
    probs = np.stack([ph, pd_, pa], axis=1)  # ordem H/D/A
    return np.clip(probs, 1e-9, 1) / np.clip(probs, 1e-9, 1).sum(axis=1, keepdims=True)
