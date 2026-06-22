#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/corners_dynamic_nb.py
=========================
Modelo de contagem de escanteios — Binomial Negativa com Dispersão Dinâmica (GAMLSS-style).
Tanto a média (mu) quanto a dispersão (r) são funções log-lineares das características da partida.
Otimização conjunta via MLE com regularização nas fronteiras de r.
"""
import numpy as np
import pandas as pd
from scipy.stats import nbinom
from scipy.optimize import minimize
from scipy.special import gammaln
import joblib


class DynamicCornersNB:
    """NB de contagem de escanteios com média (mu) e dispersão (r) dinâmicas."""

    def __init__(self, max_corners=25, init_r_home=10.0, init_r_away=8.5):
        self.max_corners = max_corners
        self.init_r_home = init_r_home
        self.init_r_away = init_r_away
        
        # Coeficientes dos modelos
        self.beta_home_ = None   # pesos da média (home)
        self.gamma_home_ = None  # pesos da dispersão (home)
        self.beta_away_ = None   # pesos da média (away)
        self.gamma_away_ = None  # pesos da dispersão (away)

    def _build_design_matrices(self, df, side="home"):
        """Constrói as matrizes de design X (média) e Z (dispersão)."""
        N = len(df)
        intercept = np.ones(N)
        
        # Elo diff relativo ao mando
        he = df["home_elo_pre"].fillna(1500.0).values
        ae = df["away_elo_pre"].fillna(1500.0).values
        elo_diff = (he - ae) if side == "home" else (ae - he)
        
        # Expectativa de chutes (sinal de intensidade ofensiva em cascata)
        pred_shots = df["pred_home_shots"].fillna(10.0).values if side == "home" else df["pred_away_shots"].fillna(10.0).values
        
        # Features residuais de estilo (mando correspondente)
        styles = [
            f"resid_{side}_style_crosses_l5",
            f"resid_{side}_style_crosses_l10",
            f"resid_{side}_style_ppda_l5",
            f"resid_{side}_style_ppda_l10",
            f"resid_{side}_style_fouls_suff_ratio_l5",
            f"resid_{side}_style_fouls_suff_ratio_l10"
        ]
        
        X_cols = [intercept, elo_diff / 100.0, pred_shots]  # Elo_diff scaled for optimization stability
        for s in styles:
            X_cols.append(df[s].fillna(0.0).values)
            
        X_mat = np.column_stack(X_cols)
        
        # Z matrix (volatilidade): intercept, pred_total_shots / 10.0, abs_elo_diff / 100.0
        pred_total_shots = (df["pred_home_shots"] + df["pred_away_shots"]).fillna(20.0).values / 10.0
        abs_elo_diff = np.abs(he - ae) / 100.0  # scaled
        
        Z_mat = np.column_stack([intercept, pred_total_shots, abs_elo_diff])
        
        return X_mat, Z_mat

    @staticmethod
    def _nloglike(params, X, Z, y):
        """Função de custo Negative Log-Likelihood baseada em gammaln."""
        K_X = X.shape[1]
        beta = params[:K_X]
        gamma = params[K_X:]
        
        # Log-linear links with numerical safety clips
        mu = np.exp(np.clip(np.dot(X, beta), -20.0, 20.0))
        r = np.exp(np.clip(np.dot(Z, gamma), -10.0, 10.0))
        
        # Penalidade suave para manter r no intervalo [1.5, 50.0]
        penalty = 0.0
        r_under = r < 1.5
        r_over = r > 50.0
        if np.any(r_under):
            penalty += 1e6 * np.sum((1.5 - r[r_under])**2)
        if np.any(r_over):
            penalty += 1e6 * np.sum((r[r_over] - 50.0)**2)
            
        # Clips de segurança numérica
        mu = np.clip(mu, 1e-3, 100.0)
        r = np.clip(r, 1.5, 50.0)
        
        # NB Type II Log-PMF usando gammaln (evita overflow)
        log_pmf = (gammaln(y + r) - gammaln(y + 1) - gammaln(r)
                   + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
        
        return -np.sum(log_pmf) + penalty

    def _fit_side(self, df, y_vals, side="home", init_r=10.0):
        """Treina os parâmetros beta e gamma via MLE para um lado usando inicialização em dois passos."""
        X_mat, Z_mat = self._build_design_matrices(df, side=side)
        
        # --- PASSO 1: Otimizar beta mantendo r constante ---
        def nloglike_beta(beta_params):
            mu = np.exp(np.clip(np.dot(X_mat, beta_params), -20.0, 20.0))
            mu = np.clip(mu, 1e-3, 100.0)
            log_pmf = (gammaln(y_vals + init_r) - gammaln(y_vals + 1) - gammaln(init_r)
                       + init_r * np.log(init_r / (init_r + mu)) + y_vals * np.log(mu / (init_r + mu)))
            return -np.sum(log_pmf)

        from sklearn.linear_model import Ridge
        y_log = np.log(y_vals + 1.0)
        ridge = Ridge(alpha=1.0, fit_intercept=False)
        ridge.fit(X_mat, y_log)
        beta_init_guess = ridge.coef_
        
        res_beta = minimize(nloglike_beta, beta_init_guess, method="L-BFGS-B")
        beta_init = res_beta.x if res_beta.success else beta_init_guess
        
        # --- PASSO 2: Otimizar gamma mantendo beta fixo ---
        mu_fixed = np.clip(np.exp(np.clip(np.dot(X_mat, beta_init), -20.0, 20.0)), 1e-3, 100.0)
        
        def nloglike_gamma(gamma_params):
            r = np.exp(np.clip(np.dot(Z_mat, gamma_params), -10.0, 10.0))
            penalty = 0.0
            r_under = r < 1.5
            r_over = r > 50.0
            if np.any(r_under):
                penalty += 1e6 * np.sum((1.5 - r[r_under])**2)
            if np.any(r_over):
                penalty += 1e6 * np.sum((r[r_over] - 50.0)**2)
            r = np.clip(r, 1.5, 50.0)
            log_pmf = (gammaln(y_vals + r) - gammaln(y_vals + 1) - gammaln(r)
                       + r * np.log(r / (r + mu_fixed)) + y_vals * np.log(mu_fixed / (r + mu_fixed)))
            return -np.sum(log_pmf) + penalty

        gamma_init_guess = np.zeros(Z_mat.shape[1])
        gamma_init_guess[0] = np.log(init_r)
        
        res_gamma = minimize(nloglike_gamma, gamma_init_guess, method="L-BFGS-B")
        gamma_init = res_gamma.x if res_gamma.success else gamma_init_guess
        
        # --- PASSO 3: Otimização conjunta ---
        params_init = np.concatenate([beta_init, gamma_init])
        
        res = minimize(self._nloglike, params_init, args=(X_mat, Z_mat, y_vals),
                       method="L-BFGS-B", options={"maxiter": 600})
        
        if not res.success:
            res = minimize(self._nloglike, params_init, args=(X_mat, Z_mat, y_vals),
                           method="Nelder-Mead", options={"maxiter": 1000})
            
        K_X = X_mat.shape[1]
        beta = res.x[:K_X]
        gamma = res.x[K_X:]
        
        return beta, gamma

    def fit(self, df, y_home, y_away):
        """Ajusta beta e gamma conjuntamente para mandante e visitante."""
        y_h = np.asarray(y_home, dtype=float)
        y_a = np.asarray(y_away, dtype=float)
        
        valid = ~np.isnan(y_h) & ~np.isnan(y_a)
        df_clean = df.iloc[valid]
        y_h_clean = y_h[valid]
        y_a_clean = y_a[valid]
        
        print("Treinando DynamicCornersNB Mandante...")
        self.beta_home_, self.gamma_home_ = self._fit_side(
            df_clean, y_h_clean, side="home", init_r=self.init_r_home
        )
        
        print("Treinando DynamicCornersNB Visitante...")
        self.beta_away_, self.gamma_away_ = self._fit_side(
            df_clean, y_a_clean, side="away", init_r=self.init_r_away
        )
        return self

    def predict_distributions(self, df):
        """Gera as distribuições marginais (home/away) e total via convolução."""
        X_h, Z_h = self._build_design_matrices(df, side="home")
        X_a, Z_a = self._build_design_matrices(df, side="away")
        
        # Cálculo de mu e r por jogo com safety clips
        mu_h = np.clip(np.exp(np.clip(np.dot(X_h, self.beta_home_), -20.0, 20.0)), 1e-3, 100.0)
        r_h = np.clip(np.exp(np.clip(np.dot(Z_h, self.gamma_home_), -10.0, 10.0)), 1.5, 50.0)
        
        mu_a = np.clip(np.exp(np.clip(np.dot(X_a, self.beta_away_), -20.0, 20.0)), 1e-3, 100.0)
        r_a = np.clip(np.exp(np.clip(np.dot(Z_a, self.gamma_away_), -10.0, 10.0)), 1.5, 50.0)
        
        N = len(df)
        prob_h = np.zeros((N, self.max_corners + 1))
        prob_a = np.zeros((N, self.max_corners + 1))
        prob_t = np.zeros((N, 2 * self.max_corners + 1))
        
        k_arr = np.arange(self.max_corners + 1)
        
        for i in range(N):
            p_h = r_h[i] / (r_h[i] + mu_h[i])
            p_a = r_a[i] / (r_a[i] + mu_a[i])
            
            prob_h[i] = nbinom.pmf(k_arr, n=r_h[i], p=p_h)
            prob_a[i] = nbinom.pmf(k_arr, n=r_a[i], p=p_a)
            
            # Normalização das marginais
            prob_h[i] /= prob_h[i].sum()
            prob_a[i] /= prob_a[i].sum()
            
            prob_t[i] = np.convolve(prob_h[i], prob_a[i])
            
        return {
            "home": prob_h,
            "away": prob_a,
            "total": prob_t,
            "lambdas": mu_h,
            "mus": mu_a,
            "r_home": r_h,
            "r_away": r_a
        }

    def save(self, filepath):
        joblib.dump(self, filepath)
        print(f"Modelo DynamicCornersNB salvo em: {filepath}")

    @classmethod
    def load(cls, filepath):
        return joblib.load(filepath)
