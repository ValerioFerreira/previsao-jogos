#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w1_critica_fixed_shin.py
========================================
Achado da AUDITORIA critica do relatorio adhoc_valuebet_w1: `shin_devig()` em
`scripts/devig_methods.py` tem um bug de formula (usa pn=pi/S depois pn**2,
ou seja pi^2/S^2, em vez da formula correta pi^2/S com pi = prob. implicita
CRUA/nao-normalizada) que faz o brentq NUNCA achar raiz em (1e-9, 0.4) para
qualquer overround realista --Resultado: shin_devig() cai SEMPRE (99.98% dos
jogos 1x2, 100% do O/U 2,5 na amostra real) no fallback `except ValueError:
return power_devig(odds)`, ou seja, a coluna "shin" do relatorio original e
uma DUPLICATA BYTE-A-BYTE de "power", nao um metodo independente.

Este script implementa a formula CORRIGIDA (Shin genuino, closed-form padrao
da literatura: p_i(z) = (sqrt(z^2 + 4(1-z)*pi_i^2/S) - z) / (2(1-z)) com
pi_i = 1/odds_i CRU, S = soma(pi_i)) e reroda a MESMA analise (edge, sweep de
limiar, split cronologico treino/teste, bootstrap) pra checar se a conclusao
do relatorio original muda quando se usa Shin de verdade em vez do
power_devig disfarçado.

NAO modifica devig_methods.py nem relatorio.md originais -- achado documentado
em critica.md.

