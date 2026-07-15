#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/stat_models.py
=============================
Candidatos ESTATÍSTICOS da Linha B (docs/PESQUISA_CLUBES.md §2.2):

- DixonColesClassic: DC 1997 clássico — força de ataque/defesa por time + vantagem de
  mando + rho de placares baixos, com time-decay exponencial (xi) opcional ("DC dinâmico"
  na prática da literatura). MLE via scipy. Diferente do DC-NB de produção (que estima
  λ/μ por GBM sobre features): aqui a força é POR TIME, estimada direto dos placares.
- BivariatePoissonKN: Karlis & Ntzoufras 2003 — componente comum λ3 (covariância).

Ambos expõem fit(df_train) / predict_matrix(df_test) -> PMFs conjuntas, e daí
probs H/D/A, PMF de total de gols etc. Interface pensada para o protocol.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10


def _hda_from_matrix(M: np.ndarray) -> tuple[float, float, float]:
    h = float(np.tril(M, -1).sum())
    d = float(np.trace(M))
    a = float(np.triu(M, 1).sum())
    return h, d, a


class DixonColesClassic:
    """
    log λ_home = mu + home_adv + att[i] - def[j]
    log λ_away = mu + att[j] - def[i]
    Correção rho nas células (0,0),(0,1),(1,0),(1,1). Pesos w = exp(-xi * dias/365).
    xi=0 → estático. Identificação: sum(att)=sum(def)=0.
    """

    def __init__(self, xi: float = 0.0, max_goals: int = MAX_GOALS):
        self.xi = xi
        self.max_goals = max_goals
        self.teams_: list = []
        self.params_: np.ndarray | None = None

    # ---- internals ----
    def _unpack(self, x):
        n = len(self.teams_)
        att = x[:n - 1]
        att = np.append(att, -att.sum())
        def_ = x[n - 1:2 * n - 2]
        def_ = np.append(def_, -def_.sum())
        mu, home, rho = x[2 * n - 2], x[2 * n - 1], x[2 * n]
        return att, def_, mu, home, rho

    @staticmethod
    def _tau(x, y, lam, mu_, rho):
        # correção DC nas células de placar baixo
        if x == 0 and y == 0:
            return 1.0 - lam * mu_ * rho
        if x == 0 and y == 1:
            return 1.0 + lam * rho
        if x == 1 and y == 0:
            return 1.0 + mu_ * rho
        if x == 1 and y == 1:
            return 1.0 - rho
        return 1.0

    def fit(self, df: pd.DataFrame, ref_date=None):
        df = df.reset_index(drop=True)
        self.teams_ = sorted(set(df["home_team"]) | set(df["away_team"]))
        tidx = {t: i for i, t in enumerate(self.teams_)}
        hi = df["home_team"].map(tidx).to_numpy()
        ai = df["away_team"].map(tidx).to_numpy()
        hg = df["home_score"].to_numpy(dtype=int)
        ag = df["away_score"].to_numpy(dtype=int)
        if self.xi > 0:
            ref = pd.Timestamp(ref_date) if ref_date is not None else df["date"].max()
            days = (ref - pd.to_datetime(df["date"])).dt.days.to_numpy(dtype=float)
            w = np.exp(-self.xi * days / 365.0)
        else:
            w = np.ones(len(df))
        n = len(self.teams_)

        # neutral: sem vantagem de mando
        neutral = df["neutral"].to_numpy(dtype=float) if "neutral" in df.columns else np.zeros(len(df))

        low_mask = (hg <= 1) & (ag <= 1)

        def nll(x):
            att, def_, mu, home, rho = self._unpack(x)
            lam = np.exp(mu + home * (1 - neutral) + att[hi] - def_[ai])
            mu_a = np.exp(mu + att[ai] - def_[hi])
            ll = (poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu_a))
            # correção rho só nas células baixas
            tau = np.ones(len(df))
            m = low_mask
            t00 = (hg == 0) & (ag == 0)
            t01 = (hg == 0) & (ag == 1)
            t10 = (hg == 1) & (ag == 0)
            t11 = (hg == 1) & (ag == 1)
            tau[t00] = 1.0 - lam[t00] * mu_a[t00] * rho
            tau[t01] = 1.0 + lam[t01] * rho
            tau[t10] = 1.0 + mu_a[t10] * rho
            tau[t11] = 1.0 - rho
            tau = np.clip(tau, 1e-10, None)
            ll = ll + np.log(tau)
            return -(w * ll).sum()

        x0 = np.zeros(2 * n + 1)
        x0[2 * n - 2] = np.log(max(hg.mean(), 0.1))  # mu
        x0[2 * n - 1] = 0.25                          # home
        x0[2 * n] = -0.05                             # rho
        res = minimize(nll, x0, method="L-BFGS-B", options={"maxiter": 300})
        self.params_ = res.x
        self._tidx = tidx
        return self

    def _rates(self, home_team, away_team, neutral=0.0):
        att, def_, mu, home, rho = self._unpack(self.params_)
        # time desconhecido no teste → força média (0)
        ih = self._tidx.get(home_team)
        ia = self._tidx.get(away_team)
        a_h = att[ih] if ih is not None else 0.0
        d_h = def_[ih] if ih is not None else 0.0
        a_a = att[ia] if ia is not None else 0.0
        d_a = def_[ia] if ia is not None else 0.0
        lam = np.exp(mu + home * (1 - neutral) + a_h - d_a)
        mu_a = np.exp(mu + a_a - d_h)
        return lam, mu_a, rho

    def predict_matrix(self, home_team, away_team, neutral=0.0) -> np.ndarray:
        lam, mu_a, rho = self._rates(home_team, away_team, neutral)
        k = np.arange(self.max_goals + 1)
        ph = poisson.pmf(k, lam)
        pa = poisson.pmf(k, mu_a)
        M = np.outer(ph, pa)
        for x in (0, 1):
            for y in (0, 1):
                M[x, y] *= self._tau(x, y, lam, mu_a, rho)
        M = np.clip(M, 0, None)
        return M / M.sum()

    def predict_hda(self, df_test: pd.DataFrame) -> np.ndarray:
        out = np.zeros((len(df_test), 3))
        neutral = df_test["neutral"].to_numpy(dtype=float) if "neutral" in df_test.columns \
            else np.zeros(len(df_test))
        for i, row in enumerate(df_test.itertuples(index=False)):
            M = self.predict_matrix(row.home_team, row.away_team, neutral[i])
            out[i] = _hda_from_matrix(M)
        return out


