#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/state_space.py
===============================
Fase 6.3 — modelo dinâmico score-driven (GAS, Generalized Autoregressive Score),
inspirado em Koopman & Lit 2015 (bivariado Poisson com intensidades evoluindo no
tempo; o único modelo da literatura com lucro comprovado contra odds — ver
docs/PESQUISA_CLUBES.md §2.1). Sem MCMC/Kalman completo (custoso demais para 54k
jogos): aproximação score-driven padrão da literatura de séries temporais
financeiras (Creal, Koopman & Lucas 2013), que É o que o Koopman-Lit usa em
formas posteriores (score-driven time series models, Koopman/Lit/Nazarov 2019).

Estado por time: (att, def), log-intensidade de ataque/defesa. Dinâmica:
    att_{t+1} = ω_att + φ*att_t + κ*s_att_t
    def_{t+1} = ω_def + φ*def_t + κ*s_def_t
onde s_t é o SCORE (gradiente da log-verossimilhança Poisson em t) escalado pela
inversa da informação de Fisher — o que dá ao update um caráter "aprende mais
rápido quando surpreendido" (diferente do pi-rating, que usa só o erro bruto).

λ_home = exp(mu + home_adv + att_i,t - def_j,t), μ_away = exp(mu + att_j,t - def_i,t).
MLE conjunta de (ω, φ, κ, mu, home_adv) via scipy, com os estados marginalizados
recursivamente (filtro determinístico — não precisa de partículas/MCMC).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


class GASDynamicRatings:
    """Ratings dinâmicos score-driven por liga (times não voam entre ligas)."""

    def __init__(self, max_goals: int = 10):
        self.max_goals = max_goals

    def _run_filter(self, hi, ai, hg, ag, neutral, n_teams, omega, phi, kappa, mu, home):
        """Roda o filtro score-driven sequencialmente; retorna λ/μ pré-jogo (para NLL)
        e os estados finais (para inferência fora da amostra)."""
        att = np.zeros(n_teams)
        deff = np.zeros(n_teams)
        lam_out = np.empty(len(hg))
        mu_out = np.empty(len(hg))
        for t in range(len(hg)):
            i, j = hi[t], ai[t]
            a_i, d_i = att[i], deff[i]
            a_j, d_j = att[j], deff[j]
            h = home * (1 - neutral[t])
            lam = np.exp(mu + h + a_i - d_j)
            mu_ = np.exp(mu + a_j - d_i)
            lam_out[t] = lam
            mu_out[t] = mu_

            # score = (observado - esperado) / sqrt(esperado) (aprox. info Fisher Poisson)
            s_att_i = (hg[t] - lam) / np.sqrt(max(lam, 1e-3))
            s_def_j = -(hg[t] - lam) / np.sqrt(max(lam, 1e-3))
            s_att_j = (ag[t] - mu_) / np.sqrt(max(mu_, 1e-3))
            s_def_i = -(ag[t] - mu_) / np.sqrt(max(mu_, 1e-3))

            att[i] = omega + phi * a_i + kappa * s_att_i
            deff[j] = omega + phi * d_j + kappa * s_def_j
            att[j] = omega + phi * a_j + kappa * s_att_j
            deff[i] = omega + phi * d_i + kappa * s_def_i
        return lam_out, mu_out, att, deff

    def fit(self, df: pd.DataFrame):
        df = df.sort_values("date").reset_index(drop=True)
        self.teams_ = sorted(set(df["home_team"]) | set(df["away_team"]))
        tidx = {t: i for i, t in enumerate(self.teams_)}
        self._tidx = tidx
        hi = df["home_team"].map(tidx).to_numpy()
        ai = df["away_team"].map(tidx).to_numpy()
        hg = df["home_score"].to_numpy(dtype=float)
        ag = df["away_score"].to_numpy(dtype=float)
        neutral = df["neutral"].to_numpy(dtype=float) if "neutral" in df.columns else np.zeros(len(df))
        n = len(self.teams_)

        def nll(params):
            omega, phi, kappa, mu, home = params
            if not (0.0 <= phi < 1.0) or kappa < 0:
                return 1e10
            lam, mu_, _, _ = self._run_filter(hi, ai, hg, ag, neutral, n, omega, phi, kappa, mu, home)
            lam = np.clip(lam, 1e-6, 1e6)
            mu_ = np.clip(mu_, 1e-6, 1e6)
            return -(poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu_)).sum()

        x0 = [0.0, 0.9, 0.05, np.log(max(hg.mean(), 0.3)), 0.25]
        res = minimize(nll, x0, method="L-BFGS-B",
                       bounds=[(-0.5, 0.5), (0.5, 0.999), (0.0, 0.5), (-2.0, 2.0), (-0.5, 1.0)])
        self.params_ = res.x
        omega, phi, kappa, mu, home = self.params_
        _, _, att_final, def_final = self._run_filter(hi, ai, hg, ag, neutral, n,
                                                       omega, phi, kappa, mu, home)
        self.att_ = att_final
        self.def_ = def_final
        self.omega_, self.phi_, self.kappa_, self.mu_, self.home_ = omega, phi, kappa, mu, home
        return self

    def predict_matrix(self, home_team, away_team, neutral=0.0) -> np.ndarray:
        ih = self._tidx.get(home_team)
        ia = self._tidx.get(away_team)
        a_h = self.att_[ih] if ih is not None else 0.0
        d_h = self.def_[ih] if ih is not None else 0.0
        a_a = self.att_[ia] if ia is not None else 0.0
        d_a = self.def_[ia] if ia is not None else 0.0
        lam = np.exp(self.mu_ + self.home_ * (1 - neutral) + a_h - d_a)
        mu_ = np.exp(self.mu_ + a_a - d_h)
        k = np.arange(self.max_goals + 1)
        ph = poisson.pmf(k, lam)
        pa = poisson.pmf(k, mu_)
        M = np.outer(ph, pa)
        return M / M.sum()

    def predict_hda(self, df_test: pd.DataFrame) -> np.ndarray:
        out = np.zeros((len(df_test), 3))
        neutral = df_test["neutral"].to_numpy(dtype=float) if "neutral" in df_test.columns \
            else np.zeros(len(df_test))
        for i, row in enumerate(df_test.itertuples(index=False)):
            M = self.predict_matrix(row.home_team, row.away_team, neutral[i])
            out[i] = [float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())]
        return out
