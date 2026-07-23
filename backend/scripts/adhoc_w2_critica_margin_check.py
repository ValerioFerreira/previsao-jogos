#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Critic check (ad-hoc, not part of w2 deliverable): is the "discordance = always
placar_exato picks D" finding a structural/mathematical necessity of how
placar_exato is derived (argmax of joint scoreline matrix collapsed to H/D/A),
rather than a substantive empirical finding? Test: are discordant games exactly
the ones where the marginal margin between the favored side (H or A) and D is
SMALLEST (i.e. "close" games where the single most-likely joint cell is a draw
scoreline even though marginal H/A mass is slightly larger)?
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"


def placar_exato_pick(pred, home, away):
    top1 = pred["placar_exato"]["top"][0]
    i, j = top1["mandante"], top1["visitante"]
    if i > j:
        return "H"
    if j > i:
        return "A"
    return "D"


def main():
    df = pd.read_parquet(DATASET)
    preds = pd.read_parquet(PREDICTIONS)

    probs = df[["p_model_H", "p_model_D", "p_model_A"]].rename(
        columns={"p_model_H": "H", "p_model_D": "D", "p_model_A": "A"})
    df["pick_favoritismo"] = probs.idxmax(axis=1)

    pred_rows = []
    for r in preds.itertuples(index=False):
        pred = json.loads(r.prediction_json)
        pred_rows.append(dict(fixture_id=r.fixture_id,
                               pick_placar_exato=placar_exato_pick(pred, r.home_team, r.away_team)))
    pe = pd.DataFrame(pred_rows)
    merged = df.merge(pe, on="fixture_id", how="left", validate="one_to_one")
    merged["discorda"] = merged["pick_favoritismo"] != merged["pick_placar_exato"]

    # margem = p_model[lado escolhido por favoritismo] - p_model_D
    # (a distancia entre o favorito marginal e o empate marginal -- se a hipotese
    # estrutural estiver certa, discordancia deve concentrar nos jogos de MENOR
    # margem, i.e. jogos "proximos" onde H (ou A) e D estao quase empatados.)
    def margin_row(row):
        fav = row["pick_favoritismo"]
        if fav == "D":
            return np.nan  # nunca acontece (favoritismo nunca escolhe D), guarda
        return row[f"p_model_{fav}"] - row["p_model_D"]

    merged["margem_fav_vs_D"] = merged.apply(margin_row, axis=1)

    print(f"N total: {len(merged)}  |  discordam: {merged['discorda'].sum()}  |  "
          f"pick_favoritismo == 'D' (deveria ser 0): {(merged['pick_favoritismo']=='D').sum()}")

    disc = merged[merged["discorda"]]
    conc = merged[~merged["discorda"]]

    print("\n=== Margem (p_model[favorito] - p_model_D) ===")
    print(f"Discordam (n={len(disc)}): media={disc['margem_fav_vs_D'].mean():.4f} "
          f"mediana={disc['margem_fav_vs_D'].median():.4f} max={disc['margem_fav_vs_D'].max():.4f} "
          f"p95={disc['margem_fav_vs_D'].quantile(.95):.4f}")
    print(f"Concordam (n={len(conc)}): media={conc['margem_fav_vs_D'].mean():.4f} "
          f"mediana={conc['margem_fav_vs_D'].median():.4f} min={conc['margem_fav_vs_D'].min():.4f} "
          f"p5={conc['margem_fav_vs_D'].quantile(.05):.4f}")

    from scipy import stats
    u_stat, u_p = stats.mannwhitneyu(disc["margem_fav_vs_D"], conc["margem_fav_vs_D"], alternative="less")
    print(f"\nMann-Whitney (H1: margem[discordam] < margem[concordam]): U={u_stat:.1f} p={u_p:.3e}")

    # overlap check: qual a margem MAXIMA entre os discordantes vs a margem MINIMA
    # entre os concordantes? Se ha overlap zero (ou quase), a fronteira e limpa =
    # e estrutural/deterministico (threshold), nao so "tendencia estatistica".
    print(f"\nMax margem entre discordantes: {disc['margem_fav_vs_D'].max():.4f}")
    print(f"Min margem entre concordantes: {conc['margem_fav_vs_D'].min():.4f}")
    overlap = ((disc['margem_fav_vs_D'].values[:, None] > conc['margem_fav_vs_D'].values[None, :]).mean())
    # (comentado: pode ser caro em memoria -- N grande. Vamos so contar quantos
    # discordantes tem margem MAIOR que a mediana dos concordantes, e vice-versa)
    thr_conc_median = conc['margem_fav_vs_D'].median()
    pct_disc_above_concmedian = (disc['margem_fav_vs_D'] > thr_conc_median).mean() * 100
    print(f"% de discordantes com margem > mediana dos concordantes ({thr_conc_median:.4f}): "
          f"{pct_disc_above_concmedian:.2f}%")

    # histograma rapido em texto (deciles)
    print("\nDecis da margem -- discordam vs concordam:")
    qs = [0, .1, .25, .5, .75, .9, 1.0]
    print("discordam:", [round(disc['margem_fav_vs_D'].quantile(q), 4) for q in qs])
    print("concordam:", [round(conc['margem_fav_vs_D'].quantile(q), 4) for q in qs])

    # Verificacao adicional: sera que HA algum caso, em qualquer parte do dataset,
    # de favoritismo=H e placar_exato=A (ou vice-versa) tao raro que nao aparece
    # nos 8117 jogos mas poderia em tese? Vamos conferir a distancia MINIMA entre
    # margem de discordantes tipo H e a distribuicao geral -- ja fizemos no crosstab
    # do script original (zero casos). Aqui so quantificamos "quao perto da fronteira".
    print("\n=== Por lado do favorito (H vs A) ===")
    for lado in ["H", "A"]:
        d = disc[disc["pick_favoritismo"] == lado]
        c = conc[conc["pick_favoritismo"] == lado]
        print(f"[{lado}] discordam n={len(d)} margem_media={d['margem_fav_vs_D'].mean():.4f} "
              f"max={d['margem_fav_vs_D'].max():.4f} | concordam n={len(c)} "
              f"margem_media={c['margem_fav_vs_D'].mean():.4f} min={c['margem_fav_vs_D'].min():.4f}")


if __name__ == "__main__":
    main()
