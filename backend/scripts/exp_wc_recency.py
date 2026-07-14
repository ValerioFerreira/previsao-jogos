#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp_wc_recency.py
==========================
Testa a hipotese: dentro da Copa do Mundo 2026, os jogos ANTERIORES da propria
Copa (in-tournament) tem mais poder preditivo para mercados secundarios
(escanteios, cartoes, chutes) do que o historico PRE-Copa (long-run) da selecao?

Metodologia (walk-forward, respeita cronologia):
  Para cada selecao, para cada jogo i>=2 dela na WC2026 (ordem cronologica):
    - in_wc_avg_X  = media da propria selecao em X (escanteios/cartoes/chutes)
                     nos jogos 1..i-1 DA PROPRIA WC2026 (recencia dentro do torneio).
    - pre_wc_avg_X = media da propria selecao em X nos ultimos K jogos ANTES do
                     inicio da WC2026 (qualquer competicao -- historico "de longo
                     prazo" que o Elo/modelo atual ja usa).
  Compara o poder preditivo de cada um (e do blend) sobre o valor REAL de X no
  jogo i, agregando por "profundidade" (game_index) para ver se o efeito cresce
  conforme a selecao acumula jogos na propria Copa.

Amostra e pequena por natureza (48 selecoes, no maximo ~7-8 jogos cada) -- os
resultados sao reportados com o N de cada bucket, sem inflar certeza.
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from app.services import raw_cache

MARKETS = {
    "corners": "Corner Kicks",
    "shots": "Total Shots",
    "cards": None,  # tratado a parte (soma amarelo+vermelho)
}
PRE_WC_WINDOW = 10  # ultimos K jogos antes da copa, qualquer competicao
EWMA_HALFLIFE = 1.0  # jogos, p/ media in-wc com decaimento exponencial


def _stat(stats_block, type_name):
    for s in stats_block or []:
        if s.get("type") == type_name:
            v = s.get("value")
            if v is None:
                return None
            if isinstance(v, str) and v.endswith("%"):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def _cards(stats_block):
    y = _stat(stats_block, "Yellow Cards") or 0
    r = _stat(stats_block, "Red Cards") or 0
    return y + r


def extract_all():
    """Retorna lista de registros: um por (fixture, team) com data, competicao e stats."""
    records = []
    for d in raw_cache.iter_all_raw():
        fx = d.get("fixture", {}) or {}
        lg = d.get("league", {}) or {}
        status = (fx.get("status") or {}).get("short")
        if status not in ("FT", "AET", "PEN"):
            continue
        date = fx.get("date")
        if not date:
            continue
        stats = d.get("statistics") or []
        by_team = {s.get("team", {}).get("id"): s.get("statistics") for s in stats}
        for side in ("home", "away"):
            t = (d.get("teams") or {}).get(side) or {}
            tid = t.get("id")
            if tid is None:
                continue
            sb = by_team.get(tid)
            rec = {
                "fixture_id": fx.get("id"),
                "team_id": tid,
                "team_name": t.get("name"),
                "date": date,
                "league_id": lg.get("id"),
                "league_name": lg.get("name"),
                "season": lg.get("season"),
                "corners": _stat(sb, "Corner Kicks"),
                "shots": _stat(sb, "Total Shots"),
                "cards": _cards(sb) if sb else None,
            }
            records.append(rec)
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    return df


def build_samples(df):
    wc = df[(df["league_id"] == 1) & (df["season"] == 2026)].copy()
    wc = wc.sort_values(["team_id", "date"])
    wc_start = wc["date"].min()

    hist = df[df["date"] < wc_start].copy()
    hist = hist.sort_values(["team_id", "date"])

    samples = []
    for tid, grp in wc.groupby("team_id"):
        grp = grp.sort_values("date").reset_index(drop=True)
        n = len(grp)
        pre = hist[hist["team_id"] == tid].tail(PRE_WC_WINDOW)
        pre_avg = {m: pre[m].dropna().mean() if len(pre) else np.nan for m in MARKETS}
        pre_n = len(pre)
        for i in range(1, n):  # i = indice do jogo atual (0-based), precisa >=1 jogo anterior na WC
            prior = grp.iloc[:i]
            row = grp.iloc[i]
            game_index = i + 1  # 1-based: 2, 3, 4...
            for m, colname in MARKETS.items():
                actual = row[m]
                if pd.isna(actual):
                    continue
                prior_vals = prior[m].dropna()
                in_wc_avg = prior_vals.mean() if len(prior_vals) else np.nan
                if len(prior_vals):
                    # EWMA: mais peso ao jogo mais recente da propria WC (halflife curto)
                    w = 0.5 ** (np.arange(len(prior_vals))[::-1] / EWMA_HALFLIFE)
                    in_wc_ewma = float(np.average(prior_vals.values, weights=w))
                else:
                    in_wc_ewma = np.nan
                samples.append({
                    "team_id": tid,
                    "team_name": row["team_name"],
                    "market": m,
                    "game_index": game_index,
                    "actual": actual,
                    "in_wc_avg": in_wc_avg,
                    "in_wc_ewma": in_wc_ewma,
                    "pre_wc_avg": pre_avg[m],
                    "pre_wc_n": pre_n,
                })
    return pd.DataFrame(samples), wc, hist


def evaluate(samples):
    print(f"\n{'='*70}\nAmostra total (jogo>=2 na WC2026, por mercado):\n{'='*70}")
    print(samples.groupby("market").size())

    for market in MARKETS:
        sub = samples[samples["market"] == market].dropna(subset=["actual", "in_wc_avg", "pre_wc_avg"])
        print(f"\n--- Mercado: {market} (N={len(sub)}) ---")
        if len(sub) < 8:
            print("  N insuficiente, pulando.")
            continue

        corr_in = sub["actual"].corr(sub["in_wc_avg"])
        corr_pre = sub["actual"].corr(sub["pre_wc_avg"])
        corr_ewma = sub["actual"].corr(sub["in_wc_ewma"])
        mae_in = (sub["actual"] - sub["in_wc_avg"]).abs().mean()
        mae_pre = (sub["actual"] - sub["pre_wc_avg"]).abs().mean()
        mae_ewma = (sub["actual"] - sub["in_wc_ewma"]).abs().mean()
        mae_mean_naive = (sub["actual"] - sub["actual"].mean()).abs().mean()

        print(f"  corr(actual, in_wc_avg)   = {corr_in:+.3f}   MAE={mae_in:.3f}")
        print(f"  corr(actual, in_wc_ewma)  = {corr_ewma:+.3f}   MAE={mae_ewma:.3f}  (halflife={EWMA_HALFLIFE:.1f} jogo)")
        print(f"  corr(actual, pre_wc_avg)  = {corr_pre:+.3f}   MAE={mae_pre:.3f}")
        print(f"  MAE baseline (media global) = {mae_mean_naive:.3f}")

        # regressao multipla padronizada p/ comparar peso relativo
        X = sub[["in_wc_avg", "pre_wc_avg"]].copy()
        X = (X - X.mean()) / X.std()
        X["const"] = 1.0
        y = sub["actual"].values
        beta, *_ = np.linalg.lstsq(X.values, y, rcond=None)
        print(f"  Regressao (padronizada): beta_in_wc={beta[0]:+.3f}  beta_pre_wc={beta[1]:+.3f}")

        # blend otimo por grid search (peso alpha em in_wc_avg, 1-alpha em pre_wc_avg)
        best_alpha, best_mae = 0, 1e9
        for alpha in np.linspace(0, 1, 21):
            pred = alpha * sub["in_wc_avg"] + (1 - alpha) * sub["pre_wc_avg"]
            mae = (sub["actual"] - pred).abs().mean()
            if mae < best_mae:
                best_mae, best_alpha = mae, alpha
        print(f"  Melhor blend: alpha(in_wc)={best_alpha:.2f}  MAE={best_mae:.3f}")

        # por profundidade (game_index): efeito cresce com mais jogos acumulados na WC?
        print("  Por profundidade (game_index):")
        for gi, g in sub.groupby("game_index"):
            if len(g) < 4:
                continue
            ci = g["actual"].corr(g["in_wc_avg"])
            cp = g["actual"].corr(g["pre_wc_avg"])
            print(f"    jogo {gi}: N={len(g):2d}  corr_in_wc={ci:+.3f}  corr_pre_wc={cp:+.3f}")


if __name__ == "__main__":
    print("Extraindo dados do espelho local...")
    df = extract_all()
    print(f"Total registros (fixture x time): {len(df)}")
    samples, wc, hist = build_samples(df)
    print(f"Times na WC2026: {wc['team_id'].nunique()} | jogos WC2026: {wc['fixture_id'].nunique()}")
    evaluate(samples)
