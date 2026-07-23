#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w1_critica_investigation.py
==========================================
Script de AUDITORIA (critico/adversario) do relatorio W1
(data/reports/adhoc_valuebet_w1/relatorio.md, gerado por
adhoc_w1_valuebet_backtest.py). NAO reescreve o relatorio original, NAO toca
model_artifacts*/predictor.py/app real -- so re-analisa o mesmo dataset/logica
pra tentar achar furos na conclusao "nao ha edge de valor".

Investiga:
  1. ROI/hit-rate por BUCKET de edge NAO-CUMULATIVO (o relatorio so mostra
     sweep cumulativo edge>limiar, que sao amostras aninhadas -- quero
     confirmar se a piora e real bucket-a-bucket, nao so um artefato do
     corte cumulativo).
  2. Perfil de odd do "chosen_side" nos buckets de edge alto vs baixo --
     testa a hipotese "de-vig degenera em odds extremas" (favorito
     fortissimo ou zebra fortissima).
  3. Diagnostico numerico do Shin: fracao de jogos onde o solver bate no
     limite superior de busca (z perto de 0.4) -- sinal de degenerescencia.
  4. Estrategia alternativa: apostar no lado de MAIOR EDGE ABSOLUTO (nao
     necessariamente o "favorito do modelo"/argmax p_model) -- ve se o
     padrao degenerado persiste quando se rompe a dependencia com
     "concordar com o favorito do book".
  5. Bootstrap CI por bucket de edge (nao cumulativo) pra checar se a
     "piora com o edge" e estatisticamente distinguivel de ruido dado o N
     de cada bucket.

Uso: python scripts/adhoc_w1_critica_investigation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from devig_methods import proportional_devig, power_devig, shin_devig  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

# reusa a logica original sem duplicar
import importlib.util
spec = importlib.util.spec_from_file_location("w1bt", ROOT / "scripts" / "adhoc_w1_valuebet_backtest.py")
w1bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w1bt)

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
STAKE = w1bt.STAKE

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)


def build_df(market):
    df_all = pd.read_parquet(DATASET)
    spec_m = w1bt.MARKETS[market]
    odd_cols = [f"odd_open_{s}" for s in spec_m["sides"]]
    df = df_all[df_all[odd_cols].notna().all(axis=1)].copy()
    df = w1bt.add_fair_open_all_methods(df, market)
    df = w1bt.chosen_side_and_actual(df, market)
    df = w1bt.add_edges(df, market)
    return df


# ────────────────────────── 1. buckets NAO-cumulativos ──────────────────────────
def noncumulative_bucket_roi(df, edge_col, bins, labels):
    d = df[df[edge_col].notna()].copy()
    d["bucket"] = pd.cut(d[edge_col], bins=bins, labels=labels, right=False)
    rows = []
    for b in labels:
        sub = d[d["bucket"] == b]
        n = len(sub)
        if n == 0:
            rows.append(dict(bucket=b, n=0, hit_rate=np.nan, roi=np.nan, odd_media=np.nan))
            continue
        win = (sub["chosen_side"] == sub["actual_side"])
        profit = w1bt.bet_outcomes(sub).sum()
        rows.append(dict(bucket=b, n=n, hit_rate=win.mean(), roi=profit / (n * STAKE),
                          odd_media=sub["odd_open_chosen"].mean()))
    return pd.DataFrame(rows)


def bootstrap_roi_noncum(df, edge_col, bins, labels, n_boot=3000, seed=99):
    d = df[df[edge_col].notna()].copy()
    d["bucket"] = pd.cut(d[edge_col], bins=bins, labels=labels, right=False)
    rng = np.random.default_rng(seed)
    rows = []
    for b in labels:
        sub = d[d["bucket"] == b]
        n = len(sub)
        if n < 5:
            rows.append(dict(bucket=b, n=n, roi=np.nan, roi_lo=np.nan, roi_hi=np.nan))
            continue
        profits = w1bt.bet_outcomes(sub).to_numpy()
        boots = np.empty(n_boot)
        for i in range(n_boot):
            s = rng.choice(profits, size=n, replace=True)
            boots[i] = s.sum() / (n * STAKE)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        rows.append(dict(bucket=b, n=n, roi=profits.sum() / (n * STAKE), roi_lo=lo, roi_hi=hi))
    return pd.DataFrame(rows)


