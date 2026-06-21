#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/corners_nb_model.py
=======================
Modelo de contagem de escanteios — Binomial Negativa INDEPENDENTE (Abordagem A).

Receita idêntica à validada em scripts/compare_corners.py (Passo 2):
  - lambda de cada lado via GradientBoostingRegressor (squared_error).
  - parâmetro de dispersão r estimado por MLE, independentemente por lado.
  - distribuição de cada lado via nbinom.pmf; total por convolução (independência).

A correlação entre lados é fraca (beta~-0.04); o acoplamento foi aposentado
para escanteios (ver comparacao_escanteios.md). Aqui é só a Abordagem A.
"""

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.optimize import minimize
from sklearn.base import BaseEstimator
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
import joblib


class CornersNB(BaseEstimator):
    """Binomial Negativa independente para escanteios (mandante, visitante, total)."""

    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05,
                 max_corners=25, random_state=42, feats=None):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_corners = max_corners
        self.random_state = random_state
        self.feats = feats              # lista de colunas (meta["full_feats"])

        # Parâmetros de dispersão estimados por MLE
        self.r_H_ = 5.0
        self.r_A_ = 5.0

        # Regressores de expectativa (lambda mandante / mu visitante)
        self.model_home_ = None
        self.model_away_ = None

    def _create_base_regressor(self):
        return Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(
                loss="squared_error",
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=self.learning_rate,
                random_state=self.random_state,
            )),
        ])

    @staticmethod
    def _optimize_r(y_vals, lam_vals):
        """MLE do parâmetro de dispersão r (idêntico a compare_corners.optimize_r)."""
        def obj(r):
            if r <= 0.05:
                return 1e10
            p = r / (r + lam_vals)
            return -np.sum(np.log(nbinom.pmf(y_vals, n=r, p=p) + 1e-15))
        res = minimize(obj, [5.0], bounds=[(0.1, 1000.0)], method="L-BFGS-B")
        return float(res.x[0])

    def fit(self, X, y_home, y_away, sample_weight=None):
        """sample_weight (opcional): peso por amostra para os regressores de lambda
        (ex.: time decay). Default None = sem peso (comportamento inalterado). O r de
        dispersão é estimado sem peso (dispersão não é a alavanca do peso temporal)."""
        X_df = pd.DataFrame(X)
        y_h = np.asarray(y_home, dtype=float)
        y_a = np.asarray(y_away, dtype=float)

        valid = ~np.isnan(y_h) & ~np.isnan(y_a)
        X_clean = X_df.iloc[valid]
        y_h_clean = y_h[valid]
        y_a_clean = y_a[valid]
        sw = np.asarray(sample_weight, dtype=float)[valid] if sample_weight is not None else None

        print(f"Treinando regressores de expectativa de contagem (N={len(X_clean)})...")
        self.model_home_ = self._create_base_regressor()
        self.model_away_ = self._create_base_regressor()
        self.model_home_.fit(X_clean, y_h_clean, reg__sample_weight=sw)
        self.model_away_.fit(X_clean, y_a_clean, reg__sample_weight=sw)

        lambdas = np.maximum(self.model_home_.predict(X_clean), 0.1)
        mus = np.maximum(self.model_away_.predict(X_clean), 0.1)

        print("Estimando dispersão (r_H, r_A) por MLE independente...")
        self.r_H_ = self._optimize_r(y_h_clean, lambdas)
        self.r_A_ = self._optimize_r(y_a_clean, mus)
        print(f"  - r_H (dispersão mandante): {self.r_H_:.4f}")
        print(f"  - r_A (dispersão visitante): {self.r_A_:.4f}")
        return self

    # ------------------------------------------------------------------ predição
    def _marginal_pmf(self, lambdas, r):
        """PMF Binomial Negativa renormalizada na grade 0..max_corners. shape (N, M+1)."""
        M = self.max_corners
        k = np.arange(M + 1)
        p = r / (r + lambdas)
        pmf = nbinom.pmf(k[None, :], n=r, p=p[:, None])   # (N, M+1)
        pmf = pmf / pmf.sum(axis=1, keepdims=True)
        return pmf

    def predict_distributions(self, X):
        """
        Retorna dict com as distribuições de contagem:
          - 'home':  (N, M+1)   PMF do mandante
          - 'away':  (N, M+1)   PMF do visitante
          - 'total': (N, 2M+1)  PMF do total (convolução, independência)
          - 'lambdas', 'mus': expectativas pontuais de cada lado
        """
        if self.feats is not None:
            X = pd.DataFrame(X)[self.feats]
        lambdas = np.maximum(self.model_home_.predict(X), 0.1)
        mus = np.maximum(self.model_away_.predict(X), 0.1)

        prob_h = self._marginal_pmf(lambdas, self.r_H_)
        prob_a = self._marginal_pmf(mus, self.r_A_)

        N = len(prob_h)
        prob_t = np.zeros((N, 2 * self.max_corners + 1))
        for i in range(N):
            prob_t[i] = np.convolve(prob_h[i], prob_a[i])

        return {"home": prob_h, "away": prob_a, "total": prob_t,
                "lambdas": lambdas, "mus": mus}

    def save(self, filepath):
        joblib.dump(self, filepath)
        print(f"Modelo {type(self).__name__} salvo em: {filepath}")

    @classmethod
    def load(cls, filepath):
        return joblib.load(filepath)
