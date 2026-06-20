#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/dixon_coles_model.py
============================
Classe customizada para o modelo Dixon-Coles Binomial Negativo (DC-NB).
Unifica a modelagem conjunta de gols do mandante e do visitante.
"""

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.optimize import minimize
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
import joblib

class DixonColesNBRegressor(BaseEstimator, RegressorMixin):
    """
    Modelo de regressão Dixon-Coles com distribuição Binomial Negativa (DC-NB)
    para gols de mandante e visitante.
    """
    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12, random_state=42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_goals = max_goals
        self.random_state = random_state
        
        # Parâmetros otimizados via MLE
        self.r_H_ = 4.0      # Parâmetro de dispersão home (default inicial)
        self.r_A_ = 4.0      # Parâmetro de dispersão away (default inicial)
        self.rho_ = 0.0      # Parâmetro de acoplamento Dixon-Coles
        
        # Regressores base de expectativas de gols (lambdas/mus)
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
                random_state=self.random_state
            ))
        ])

    def fit(self, X, y_home, y_away):
        """
        Treina o modelo:
          1. Ajusta os regressores base para obter lambdas e mus esperados.
          2. Estima r_H, r_A e rho maximizando a verossimilhança no treino.
        """
        # Garantir conversão para numpy
        X_df = pd.DataFrame(X)
        y_h = np.array(y_home, dtype=float)
        y_a = np.array(y_away, dtype=float)
        
        # Filtrar amostras válidas (sem NaNs)
        valid = ~np.isnan(y_h) & ~np.isnan(y_a)
        X_clean = X_df.iloc[valid]
        y_h_clean = y_h[valid]
        y_a_clean = y_a[valid]
        
        print(f"Treinando regressores de expectativa de gols (N={len(X_clean)})...")
        self.model_home_ = self._create_base_regressor()
        self.model_away_ = self._create_base_regressor()
        
        self.model_home_.fit(X_clean, y_h_clean)
        self.model_away_.fit(X_clean, y_a_clean)
        
        # Predições de lambdas e mus no conjunto de treino
        lambdas = self.model_home_.predict(X_clean)
        mus = self.model_away_.predict(X_clean)
        
        # Evitar valores não-positivos de expectativas de gols
        lambdas = np.maximum(lambdas, 1e-4)
        mus = np.maximum(mus, 1e-4)
        
        # Estimar parâmetros globais (r_H, r_A, rho) via MLE
        print("Ajustando parâmetros de dispersão e correlação (r_H, r_A, rho) via MLE...")
        
        # Função objetivo: Negative Log-Likelihood
        def objective(params):
            r_H, r_A, rho = params
            
            # Restrições de borda explícitas no cálculo do NLL
            if r_H <= 0.01 or r_A <= 0.01:
                return 1e10
                
            nll = self._calculate_nll(y_h_clean, y_a_clean, lambdas, mus, r_H, r_A, rho)
            return nll

        # Chute inicial e limites
        # rho restrito para evitar probabilidades unnormalized negativas
        initial_guess = [4.0, 4.0, 0.0]
        bounds = [(0.1, 1000.0), (0.1, 1000.0), (-0.25, 0.25)]
        
        res = minimize(objective, initial_guess, method="L-BFGS-B", bounds=bounds)
        
        if res.success:
            self.r_H_, self.r_A_, self.rho_ = res.x
            print(f"MLE convergiu com sucesso:")
            print(f"  - r_H (dispersão mandante): {self.r_H_:.4f}")
            print(f"  - r_A (dispersão visitante): {self.r_A_:.4f}")
            print(f"  - rho (correlação DC): {self.rho_:.4f}")
        else:
            print("[AVISO] Otimização MLE não convergiu. Usando valores default.")
            self.r_H_, self.r_A_, self.rho_ = 4.0, 4.0, 0.0
            
        return self

    def _calculate_nll(self, y_h, y_a, lambdas, mus, r_H, r_A, rho):
        """
        Calcula o NLL em lote vetorizado para todos os jogos.
        """
        N = len(y_h)
        M = self.max_goals
        k = np.arange(M + 1)
        
        # Probabilidades marginais de gols
        # shape: (N, M + 1)
        p_H = r_H / (r_H + lambdas)
        prob_H = nbinom.pmf(k[None, :], n=r_H, p=p_H[:, None])
        
        p_A = r_A / (r_A + mus)
        prob_A = nbinom.pmf(k[None, :], n=r_A, p=p_A[:, None])
        
        # Produto independente joint
        # shape: (N, M + 1, M + 1)
        P_joint = prob_H[:, :, None] * prob_A[:, None, :]
        
        # Fator de correção de Dixon-Coles
        tau = np.ones((N, M + 1, M + 1))
        tau[:, 0, 0] = 1 - lambdas * mus * rho
        tau[:, 0, 1] = 1 + lambdas * rho
        tau[:, 1, 0] = 1 + mus * rho
        tau[:, 1, 1] = 1 - rho
        
        # Aplicar correção e garantir não-negatividade
        P_joint_corr = np.maximum(P_joint * tau, 0.0)
        
        # Renormalização para somar exatamente 1.0 por partida
        sums = P_joint_corr.sum(axis=(1, 2), keepdims=True)
        sums[sums == 0] = 1e-15  # evitar divisão por zero
        P_joint_norm = P_joint_corr / sums
        
        # Obter probabilidade dos placares reais
        # Limitar placares observados ao valor máximo de M
        y_h_clipped = np.clip(y_h, 0, M).astype(int)
        y_a_clipped = np.clip(y_a, 0, M).astype(int)
        
        prob_obs = P_joint_norm[np.arange(N), y_h_clipped, y_a_clipped]
        
        # NLL
        nll = -np.log(prob_obs + 1e-15).sum()
        return nll

    def predict_joint_distribution(self, X):
        """
        Gera a matriz unificada conjunta renormalizada para cada linha de X.
        Retorna um tensor numpy de shape (N, M + 1, M + 1).
        """
        N = len(X)
        M = self.max_goals
        k = np.arange(M + 1)
        
        lambdas = self.model_home_.predict(X)
        mus = self.model_away_.predict(X)
        
        # Evitar não-positivos
        lambdas = np.maximum(lambdas, 1e-4)
        mus = np.maximum(mus, 1e-4)
        
        p_H = self.r_H_ / (self.r_H_ + lambdas)
        prob_H = nbinom.pmf(k[None, :], n=self.r_H_, p=p_H[:, None])
        
        p_A = self.r_A_ / (self.r_A_ + mus)
        prob_A = nbinom.pmf(k[None, :], n=self.r_A_, p=p_A[:, None])
        
        P_joint = prob_H[:, :, None] * prob_A[:, None, :]
        
        tau = np.ones((N, M + 1, M + 1))
        tau[:, 0, 0] = 1 - lambdas * mus * self.rho_
        tau[:, 0, 1] = 1 + lambdas * self.rho_
        tau[:, 1, 0] = 1 + mus * self.rho_
        tau[:, 1, 1] = 1 - self.rho_
        
        P_joint_corr = np.maximum(P_joint * tau, 0.0)
        sums = P_joint_corr.sum(axis=(1, 2), keepdims=True)
        sums[sums == 0] = 1e-15
        
        return P_joint_corr / sums

    def predict_proba_markets(self, X):
        """
        Deriva as probabilidades dos mercados a partir da matriz conjunta.
        Retorna um dicionário contendo arrays de probabilidade para cada alvo:
          - 'result': shape (N, 3) correspondente a [A, D, H] (Out-of-home/Draw/Home)
          - 'btts': shape (N,) correspondente à probabilidade de BTTS-Sim
          - 'over_2_5': shape (N,) correspondente à probabilidade de Over 2.5
        """
        P_joint = self.predict_joint_distribution(X)
        N = len(X)
        M = self.max_goals
        
        x_indices = np.arange(M + 1)
        y_indices = np.arange(M + 1)
        
        # Matriz de índices para condições
        X_grid, Y_grid = np.meshgrid(x_indices, y_indices, indexing='ij')
        
        # 1. Resultado de partida (H, D, A)
        # Atenção: as classes na API original e classificadores são ordenadas como ['A', 'D', 'H']
        p_home = P_joint[:, X_grid > Y_grid].sum(axis=1)
        p_draw = P_joint[:, X_grid == Y_grid].sum(axis=1)
        p_away = P_joint[:, X_grid < Y_grid].sum(axis=1)
        
        # Empilhar no formato de saída [A, D, H] compatível com as classes ordinais
        prob_result = np.column_stack([p_away, p_draw, p_home])
        
        # 2. BTTS
        prob_btts = P_joint[:, (X_grid >= 1) & (Y_grid >= 1)].sum(axis=1)
        
        # 3. Over 2.5
        prob_over = P_joint[:, (X_grid + Y_grid) >= 3].sum(axis=1)
        
        return {
            "result": prob_result,
            "btts": prob_btts,
            "over_2_5": prob_over,
            "joint": P_joint
        }
        
    def save(self, filepath):
        joblib.dump(self, filepath)
        print(f"Modelo Dixon-Coles salvo em: {filepath}")
        
    @classmethod
    def load(cls, filepath):
        return joblib.load(filepath)
