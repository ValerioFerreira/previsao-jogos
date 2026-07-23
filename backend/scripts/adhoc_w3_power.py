#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w3_power.py
==========================
Bateria ad-hoc W3 (2026-07-22), parte 3/3: dado o desvio-padrao observado do
retorno por aposta (odds reais, book "Avg", 4 ligas), quantos jogos (N)
seriam necessarios pra um teste com 80% de poder detectar um edge de ROI de
2 pontos percentuais com significancia de 5% (bicaudal)?

Formula (teste-z de 1 amostra, aproximacao padrao p/ dimensionamento de
amostra -- valida aqui porque N já é grande o bastante p/ CLT mesmo se a
distribuicao por aposta for assimetrica):

    n = (z_{alfa/2} + z_{beta})^2 * sigma^2 / delta^2

  z_{alfa/2} = 1.9600 (alfa=0.05 bicaudal)
  z_{beta}   = 0.8416 (poder=80%)
  sigma      = desvio-padrao do retorno por aposta, FRACAO do stake
               (ex.: -1.0 se perde, +odd-1 se ganha) -- estimado empiricamente
               dos dados reais (nao assumido).
  delta      = 0.02 (edge de ROI que queremos conseguir detectar)

Uso: python scripts/adhoc_w3_power.py
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
ALPHA = 0.05
POWER = 0.80
DELTA = 0.02  # edge de ROI a detectar (fracao, 2%)

Z_ALPHA_2 = stats.norm.ppf(1 - ALPHA / 2)
Z_BETA = stats.norm.ppf(POWER)

GAMES_PER_SEASON = {
    "Brasileirao": 380,  # 38 rodadas x 10 jogos (2025 teve so 306 disponiveis no dataset ate a data de corte dos dados)
    "Premier League": 380,
    "La Liga": 380,
    "Serie A Italia": 380,
}


def required_n(sigma: float, delta: float = DELTA) -> float:
    return ((Z_ALPHA_2 + Z_BETA) ** 2) * (sigma ** 2) / (delta ** 2)


def main():
    bets = pd.read_parquet(BETS)
    bets["league"] = bets["country"].map({"Brazil": "Brasileirao", "England": "Premier League",
                                           "Spain": "La Liga", "Italy": "Serie A Italia"})
    bets["frac_return"] = bets["net_return"] / STAKE  # -1 (perda) ou +odd-1 (ganho)

    print("=" * 90)
    print(f" DIMENSIONAMENTO DE AMOSTRA -- detectar edge de ROI={DELTA*100:.0f}% com poder={POWER*100:.0f}%, "
          f"alfa={ALPHA} (bicaudal)")
    print(f" z_alfa/2={Z_ALPHA_2:.4f}  z_beta={Z_BETA:.4f}  (z_alfa/2+z_beta)^2={((Z_ALPHA_2+Z_BETA)**2):.4f}")
    print("=" * 90)

    rows = []

    # 1) por estrategia, pooled (todas as ligas que tem a estrategia)
    print("\n-- sigma empirico e N necessario, por estrategia (pooled 4 ligas) --")
    for strategy, g in bets.groupby("strategy"):
        sigma = g["frac_return"].std(ddof=1)
        n_req = required_n(sigma)
        n_atual = len(g)
        rows.append(dict(nivel="estrategia_pooled", chave=strategy, sigma=sigma, n_atual=n_atual, n_necessario=n_req))
        print(f"  {strategy:14s}  sigma={sigma:.4f}  N_atual={n_atual:5d}  N_necessario(edge=2%)={n_req:9.0f}  "
              f"(faltam {max(0, n_req-n_atual):9.0f})")

    # 2) por liga (pooled todas as estrategias dessa liga -- sigma "tipico" da liga)
    print("\n-- sigma empirico e N necessario, por liga (pooled todas as estrategias) --")
    for league, g in bets.groupby("league"):
        sigma = g["frac_return"].std(ddof=1)
        n_req = required_n(sigma)
        n_atual = len(g)
        rows.append(dict(nivel="liga_pooled", chave=league, sigma=sigma, n_atual=n_atual, n_necessario=n_req))
        print(f"  {league:14s}  sigma={sigma:.4f}  N_atual={n_atual:5d}  N_necessario(edge=2%)={n_req:9.0f}  "
              f"(faltam {max(0, n_req-n_atual):9.0f})")

    # 3) grand pooled
    sigma_grand = bets["frac_return"].std(ddof=1)
    n_req_grand = required_n(sigma_grand)
    print(f"\n-- grand pooled (todas as 17 combinacoes, N={len(bets)}) --")
    print(f"  sigma={sigma_grand:.4f}  N_necessario(edge=2%)={n_req_grand:.0f}  "
          f"(faltam {max(0, n_req_grand-len(bets)):.0f} apostas)")
    rows.append(dict(nivel="grand_pooled", chave="tudo", sigma=sigma_grand, n_atual=len(bets),
                      n_necessario=n_req_grand))

    # 4) caso mais realista pro produto: uma unica estrategia x liga por vez (o jeito que o
    #    usuario realmente jogaria) -- usa sigma tipico do mercado 1x2 (favoritismo, odd~2.0)
    #    pooled entre as 3 ligas europeias (excluindo Brasileirao, que tem leakage parcial).
    euro_fav = bets[(bets.strategy == "favoritismo") & (bets.league != "Brasileirao")]
    sigma_euro_fav = euro_fav["frac_return"].std(ddof=1)
    n_req_euro_fav = required_n(sigma_euro_fav)
    n_atual_euro_fav = len(euro_fav)
    print(f"\n-- caso de referencia: favoritismo, 3 ligas europeias (sem Brasileirao, sem leakage) --")
    print(f"  sigma={sigma_euro_fav:.4f}  N_atual={n_atual_euro_fav}  N_necessario(edge=2%)={n_req_euro_fav:.0f}  "
          f"(faltam {max(0, n_req_euro_fav-n_atual_euro_fav):.0f} apostas)")
    faltam = max(0, n_req_euro_fav - n_atual_euro_fav)
    temporadas_por_liga = faltam / 3 / 380  # dividido entre as 3 ligas, 380 jogos/temporada cada
    print(f"  -> se dividido entre as 3 ligas (380 jogos/temporada cada), faltam ~{temporadas_por_liga:.1f} "
          f"temporadas ADICIONAIS por liga (~{faltam/380:.1f} temporadas se concentrado numa unica liga)")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "power_analysis.csv", index=False)
    print(f"\nCSV salvo em {OUT_DIR / 'power_analysis.csv'}")


if __name__ == "__main__":
    main()
