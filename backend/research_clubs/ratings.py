#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/ratings.py
=========================
Ratings dinâmicos da literatura (Linha B) — todos point-in-time (o rating usado como
feature é o PRÉ-jogo; a atualização acontece depois). Fórmulas: survey Bunker et al.
2024 (arXiv 2403.07669) e papers originais.

- pi-ratings (Constantinou & Fenton 2013): rating casa/fora, erro de saldo esperado com
  amortecimento logarítmico de goleadas. SOTA nos challenges com CatBoost por cima.
- Berrar ratings (Berrar et al. 2019): força ofensiva/defensiva via logística de gols
  esperados; 4 atualizações por jogo.
- GAP ratings (Wheatcroft 2020/21): ataque/defesa casa/fora POR ESTATÍSTICA (chutes,
  escanteios, ...), desenhado para prever contagens não-raras.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ─── pi-ratings ──────────────────────────────────────────────────────────────
def _pi_expected_gd(r: float, b: float = 10.0, c: float = 3.0) -> float:
    return np.sign(r) * (b ** (abs(r) / c) - 1.0)


def compute_pi_ratings(df: pd.DataFrame, lam: float = 0.035, gamma: float = 0.7,
                       b: float = 10.0, c: float = 3.0) -> pd.DataFrame:
    """
    df ordenado por data com home_team/away_team/home_score/away_score.
    Retorna DataFrame alinhado com colunas pré-jogo:
      pi_home_h, pi_home_a, pi_away_h, pi_away_a, pi_home_mean, pi_away_mean, pi_exp_gd
    """
    RH: dict = {}
    RA: dict = {}
    out = np.zeros((len(df), 7))
    for i, row in enumerate(df.itertuples(index=False)):
        ht, at = row.home_team, row.away_team
        rah, raa = RH.get(ht, 0.0), RA.get(ht, 0.0)
        rbh, rba = RH.get(at, 0.0), RA.get(at, 0.0)
        e_home = _pi_expected_gd(rah, b, c)
        e_away = _pi_expected_gd(rba, b, c)
        e_gd = e_home - e_away
        out[i] = [rah, raa, rbh, rba, (rah + raa) / 2.0, (rbh + rba) / 2.0, e_gd]

        gd = row.home_score - row.away_score
        err = gd - e_gd
        psi = c * np.log10(1.0 + abs(err))
        # time da casa: atualiza rating de CASA pelo erro; o de FORA acompanha via gamma
        d_h = lam * psi * np.sign(err)
        RH[ht] = rah + d_h
        RA[ht] = raa + gamma * d_h
        # visitante: erro espelhado
        d_a = lam * psi * np.sign(-err)
        RA[at] = rba + d_a
        RH[at] = rbh + gamma * d_a
    return pd.DataFrame(out, columns=[
        "pi_home_h", "pi_home_a", "pi_away_h", "pi_away_a",
        "pi_home_mean", "pi_away_mean", "pi_exp_gd"], index=df.index)


# ─── Berrar ratings ──────────────────────────────────────────────────────────
def compute_berrar_ratings(df: pd.DataFrame, alpha_h: float = 5.0, alpha_a: float = 5.0,
                           beta: float = 2.0, bias_h: float = 0.0, bias_a: float = 0.0,
                           w_o: float = 0.1, w_d: float = 0.1) -> pd.DataFrame:
    """
    Ratings ofensivo/defensivo por logística de gols esperados.
    Retorna colunas pré-jogo: br_home_off, br_home_def, br_away_off, br_away_def,
    br_exp_gh, br_exp_ga (gols esperados do jogo pela fórmula logística).
    """
    O: dict = {}
    D: dict = {}
    out = np.zeros((len(df), 6))
    for i, row in enumerate(df.itertuples(index=False)):
        ht, at = row.home_team, row.away_team
        oh, dh = O.get(ht, 0.0), D.get(ht, 0.0)
        oa, da = O.get(at, 0.0), D.get(at, 0.0)
        g_h = alpha_h / (1.0 + np.exp(-beta * (oh - da) - bias_h))
        g_a = alpha_a / (1.0 + np.exp(-beta * (oa - dh) - bias_a))
        out[i] = [oh, dh, oa, da, g_h, g_a]

        gh, ga = row.home_score, row.away_score
        O[ht] = oh + w_o * (gh - g_h)
        D[ht] = dh + w_d * (ga - g_a)
        O[at] = oa + w_o * (ga - g_a)
        D[at] = da + w_d * (gh - g_h)
    return pd.DataFrame(out, columns=[
        "br_home_off", "br_home_def", "br_away_off", "br_away_def",
        "br_exp_gh", "br_exp_ga"], index=df.index)


