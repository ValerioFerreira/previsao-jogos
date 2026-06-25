import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.base import BaseEstimator
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
import joblib

class CardsGP(BaseEstimator):
    """Modelo de contagem de cartões utilizando a distribuição de Poisson Generalizada (GP)."""

    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05,
                 max_corners=15, random_state=42, feats=None):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_corners = max_corners
        self.random_state = random_state
        self.feats = feats

        # Parâmetros de dispersão GP (lambda_GP) estimados por MLE
        self.gp_lambda_H_ = 0.0
        self.gp_lambda_A_ = 0.0

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
    def _optimize_gp_lambda(y_vals, mu_vals):
        """MLE for Generalized Poisson dispersion parameter lambda_GP."""
        import scipy.special as sp
        
        def obj(lam):
            lam = lam[0]
            # Strict bounds constraint to prevent illegal values:
            if lam <= -0.45 or lam >= 0.75:
                return 1e10
            theta = mu_vals * (1.0 - lam)
            if np.any(theta <= 0.01):
                return 1e10
            val = theta + lam * y_vals
            if np.any(val <= 0.01):
                return 1e10
                
            log_pmf = np.log(theta) + (y_vals - 1.0) * np.log(val) - val - sp.gammaln(y_vals + 1.0)
            return -np.sum(log_pmf)
            
        try:
            res = minimize(obj, [0.0], bounds=[(-0.45, 0.75)], method="L-BFGS-B")
            if res.success:
                return float(res.x[0])
            else:
                print("   [AVISO] MLE nao convergiu. Fallback para Poisson (lambda_GP = 0).")
                return 0.0
        except Exception as e:
            print(f"   [AVISO] MLE falhou com erro: {e}. Fallback para Poisson (lambda_GP = 0).")
            return 0.0

    def fit(self, X, y_home, y_away, sample_weight=None):
        X_df = pd.DataFrame(X)
        y_h = np.asarray(y_home, dtype=float)
        y_a = np.asarray(y_away, dtype=float)

        valid = ~np.isnan(y_h) & ~np.isnan(y_a)
        X_clean = X_df.iloc[valid]
        y_h_clean = y_h[valid]
        y_a_clean = y_a[valid]
        sw = np.asarray(sample_weight, dtype=float)[valid] if sample_weight is not None else None

        print(f"Treinando regressores GP para cartões (N={len(X_clean)})...")
        self.model_home_ = self._create_base_regressor()
        self.model_away_ = self._create_base_regressor()
        self.model_home_.fit(X_clean, y_h_clean, reg__sample_weight=sw)
        self.model_away_.fit(X_clean, y_a_clean, reg__sample_weight=sw)

        lambdas = np.maximum(self.model_home_.predict(X_clean), 0.1)
        mus = np.maximum(self.model_away_.predict(X_clean), 0.1)

        print("Estimando dispersao GP (gp_lambda_H, gp_lambda_A) por MLE independente...")
        self.gp_lambda_H_ = self._optimize_gp_lambda(y_h_clean, lambdas)
        self.gp_lambda_A_ = self._optimize_gp_lambda(y_a_clean, mus)
        print(f"  - gp_lambda_H: {self.gp_lambda_H_:.4f}")
        print(f"  - gp_lambda_A: {self.gp_lambda_A_:.4f}")
        return self

    def _marginal_pmf(self, mu_vals, lam):
        import scipy.special as sp
        M = self.max_corners
        k = np.arange(M + 1)
        
        # Broadcast theta and k to shape (N, M+1)
        theta = np.broadcast_to(mu_vals[:, None] * (1.0 - lam), (len(mu_vals), M + 1))
        val = theta + lam * k[None, :]
        mask = (theta > 0.01) & (val > 0.01)
        
        log_pmf = np.zeros((len(mu_vals), M + 1))
        k_mat = np.broadcast_to(k[None, :], (len(mu_vals), M + 1))
        
        log_pmf[mask] = np.log(theta[mask]) + (k_mat[mask] - 1.0) * np.log(val[mask]) - val[mask] - sp.gammaln(k_mat[mask] + 1.0)
        
        pmf = np.zeros((len(mu_vals), M + 1))
        pmf[mask] = np.exp(log_pmf[mask])
        
        pmf = pmf / pmf.sum(axis=1, keepdims=True)
        return pmf

    def predict_distributions(self, X):
        if self.feats is not None:
            X = pd.DataFrame(X)[self.feats]
        lambdas = np.maximum(self.model_home_.predict(X), 0.1)
        mus = np.maximum(self.model_away_.predict(X), 0.1)

        prob_h = self._marginal_pmf(lambdas, self.gp_lambda_H_)
        prob_a = self._marginal_pmf(mus, self.gp_lambda_A_)

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
