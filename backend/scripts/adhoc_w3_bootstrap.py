#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w3_bootstrap.py
==============================
Bateria ad-hoc W3 (2026-07-22), parte 2/3: bootstrap (>=2000 reamostragens
com reposicao) do ROI de cada uma das 17 combinacoes liga x estrategia
reconstruidas por adhoc_w3_reconstruct.py, mais o pooled por estrategia (5
linhas, cada uma juntando as ligas que tem aquela estrategia) e o grand
pooled (tudo junto). Em seguida aplica correcao de comparacoes multiplas
(Bonferroni e Benjamini-Hochberg/FDR) nos 17 testes liga x estrategia.

Metodologia do bootstrap: reamostra as APOSTAS (nao os jogos-fonte) com
reposicao, mesmo N do grupo original, recalcula ROI% = 100*lucro/stake_total
a cada reamostragem; >=2000 iteracoes (aqui 20000, e barato dado N<=1408).
IC 95% = percentil 2.5/97.5 da distribuicao bootstrap (metodo percentil,
sem assumir normalidade -- apropriado p/ ROI de apostas com odds ~2, que e
assimetrico: perda de R$5 fixa vs ganho de odd*R$5-R$5 variavel).

p-valor (bicaudal) tambem via bootstrap: 2*min(P(ROI_boot<=0), P(ROI_boot>=0)),
capado em 1 -- consistente com o mesmo metodo do IC (nao troca pra outro
approach no meio do caminho). Teste-t de 1 amostra (scipy) reportado como
checagem cruzada parametrica.

Uso: python scripts/adhoc_w3_bootstrap.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = ROOT / "data" / "reports" / "adhoc_valuebet_w3"
BETS = OUT_DIR / "bets_long.parquet"

STAKE = 5.0
N_BOOT = 20000
SEED = 20260722
ALPHA = 0.05


