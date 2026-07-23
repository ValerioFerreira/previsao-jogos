#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w2_threshold_sweep.py
====================================
Bateria ad-hoc "w2" (2026-07-22), pergunta 2: restringir a estrategia
"modelo escolhe" (O/U 2,5 -- aposta no lado que o modelo da mais probabilidade)
SO aos casos de alta divergencia |p_model_over - p_fair_open_over| melhora o
ROI vs a estrategia cega original (aposta em TODO jogo)?

Metodologia (pedido do dono, cuidado com overfitting de limiar):
  1. Split CRONOLOGICO 50/50 por data (mais antiga = treino p/ escolher o
     limiar que maximiza ROI; mais recente = validacao, limiar fixo aplicado
     sem re-otimizar).
  2. Sweep de limiares 0.00-0.16 (passo 0.01, cobre ate ~p99 da divergencia
     observada).
  3. PLACEBO -- pra cada limiar escolhido no treino, gera distribuicao nula
     de ROI escolhendo N apostas ALEATORIAS (mesmo N que o limiar produziu)
     do pool de treino, 5000 repeticoes. Se o ROI do limiar "vencedor" nao
     escapar dessa distribuicao nula, e apenas reducao de variancia por N
     menor (artefato), nao sinal real.
  4. Split REVERSO (treino=metade recente, valida=metade antiga) como
     contraprova de robustez.

So usa fixtures com odd_open_over/odd_open_under E p_fair_open_over
presentes (4955/8117 -- unico jeito de ter ROI real E divergencia vs abertura
juntos). Nao mexe em model_artifacts/predictor.py/app real.

Saida: prints + `data/reports/adhoc_valuebet_w2/threshold_sweep_train.csv`,
`..._test.csv`, `..._reverse_train.csv`, `..._reverse_test.csv`,
`..._placebo.csv`.

Uso: python scripts/adhoc_w2_threshold_sweep.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
OUT_DIR = ROOT / "data" / "reports" / "adhoc_valuebet_w2"

STAKE = 1.0
THRESHOLDS = np.round(np.arange(0.00, 0.17, 0.01), 2)
MIN_N = 30  # guarda minima de amostra p/ um limiar ser considerado no treino
RNG_SEED = 42
N_PLACEBO = 5000


def summarize(bets: pd.DataFrame) -> dict:
    n = len(bets)
    if n == 0:
        return dict(n=0, win_rate=None, roi_pct=None, lucro=None)
    wins = int(bets["won"].sum())
    retorno = float((bets["won"] * bets["odd"] * STAKE).sum())
    stake_total = n * STAKE
    lucro = retorno - stake_total
    return dict(n=n, win_rate=round(100 * wins / n, 2), roi_pct=round(100 * lucro / stake_total, 2),
                lucro=round(lucro, 2))


def build_bets(df: pd.DataFrame) -> pd.DataFrame:
    """Estrategia 'modelo escolhe': aposta no lado (over/under) que o modelo
    da mais probabilidade, TODO jogo (estrategia cega original). odd/won por
    linha; 'divergence' = |p_model_over - p_fair_open_over| pra filtrar depois."""
    chosen_over = df["p_model_over"] >= 0.5
    out = pd.DataFrame({
        "fixture_id": df["fixture_id"].values,
        "date": df["date"].values,
        "chosen": np.where(chosen_over, "over", "under"),
        "odd": np.where(chosen_over, df["odd_open_over"], df["odd_open_under"]),
        "won": np.where(chosen_over, df["actual_over"], ~df["actual_over"]),
        "divergence": (df["p_model_over"] - df["p_fair_open_over"]).abs().values,
    })
    return out