Uso: python scripts/adhoc_w1_critica_fixed_shin.py
"""
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from devig_methods import proportional_devig, power_devig  # noqa: E402

spec = importlib.util.spec_from_file_location("w1bt", ROOT / "scripts" / "adhoc_w1_valuebet_backtest.py")
w1bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w1bt)

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
STAKE = w1bt.STAKE
THRESHOLDS = w1bt.THRESHOLDS


def shin_devig_fixed(odds: list[float], tol: float = 1e-12):
    """Formula corrigida do Shin: pi_i^2/S (pi CRU, um fator de S), nao (pi/S)^2
    como no devig_methods.py original. Mesma logica de fallback (overround<=0
    -> proporcional; brentq falha -> power) preservada por consistencia, mas
    aqui o fallback deve ser RARO (nao sistematico)."""
    pi = np.array([1.0 / o for o in odds])
    S = pi.sum()

    def f(z):
        inside = z ** 2 + 4.0 * (1.0 - z) * (pi ** 2) / S
        p = (np.sqrt(np.maximum(inside, 0.0)) - z) / (2.0 * (1.0 - z))
        return p.sum() - 1.0

    overround = S - 1.0
    if overround <= 1e-9:
        return proportional_devig(odds), "proporcional_fallback"
    try:
        z = brentq(f, 1e-9, 0.4, xtol=tol)
    except ValueError:
        try:
            return power_devig(odds), "power_fallback"
        except Exception:
            return None, "erro"
    inside = z ** 2 + 4.0 * (1.0 - z) * (pi ** 2) / S
    p = (np.sqrt(np.maximum(inside, 0.0)) - z) / (2.0 * (1.0 - z))
    p = np.clip(p, 1e-9, None)
    return list(p / p.sum()), "shin_genuino"


def build_with_fixed_shin(market):
    df_all = pd.read_parquet(DATASET)
    spec_m = w1bt.MARKETS[market]
    sides = spec_m["sides"]
    odd_cols = [f"odd_open_{s}" for s in sides]
    df = df_all[df_all[odd_cols].notna().all(axis=1)].copy()

    out = {s: np.full(len(df), np.nan) for s in sides}
    path_counts = {}
    for pos, (_, row) in enumerate(df.iterrows()):
        odds = [row[c] for c in odd_cols]
        p, path = shin_devig_fixed(odds)
        path_counts[path] = path_counts.get(path, 0) + 1
        if p is None:
            continue
        for s, pv in zip(sides, p):
            out[s][pos] = pv
    for s in sides:
        df[f"p_fair_open_{s}__shinfixed"] = out[s]

    df = w1bt.chosen_side_and_actual(df, market)
    fair_chosen = [df.at[i, f"p_fair_open_{s}__shinfixed"] for i, s in zip(df.index, df["chosen_side"])]
    df["edge__shinfixed"] = df["p_model_chosen"].to_numpy() - np.array(fair_chosen, dtype=float)
    return df, path_counts


def run_full_pipeline(df, ecol):
    sub = df[df[ecol].notna()].copy()
    sweep_full = w1bt.threshold_sweep(sub, ecol)
    train, test = w1bt.chronological_split(sub)
    sweep_train = w1bt.threshold_sweep(train, ecol)
    best_th = w1bt.pick_best_threshold(sweep_train)
    train_at_best = w1bt.threshold_sweep(train, ecol, thresholds=[best_th]).iloc[0].to_dict() if best_th is not None else None
    test_at_best = w1bt.threshold_sweep(test, ecol, thresholds=[best_th]).iloc[0].to_dict() if best_th is not None else None
    boot_test = w1bt.bootstrap_roi_ci(test, ecol, best_th) if best_th is not None else None
    return dict(sweep_full=sweep_full, sweep_train=sweep_train, best_th=best_th,
                train_at_best=train_at_best, test_at_best=test_at_best, boot_test=boot_test,
                n_train=len(train), n_test=len(test))


def main():
    for market in ("1x2", "ou25"):
        print(f"\n{'='*70}\nMERCADO {market} -- Shin CORRIGIDO vs power vs proporcional (buggy shin==power)\n{'='*70}")
        df, path_counts = build_with_fixed_shin(market)
        n = len(df)
        print(f"Caminhos de resolucao do Shin CORRIGIDO (n={n}):")
        for k, v in path_counts.items():
            print(f"  {k}: {v} ({v/n*100:.2f}%)")

        res = run_full_pipeline(df, "edge__shinfixed")
        print(f"\nSweep completo (in-sample, todos limiares) -- SHIN CORRIGIDO:")
        print(res["sweep_full"].to_string(index=False))
        print(f"\nSweep treino -- SHIN CORRIGIDO:")
        print(res["sweep_train"].to_string(index=False))
        print(f"\nLimiar escolhido no treino: {res['best_th']}")
        if res["train_at_best"]:
            tb, te = res["train_at_best"], res["test_at_best"]
            print(f"Treino: n={tb['n']}, hit_rate={tb['hit_rate']:.4f}, roi={tb['roi']:.4f}")
            print(f"TESTE : n={te['n']}, hit_rate={te['hit_rate']:.4f}, roi={te['roi']:.4f}")
            bt = res["boot_test"]
            print(f"Bootstrap IC95% teste: [{bt['roi_lo']*100:.2f}%, {bt['roi_hi']*100:.2f}%]")

        # comparacao direta: quantas fixtures tem edge__shinfixed bem diferente de edge__power?
        # (recalcula power localmente pra comparar)
        spec_m = w1bt.MARKETS[market]
        sides = spec_m["sides"]
        odd_cols = [f"odd_open_{s}" for s in sides]
        power_fair = {s: np.full(len(df), np.nan) for s in sides}
        for pos, (_, row) in enumerate(df.iterrows()):
            odds = [row[c] for c in odd_cols]
            try:
                p = power_devig(odds)
            except Exception:
                continue
            for s, pv in zip(sides, p):
                power_fair[s][pos] = pv
        fair_power_chosen = np.array([power_fair[s][pos] for pos, s in enumerate(df["chosen_side"])])
        edge_power = df["p_model_chosen"].to_numpy() - fair_power_chosen
        edge_shinfixed = df["edge__shinfixed"].to_numpy()
        diff = np.abs(edge_power - edge_shinfixed)
        valid = ~np.isnan(diff)
        print(f"\nDiferenca media |edge_power - edge_shin_corrigido| = {np.nanmean(diff):.5f} "
              f"(max={np.nanmax(diff):.5f}, n_valid={valid.sum()})")
        print(f"Correlacao edge_power vs edge_shin_corrigido: {np.corrcoef(edge_power[valid], edge_shinfixed[valid])[0,1]:.4f}")


if __name__ == "__main__":
    main()