# ─── GAP ratings (por estatística) ───────────────────────────────────────────
def compute_gap_ratings(df: pd.DataFrame, home_stat_col: str, away_stat_col: str,
                        lam: float = 0.1, phi1: float = 0.7, phi2: float = 0.7,
                        prefix: str = "gap") -> pd.DataFrame:
    """
    GAP ratings para UMA estatística (ex.: chutes: home_cur_sb_shots/away_cur_sb_shots).
    4 ratings por time (ataque/defesa × casa/fora), init = média incremental da liga.
    Retorna colunas pré-jogo: {prefix}_home_att, {prefix}_home_def, {prefix}_away_att,
    {prefix}_away_def, {prefix}_exp_home, {prefix}_exp_away.
    Linhas sem a estatística não atualizam ratings (e recebem os valores correntes).
    """
    Ha: dict = {}; Hd: dict = {}; Aa: dict = {}; Ad: dict = {}
    out = np.full((len(df), 6), np.nan)
    running_mean, n_seen = 2.0, 1  # prior fraco; converge rápido para a média real
    hs = df[home_stat_col].to_numpy(dtype=float)
    as_ = df[away_stat_col].to_numpy(dtype=float)
    for i, row in enumerate(df.itertuples(index=False)):
        ht, at = row.home_team, row.away_team
        m = running_mean
        ha_i = Ha.get(ht, m); hd_i = Hd.get(ht, m)
        aa_i = Aa.get(ht, m); ad_i = Ad.get(ht, m)
        ha_j = Ha.get(at, m); hd_j = Hd.get(at, m)
        aa_j = Aa.get(at, m); ad_j = Ad.get(at, m)
        exp_h = (ha_i + ad_j) / 2.0
        exp_a = (aa_j + hd_i) / 2.0
        out[i] = [ha_i, hd_i, aa_j, ad_j, exp_h, exp_a]

        sh, sa = hs[i], as_[i]
        if np.isnan(sh) or np.isnan(sa):
            continue
        running_mean += (0.5 * (sh + sa) - running_mean) / (n_seen + 1)
        n_seen += 1
        err_h = sh - exp_h
        err_a = sa - exp_a
        # time da casa i: ataque em casa (peso phi1) e a versão fora acompanha (1-phi1)
        Ha[ht] = max(ha_i + lam * phi1 * err_h, 0.0)
        Aa[ht] = max(aa_i + lam * (1 - phi1) * err_h, 0.0)
        Hd[ht] = max(hd_i + lam * phi1 * err_a, 0.0)
        Ad[ht] = max(ad_i + lam * (1 - phi1) * err_a, 0.0)
        # visitante j
        Aa[at] = max(aa_j + lam * phi2 * err_a, 0.0)
        Ha[at] = max(ha_j + lam * (1 - phi2) * err_a, 0.0)
        Ad[at] = max(ad_j + lam * phi2 * err_h, 0.0)
        Hd[at] = max(hd_j + lam * (1 - phi2) * err_h, 0.0)
    return pd.DataFrame(out, columns=[
        f"{prefix}_home_att", f"{prefix}_home_def", f"{prefix}_away_att",
        f"{prefix}_away_def", f"{prefix}_exp_home", f"{prefix}_exp_away"], index=df.index)