# ────────────────────────── 2. perfil de odd por bucket ──────────────────────────
def odd_profile_by_bucket(df, edge_col, bins, labels):
    d = df[df[edge_col].notna()].copy()
    d["bucket"] = pd.cut(d[edge_col], bins=bins, labels=labels, right=False)
    rows = []
    for b in labels:
        sub = d[d["bucket"] == b]
        n = len(sub)
        if n == 0:
            continue
        odd = sub["odd_open_chosen"]
        # classifica: favorito forte (odd<1.5), favorito medio (1.5-2.5), zebra media (2.5-4), zebra forte (>4)
        cat_counts = pd.cut(odd, bins=[0, 1.5, 2.5, 4.0, np.inf],
                             labels=["fav_forte(<1.5)", "fav_medio(1.5-2.5)", "zebra_media(2.5-4)", "zebra_forte(>4)"]
                             ).value_counts(normalize=True).reindex(
            ["fav_forte(<1.5)", "fav_medio(1.5-2.5)", "zebra_media(2.5-4)", "zebra_forte(>4)"]).fillna(0.0)
        rows.append(dict(bucket=b, n=n, odd_min=odd.min(), odd_p25=odd.quantile(.25),
                          odd_mediana=odd.median(), odd_p75=odd.quantile(.75), odd_max=odd.max(),
                          **{f"frac_{k}": v for k, v in cat_counts.items()}))
    return pd.DataFrame(rows)


# ────────────────────────── 3. diagnostico Shin (z perto do limite) ──────────────────────────
def shin_z_diagnostics(df, market):
    spec_m = w1bt.MARKETS[market]
    sides = spec_m["sides"]
    odd_cols = [f"odd_open_{s}" for s in sides]
    zs = []
    overrounds = []
    fallback_power = 0
    for _, row in df.iterrows():
        odds = [row[c] for c in odd_cols]
        pi = np.array([1.0 / o for o in odds])
        S = pi.sum()
        overround = S - 1.0
        overrounds.append(overround)
        if overround <= 1e-9:
            zs.append(np.nan)
            continue

        def f(z):
            pn = pi / S
            inside = z ** 2 + 4.0 * (1.0 - z) * (pn ** 2)
            p = (np.sqrt(np.maximum(inside, 0.0)) - z) / (2.0 * (1.0 - z))
            return p.sum() - 1.0
        try:
            z = brentq(f, 1e-9, 0.4, xtol=1e-12)
            zs.append(z)
        except ValueError:
            zs.append(np.nan)
            fallback_power += 1
    df = df.copy()
    df["_shin_z"] = zs
    df["_overround"] = overrounds
    near_bound = (df["_shin_z"] > 0.39).sum()
    print(f"  [shin diag {market}] overround medio={np.nanmean(overrounds):.4f}, "
          f"z medio={np.nanmean(zs):.4f}, z>0.39 (perto do limite 0.4): {near_bound}/{len(df)}, "
          f"falhas->power fallback: {fallback_power}")
    return df


# ────────────────────────── 4. estrategia alternativa: maior edge absoluto ──────────────────────────
def chosen_by_max_edge(df, market, method):
    """Recalcula 'chosen_side' como argmax(p_model_s - p_fair_open_s__method) em vez de
    argmax(p_model_s). Pode escolher um lado DIFERENTE do favorito do modelo."""
    spec_m = w1bt.MARKETS[market]
    sides = spec_m["sides"]
    model_cols = [spec_m["model_cols"][s] for s in sides]
    fair_cols = [f"p_fair_open_{s}__{method}" for s in sides]
    d = df.copy()
    edge_matrix = d[model_cols].to_numpy() - d[fair_cols].to_numpy()
    idx_max = edge_matrix.argmax(axis=1)
    d["chosen_side_maxedge"] = [sides[i] for i in idx_max]
    d["edge_maxedge"] = edge_matrix[np.arange(len(d)), idx_max]
    d["odd_open_maxedge"] = [d.at[i, f"odd_open_{s}"] for i, s in zip(d.index, d["chosen_side_maxedge"])]
    d["differs_from_model_favorite"] = d["chosen_side_maxedge"] != d["chosen_side"]
    return d


