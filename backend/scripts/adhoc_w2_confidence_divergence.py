#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w2_confidence_divergence.py
==========================================
Bateria ad-hoc "w2" (2026-07-22), pergunta 1: a hipotese de que a CONFIANCA do
modelo em O/U 2,5 (|p_model_over - 0.5|) e alta principalmente quando o
modelo esta ecoando o consenso do mercado (divergencia baixa vs p_fair_open),
nao quando esta achando algo novo -- explicacao candidata pro achado
contraintuitivo "modelo escolhe" ter a MELHOR taxa de acerto mas o PIOR ROI
nas 4 ligas do backtest anterior.

Parte do dataset `data/built/backtest_valuebet_dataset.parquet` (8117 fixtures,
todas as ligas). Nao mexe em model_artifacts/predictor.py/app real -- pesquisa
pura, decisao de produto.

Saida: prints + `data/reports/adhoc_valuebet_w2/confidence_divergence.csv`
(bucket vs divergencia) e `..._raw_correlation.csv` (n, r, p por metodo).

Uso: python scripts/adhoc_w2_confidence_divergence.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
OUT_DIR = ROOT / "data" / "reports" / "adhoc_valuebet_w2"


def main():
    df = pd.read_parquet(DATASET)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # p_fair de referencia: abertura quando existir, senao fechamento (27
    # fixtures sem abertura mas com fechamento -- cobertura quase total).
    df["p_fair_ref_over"] = df["p_fair_open_over"].fillna(df["p_fair_close_over"])
    df["ref_source"] = np.where(df["p_fair_open_over"].notna(), "open",
                                 np.where(df["p_fair_close_over"].notna(), "close", "none"))

    sub = df[df["p_fair_ref_over"].notna()].copy()
    print(f"Total fixtures: {len(df)} | com p_fair_ref_over (open ou close): {len(sub)}")
    print(sub["ref_source"].value_counts().to_dict())

    # ---- 1) Correlacao p_model_over vs p_fair_ref_over (bruta) ----
    print("\n=== Correlacao p_model_over vs p_fair_ref_over (mercado a priori) ===")
    pear_r, pear_p = stats.pearsonr(sub["p_model_over"], sub["p_fair_ref_over"])
    spear_r, spear_p = stats.spearmanr(sub["p_model_over"], sub["p_fair_ref_over"])
    print(f"Pearson  r={pear_r:.4f}  p={pear_p:.2e}  (n={len(sub)})")
    print(f"Spearman r={spear_r:.4f}  p={spear_p:.2e}  (n={len(sub)})")

    corr_rows = [
        dict(metodo="pearson", n=len(sub), r=pear_r, p=pear_p),
        dict(metodo="spearman", n=len(sub), r=spear_r, p=spear_p),
    ]

    # Repetir SO no subconjunto com abertura de verdade (evita contaminar com
    # fechamento, que ja incorpora informacao pos-abertura/movimento de linha).
    sub_open = df[df["p_fair_open_over"].notna()].copy()
    pear_r_o, pear_p_o = stats.pearsonr(sub_open["p_model_over"], sub_open["p_fair_open_over"])
    spear_r_o, spear_p_o = stats.spearmanr(sub_open["p_model_over"], sub_open["p_fair_open_over"])
    print(f"\n[SO abertura, n={len(sub_open)}] Pearson r={pear_r_o:.4f} p={pear_p_o:.2e} | "
          f"Spearman r={spear_r_o:.4f} p={spear_p_o:.2e}")
    corr_rows.append(dict(metodo="pearson_so_abertura", n=len(sub_open), r=pear_r_o, p=pear_p_o))
    corr_rows.append(dict(metodo="spearman_so_abertura", n=len(sub_open), r=spear_r_o, p=spear_p_o))

    pd.DataFrame(corr_rows).to_csv(OUT_DIR / "confidence_correlation_raw.csv", index=False)

    # ---- 2) Divergencia por bucket de confianca ----
    sub["conf"] = np.maximum(sub["p_model_over"], sub["p_model_under"])
    sub["divergence"] = (sub["p_model_over"] - sub["p_fair_ref_over"]).abs()

    high = sub[sub["conf"] > 0.65]
    med = sub[(sub["conf"] >= 0.50) & (sub["conf"] <= 0.55)]
    low_mid = sub[(sub["conf"] > 0.55) & (sub["conf"] <= 0.65)]  # zona intermediaria, so contexto

    print(f"\n=== Divergencia |p_model_over - p_fair_ref_over| por bucket de confianca ===")
    print(f"Confianca = max(p_model_over, p_model_under)")

    rows = []
    for name, g in (("alta (>65%)", high), ("media (50-55%)", med), ("intermediaria (55-65%)", low_mid)):
        if len(g) == 0:
            print(f"{name}: n=0")
            continue
        desc = g["divergence"].describe()
        print(f"{name}: n={len(g)} media_div={desc['mean']:.4f} mediana_div={desc['50%']:.4f} "
              f"desvio={desc['std']:.4f}")
        rows.append(dict(bucket=name, n=len(g), media_divergencia=desc["mean"],
                          mediana_divergencia=desc["50%"], desvio_divergencia=desc["std"]))

    # Teste estatistico alta vs media (Mann-Whitney, nao assume normalidade;
    # + t-test de Welch como cross-check parametrico)
    if len(high) > 5 and len(med) > 5:
        u_stat, u_p = stats.mannwhitneyu(high["divergence"], med["divergence"], alternative="less")
        t_stat, t_p = stats.ttest_ind(high["divergence"], med["divergence"], equal_var=False,
                                       alternative="less")
        print(f"\nMann-Whitney U (H1: divergencia[alta] < divergencia[media]): "
              f"U={u_stat:.1f} p={u_p:.2e}")
        print(f"Welch t-test  (H1: media[alta] < media[media]): t={t_stat:.3f} p={t_p:.2e}")
        rows.append(dict(bucket="teste_mannwhitney_alta_lt_media", n=None,
                          media_divergencia=None, mediana_divergencia=None, desvio_divergencia=None,
                          estatistica=u_stat, p_valor=u_p))
        rows.append(dict(bucket="teste_welch_t_alta_lt_media", n=None,
                          media_divergencia=None, mediana_divergencia=None, desvio_divergencia=None,
                          estatistica=t_stat, p_valor=t_p))

    # ---- 2b) Versao continua (mais robusta que 2 buckets arbitrarios):
    # correlacao Spearman entre CONFIANCA (continua, 0.5-1.0) e DIVERGENCIA
    # (continua) em toda a amostra -- testa monotonicidade sem discretizar.
    conf_div_r, conf_div_p = stats.spearmanr(sub["conf"], sub["divergence"])
    print(f"\n=== Correlacao continua: confianca vs divergencia (todos os buckets, n={len(sub)}) ===")
    print(f"Spearman r={conf_div_r:.4f}  p={conf_div_p:.2e}  "
          f"({'confirma' if conf_div_r < 0 else 'NAO confirma'} hipotese: negativo = mais confianca -> menos divergencia)")
    rows.append(dict(bucket="spearman_conf_vs_divergencia_continua", n=len(sub),
                      media_divergencia=None, mediana_divergencia=None, desvio_divergencia=None,
                      estatistica=conf_div_r, p_valor=conf_div_p))

    pd.DataFrame(rows).to_csv(OUT_DIR / "confidence_divergence_buckets.csv", index=False)
    print(f"\n>> CSVs salvos em {OUT_DIR}")


if __name__ == "__main__":
    main()