def sweep(bets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for thr in THRESHOLDS:
        sel = bets[bets["divergence"] > thr]
        s = summarize(sel)
        rows.append(dict(limiar=thr, **s))
    return pd.DataFrame(rows)


def placebo_test(pool: pd.DataFrame, n_bets: int, observed_roi: float, seed: int) -> dict:
    """Distribuicao nula: escolhe n_bets ALEATORIOS do pool (sem olhar
    divergencia) N_PLACEBO vezes, calcula ROI de cada amostra. Se o ROI
    observado (limiar escolhido) nao for extremo vs essa distribuicao nula,
    e reducao de N (variancia), nao sinal de divergencia."""
    if n_bets == 0 or n_bets > len(pool):
        return dict(n_bets=n_bets, observed_roi=observed_roi, null_mean=None, null_std=None,
                     percentile_observado=None, p_value_two_sided=None)
    rng = np.random.default_rng(seed)
    rois = np.empty(N_PLACEBO)
    won = pool["won"].to_numpy()
    odd = pool["odd"].to_numpy()
    n_pool = len(pool)
    for i in range(N_PLACEBO):
        idx = rng.choice(n_pool, size=n_bets, replace=False)
        w = won[idx]
        o = odd[idx]
        retorno = (w * o * STAKE).sum()
        stake_total = n_bets * STAKE
        rois[i] = 100 * (retorno - stake_total) / stake_total
    pct = float((rois < observed_roi).mean() * 100)
    p_two_sided = float(2 * min(pct, 100 - pct) / 100)
    return dict(n_bets=n_bets, observed_roi=observed_roi, null_mean=round(float(rois.mean()), 3),
                null_std=round(float(rois.std()), 3), percentile_observado=round(pct, 1),
                p_value_two_sided=round(p_two_sided, 4))


def run_split(bets: pd.DataFrame, train_is_early: bool, label: str):
    bets_sorted = bets.sort_values(["date", "fixture_id"]).reset_index(drop=True)
    mid = len(bets_sorted) // 2
    if train_is_early:
        train, test = bets_sorted.iloc[:mid], bets_sorted.iloc[mid:]
    else:
        train, test = bets_sorted.iloc[mid:], bets_sorted.iloc[:mid]

    print(f"\n{'='*70}\n SPLIT: {label} (treino n={len(train)}, teste n={len(test)})\n{'='*70}")
    print(f"Treino: {train['date'].min()} .. {train['date'].max()}")
    print(f"Teste:  {test['date'].min()} .. {test['date'].max()}")

    base_train = summarize(train)
    base_test = summarize(test)
    print(f"\nBaseline CEGO (limiar=0, todo jogo):")
    print(f"  Treino: n={base_train['n']} win%={base_train['win_rate']} ROI%={base_train['roi_pct']}")
    print(f"  Teste:  n={base_test['n']} win%={base_test['win_rate']} ROI%={base_test['roi_pct']}")

    sweep_train = sweep(train)
    sweep_test = sweep(test)
    print("\nSweep de limiares -- TREINO:")
    print(sweep_train.to_string(index=False))
    print("\nSweep de limiares -- TESTE (usando os MESMOS limiares, sem re-otimizar):")
    print(sweep_test.to_string(index=False))

    sweep_train.to_csv(OUT_DIR / f"threshold_sweep_{label}_train.csv", index=False)
    sweep_test.to_csv(OUT_DIR / f"threshold_sweep_{label}_test.csv", index=False)

    # Escolhe o limiar que MAXIMIZA ROI no treino, com guarda de N minimo.
    valid = sweep_train[sweep_train["n"] >= MIN_N]
    if len(valid) == 0:
        print(f"\n[{label}] Nenhum limiar com n>={MIN_N} no treino -- sem limiar escolhido.")
        return None
    best_row = valid.loc[valid["roi_pct"].idxmax()]
    best_thr = best_row["limiar"]
    print(f"\n[{label}] Limiar escolhido no TREINO (max ROI, n>={MIN_N}): {best_thr} "
          f"(treino: n={int(best_row['n'])} ROI={best_row['roi_pct']}%)")

    test_at_best = sweep_test[sweep_test["limiar"] == best_thr].iloc[0]
    print(f"[{label}] Mesmo limiar aplicado no TESTE (fora da amostra): "
          f"n={int(test_at_best['n'])} win%={test_at_best['win_rate']} ROI%={test_at_best['roi_pct']}")

    # Placebo -- treino
    placebo_train = placebo_test(train, int(best_row["n"]), best_row["roi_pct"], seed=RNG_SEED)
    print(f"[{label}] PLACEBO treino (N={placebo_train['n_bets']} apostas aleatorias, "
          f"{N_PLACEBO} repeticoes): ROI nulo media={placebo_train['null_mean']}% "
          f"desvio={placebo_train['null_std']}% | ROI observado={placebo_train['observed_roi']}% "
          f"esta no percentil {placebo_train['percentile_observado']} da nula "
          f"(p bicaudal={placebo_train['p_value_two_sided']})")

    # Placebo -- teste (mesmo N do teste-no-limiar, comparado ao pool de teste)
    if not pd.isna(test_at_best["n"]) and test_at_best["n"] > 0:
        placebo_test_ = placebo_test(test, int(test_at_best["n"]), test_at_best["roi_pct"], seed=RNG_SEED + 1)
        print(f"[{label}] PLACEBO teste (N={placebo_test_['n_bets']} apostas aleatorias): "
              f"ROI nulo media={placebo_test_['null_mean']}% desvio={placebo_test_['null_std']}% | "
              f"ROI observado={placebo_test_['observed_roi']}% esta no percentil "
              f"{placebo_test_['percentile_observado']} da nula (p bicaudal={placebo_test_['p_value_two_sided']})")
    else:
        placebo_test_ = dict(n_bets=0, observed_roi=None, null_mean=None, null_std=None,
                              percentile_observado=None, p_value_two_sided=None)

    pd.DataFrame([
        dict(split=label, fase="treino", limiar=best_thr, **placebo_train),
        dict(split=label, fase="teste", limiar=best_thr, **placebo_test_),
    ]).to_csv(OUT_DIR / f"threshold_placebo_{label}.csv", index=False)

    return dict(label=label, best_thr=best_thr, base_train=base_train, base_test=base_test,
                train_at_best=dict(n=int(best_row["n"]), win_rate=best_row["win_rate"], roi_pct=best_row["roi_pct"]),
                test_at_best=dict(n=int(test_at_best["n"]), win_rate=test_at_best["win_rate"], roi_pct=test_at_best["roi_pct"]),
                placebo_train=placebo_train, placebo_test=placebo_test_)


def main():
    df = pd.read_parquet(DATASET)
    sub = df[df["odd_open_over"].notna() & df["odd_open_under"].notna() & df["p_fair_open_over"].notna()].copy()
    print(f"Fixtures com odd_open_over/under E p_fair_open_over: {len(sub)}/{len(df)}")

    bets = build_bets(sub)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    r1 = run_split(bets, train_is_early=True, label="cronologico")
    r2 = run_split(bets, train_is_early=False, label="reverso")
    for r in (r1, r2):
        if r:
            results.append(r)

    print("\n" + "=" * 70)
    print(" RESUMO FINAL")
    print("=" * 70)
    for r in results:
        print(f"\n[{r['label']}] limiar escolhido no treino: {r['best_thr']}")
        print(f"  Baseline cego  -- treino ROI={r['base_train']['roi_pct']}% (n={r['base_train']['n']}) | "
              f"teste ROI={r['base_test']['roi_pct']}% (n={r['base_test']['n']})")
        print(f"  C/ limiar      -- treino ROI={r['train_at_best']['roi_pct']}% (n={r['train_at_best']['n']}) | "
              f"teste ROI={r['test_at_best']['roi_pct']}% (n={r['test_at_best']['n']})")
        melhora_test = (r['test_at_best']['roi_pct'] or 0) - (r['base_test']['roi_pct'] or 0)
        print(f"  Melhora OOS (teste c/limiar - teste cego): {melhora_test:+.2f} p.p.")


if __name__ == "__main__":
    main()