class BivariatePoissonKN:
    """
    Karlis & Ntzoufras 2003: (X,Y) = (W1+W3, W2+W3), Wk ~ Poisson(λk) independentes.
    λ1 = exp(mu + home + att_i - def_j), λ2 = exp(mu + att_j - def_i), λ3 = exp(c) global.
    Cov(X,Y) = λ3 — correlação POSITIVA de placares (jogo aberto/fechado).
    """

    def __init__(self, xi: float = 0.0, max_goals: int = MAX_GOALS):
        self.xi = xi
        self.max_goals = max_goals

    def _unpack(self, x):
        n = len(self.teams_)
        att = np.append(x[:n - 1], -x[:n - 1].sum())
        def_ = np.append(x[n - 1:2 * n - 2], -x[n - 1:2 * n - 2].sum())
        mu, home, log_l3 = x[2 * n - 2], x[2 * n - 1], x[2 * n]
        return att, def_, mu, home, np.exp(log_l3)

    def fit(self, df: pd.DataFrame, ref_date=None):
        df = df.reset_index(drop=True)
        self.teams_ = sorted(set(df["home_team"]) | set(df["away_team"]))
        tidx = {t: i for i, t in enumerate(self.teams_)}
        self._tidx = tidx
        hi = df["home_team"].map(tidx).to_numpy()
        ai = df["away_team"].map(tidx).to_numpy()
        hg = df["home_score"].to_numpy(dtype=int)
        ag = df["away_score"].to_numpy(dtype=int)
        neutral = df["neutral"].to_numpy(dtype=float) if "neutral" in df.columns else np.zeros(len(df))
        if self.xi > 0:
            ref = pd.Timestamp(ref_date) if ref_date is not None else df["date"].max()
            days = (ref - pd.to_datetime(df["date"])).dt.days.to_numpy(dtype=float)
            w = np.exp(-self.xi * days / 365.0)
        else:
            w = np.ones(len(df))
        n = len(self.teams_)

        kmax_arr = np.minimum(hg, ag)
        kmax_global = int(kmax_arr.max())

        def nll(x):
            att, def_, mu, home, l3 = self._unpack(x)
            l1 = np.exp(mu + home * (1 - neutral) + att[hi] - def_[ai])
            l2 = np.exp(mu + att[ai] - def_[hi])
            # pmf bivariada vetorizada: soma_k pois(x-k;l1) pois(y-k;l2) pois(k;l3)
            s = np.zeros(len(hg))
            for k in range(kmax_global + 1):
                m = kmax_arr >= k
                s[m] += (poisson.pmf(hg[m] - k, l1[m]) * poisson.pmf(ag[m] - k, l2[m])
                         * poisson.pmf(k, l3))
            ll = np.log(np.clip(s, 1e-300, None))
            return -(w * ll).sum()

        x0 = np.zeros(2 * n + 1)
        x0[2 * n - 2] = np.log(max(hg.mean(), 0.1))
        x0[2 * n - 1] = 0.25
        x0[2 * n] = np.log(0.1)
        res = minimize(nll, x0, method="L-BFGS-B", options={"maxiter": 200})
        self.params_ = res.x
        return self

    def predict_matrix(self, home_team, away_team, neutral=0.0) -> np.ndarray:
        att, def_, mu, home, l3 = self._unpack(self.params_)
        ih = self._tidx.get(home_team)
        ia = self._tidx.get(away_team)
        a_h = att[ih] if ih is not None else 0.0
        d_h = def_[ih] if ih is not None else 0.0
        a_a = att[ia] if ia is not None else 0.0
        d_a = def_[ia] if ia is not None else 0.0
        l1 = np.exp(mu + home * (1 - neutral) + a_h - d_a)
        l2 = np.exp(mu + a_a - d_h)
        G = self.max_goals
        M = np.zeros((G + 1, G + 1))
        k = np.arange(G + 1)
        p3 = poisson.pmf(k, l3)
        p1 = poisson.pmf(k, l1)
        p2 = poisson.pmf(k, l2)
        for x in range(G + 1):
            for y in range(G + 1):
                kk = np.arange(min(x, y) + 1)
                M[x, y] = float((p1[x - kk] * p2[y - kk] * p3[kk]).sum())
        M = np.clip(M, 0, None)
        return M / M.sum()

    def predict_hda(self, df_test: pd.DataFrame) -> np.ndarray:
        out = np.zeros((len(df_test), 3))
        neutral = df_test["neutral"].to_numpy(dtype=float) if "neutral" in df_test.columns \
            else np.zeros(len(df_test))
        for i, row in enumerate(df_test.itertuples(index=False)):
            M = self.predict_matrix(row.home_team, row.away_team, neutral[i])
            out[i] = _hda_from_matrix(M)
        return out