def backtest_maxedge(d, market):
    win = (d["chosen_side_maxedge"] == d["actual_side"])
    profit = np.where(win, STAKE * (d["odd_open_maxedge"] - 1.0), -STAKE)
    return profit


def sweep_maxedge(d, thresholds=w1bt.THRESHOLDS):
    rows = []
    for th in thresholds:
        sub = d[d["edge_maxedge"] > th]
        n = len(sub)
        if n == 0:
            rows.append(dict(limiar=th, n=0, hit_rate=np.nan, roi=np.nan))
            continue
        win = (sub["chosen_side_maxedge"] == sub["actual_side"])
        profit = backtest_maxedge(sub, None).sum()
        rows.append(dict(limiar=th, n=n, hit_rate=win.mean(), roi=profit / (n * STAKE)))
    return pd.DataFrame(rows)


def main():
    print("=" * 90)
    print("AUDITORIA W1 -- investigacao critica do relatorio adhoc_valuebet_w1")
    print("=" * 90)

    bins = [-np.inf, 0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, np.inf]
    labels = ["<0%", "0-1%", "1-2%", "2-3%", "3-5%", "5-8%", "8-10%", ">10%"]

    for market in ("1x2", "ou25"):
        print(f"\n\n########## MERCADO {market} ##########")
        df = build_df(market)

        for method in ("shin",):  # foco no metodo usado no relatorio p/ CLV/breakdown
            ecol = w1bt.edge_col_name(method)
            sub = df[df[ecol].notna()].copy()

            print(f"\n--- [{method}] 1. ROI por bucket de edge NAO-cumulativo ---")
            tab = noncumulative_bucket_roi(sub, ecol, bins, labels)
            print(tab.to_string(index=False))

            print(f"\n--- [{method}] 1b. Bootstrap CI (95%) por bucket NAO-cumulativo ---")
            tab_boot = bootstrap_roi_noncum(sub, ecol, bins, labels)
            print(tab_boot.to_string(index=False))

            print(f"\n--- [{method}] 2. Perfil de odd do chosen_side por bucket de edge ---")
            prof = odd_profile_by_bucket(sub, ecol, bins, labels)
            print(prof.to_string(index=False))

        print(f"\n--- 3. Diagnostico numerico Shin (overround / z) ---")
        shin_z_diagnostics(df, market)

        print(f"\n--- 4. Estrategia alternativa: maior edge absoluto (shin) ---")
        d_me = chosen_by_max_edge(sub, market, "shin")
        print(f"  Difere do favorito do modelo (argmax p_model) em {d_me['differs_from_model_favorite'].mean()*100:.2f}% dos jogos")
        train, test = w1bt.chronological_split(d_me)
        sweep_train_me = sweep_maxedge(train)
        print("  Sweep treino (max-edge):")
        print(sweep_train_me.to_string(index=False))
        # escolhe limiar por ROI treino (>=30 apostas), aplica no teste
        elig = sweep_train_me[sweep_train_me["n"] >= 30]
        if not elig.empty:
            best = elig.sort_values(["roi", "limiar"], ascending=[False, True]).iloc[0]
            best_th = float(best["limiar"])
            test_sweep = sweep_maxedge(test, thresholds=[best_th])
            print(f"  Limiar escolhido (treino, max-edge): {best_th*100:.1f}%")
            print("  Resultado teste (max-edge, limiar fixo):")
            print(test_sweep.to_string(index=False))
        else:
            print("  Sem limiar elegivel.")

    print("\n\nFIM DA AUDITORIA")


if __name__ == "__main__":
    main()