def bootstrap_roi(net_returns: np.ndarray, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Retorna um array de n_boot ROI% (reamostragem com reposicao, mesmo N)."""
    n = len(net_returns)
    idx = rng.integers(0, n, size=(n_boot, n))
    resampled = net_returns[idx]  # (n_boot, n)
    lucro = resampled.sum(axis=1)
    stake_total = n * STAKE
    return 100.0 * lucro / stake_total


def analyze_group(label: str, net_returns: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(net_returns)
    point_roi = 100.0 * net_returns.sum() / (n * STAKE)
    boot = bootstrap_roi(net_returns, N_BOOT, rng)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    p_le0 = float((boot <= 0).mean())
    p_ge0 = float((boot >= 0).mean())
    p_boot = min(1.0, 2 * min(p_le0, p_ge0))
    # cross-check parametrico: teste-t de 1 amostra sobre o retorno por aposta (em R$)
    t_stat, p_ttest = stats.ttest_1samp(net_returns, popmean=0.0)
    excludes_zero = (lo > 0) or (hi < 0)
    return dict(
        label=label, n=n, roi_pct=round(point_roi, 4),
        ci_lo=round(float(lo), 4), ci_hi=round(float(hi), 4),
        excludes_zero=excludes_zero,
        p_bootstrap=round(p_boot, 4), p_ttest=round(float(p_ttest), 4),
        odd_media=None,
    )


def main():
    bets = pd.read_parquet(BETS)
    bets["league"] = bets["country"].map({"Brazil": "Brasileirao", "England": "Premier League",
                                           "Spain": "La Liga", "Italy": "Serie A Italia"})
    rng = np.random.default_rng(SEED)

    print("=" * 90)
    print(f" BOOTSTRAP ({N_BOOT} reamostragens) -- IC 95%% do ROI, 17 combinacoes liga x estrategia")
    print("=" * 90)

    combo_results = []
    for (league, strategy), g in bets.groupby(["league", "strategy"]):
        r = analyze_group(f"{league} / {strategy}", g["net_return"].to_numpy(), rng)
        r["league"] = league
        r["strategy"] = strategy
        r["odd_media"] = round(float(g["odd"].mean()), 3)
        combo_results.append(r)
    combo_df = pd.DataFrame(combo_results).sort_values(["strategy", "league"]).reset_index(drop=True)

    for r in combo_df.itertuples(index=False):
        flag = "EXCLUI 0" if r.excludes_zero else "inclui 0"
        print(f"  {r.league:14s} / {r.strategy:14s}  N={r.n:4d}  ROI={r.roi_pct:+7.2f}%  "
              f"IC95%=[{r.ci_lo:+7.2f}%, {r.ci_hi:+7.2f}%]  ({flag})  "
              f"p_boot={r.p_bootstrap:.4f}  p_ttest={r.p_ttest:.4f}")

    print("\n" + "=" * 90)
    print(" POOLED POR ESTRATEGIA (junta as ligas que tem aquela estrategia)")
    print("=" * 90)
    pooled_results = []
    for strategy, g in bets.groupby("strategy"):
        r = analyze_group(strategy, g["net_return"].to_numpy(), rng)
        r["strategy"] = strategy
        pooled_results.append(r)
        flag = "EXCLUI 0" if r["excludes_zero"] else "inclui 0"
        print(f"  {strategy:14s}  N={r['n']:4d}  ROI={r['roi_pct']:+7.2f}%  "
              f"IC95%=[{r['ci_lo']:+7.2f}%, {r['ci_hi']:+7.2f}%]  ({flag})  p_boot={r['p_bootstrap']:.4f}")
    pooled_df = pd.DataFrame(pooled_results)

    print("\n" + "=" * 90)
    print(" GRAND POOLED (todas as 17 combinacoes juntas, 6122 apostas)")
    print("=" * 90)
    grand = analyze_group("grand_pooled", bets["net_return"].to_numpy(), rng)
    flag = "EXCLUI 0" if grand["excludes_zero"] else "inclui 0"
    print(f"  N={grand['n']}  ROI={grand['roi_pct']:+.2f}%  IC95%=[{grand['ci_lo']:+.2f}%, "
          f"{grand['ci_hi']:+.2f}%]  ({flag})  p_boot={grand['p_bootstrap']:.4f}")

    # --- Correcao de comparacoes multiplas (Bonferroni e BH/FDR) nos 17 testes ---
    print("\n" + "=" * 90)
    print(" CORRECAO DE COMPARACOES MULTIPLAS (17 testes liga x estrategia)")
    print("=" * 90)
    m = len(combo_df)
    pvals = combo_df["p_bootstrap"].to_numpy()
    bonf_alpha = ALPHA / m
    bonf_sig = pvals < bonf_alpha
    order = np.argsort(pvals)
    ranked = pvals[order]
    bh_thresh = (np.arange(1, m + 1) / m) * ALPHA
    bh_pass = ranked <= bh_thresh
    # maior k tal que p_(k) <= (k/m)*alpha -- todos abaixo desse k tambem rejeitam
    if bh_pass.any():
        k_max = np.max(np.where(bh_pass)[0])
        bh_sig_sorted = np.zeros(m, dtype=bool)
        bh_sig_sorted[: k_max + 1] = True
    else:
        bh_sig_sorted = np.zeros(m, dtype=bool)
    bh_sig = np.zeros(m, dtype=bool)
    bh_sig[order] = bh_sig_sorted
    # BH q-value (adjusted p-value) por combinacao, monotonico
    bh_qval_sorted = np.minimum.accumulate((ranked * m / np.arange(1, m + 1))[::-1])[::-1]
    bh_qval_sorted = np.clip(bh_qval_sorted, 0, 1)
    bh_qval = np.empty(m)
    bh_qval[order] = bh_qval_sorted

    combo_df["p_bonferroni_adj"] = np.minimum(pvals * m, 1.0)
    combo_df["bonferroni_sig_0.05"] = bonf_sig
    combo_df["bh_qvalue"] = np.round(bh_qval, 4)
    combo_df["bh_fdr_sig_0.05"] = bh_sig

    print(f"  Bonferroni: alpha ajustado = 0.05/{m} = {bonf_alpha:.5f}")
    print(f"  Testes significativos (bruto p<0.05): {(pvals < ALPHA).sum()}/{m}")
    print(f"  Testes significativos apos Bonferroni: {bonf_sig.sum()}/{m}")
    print(f"  Testes significativos apos BH/FDR (q<0.05): {bh_sig.sum()}/{m}")
    print("\n  Detalhe (ordenado por p bruto):")
    show = combo_df.sort_values("p_bootstrap")[
        ["league", "strategy", "n", "roi_pct", "p_bootstrap", "p_bonferroni_adj", "bh_qvalue",
         "bonferroni_sig_0.05", "bh_fdr_sig_0.05"]
    ]
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(show.to_string(index=False))

    combo_df.to_csv(OUT_DIR / "combo_bootstrap_ci.csv", index=False)
    pooled_df.to_csv(OUT_DIR / "pooled_bootstrap_ci.csv", index=False)
    pd.DataFrame([grand]).to_csv(OUT_DIR / "grand_pooled_bootstrap_ci.csv", index=False)

    print(f"\nCSVs salvos em {OUT_DIR}")


if __name__ == "__main__":
    main()
