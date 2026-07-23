#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w2_discordance_edge.py
=====================================
Bateria ad-hoc "w2" (2026-07-22), pergunta 3: na base COMPLETA (8117 fixtures,
todas as ligas), quantifica a discordancia entre os picks "favoritismo"
(argmax H/D/A) e "placar_exato" (H/D/A derivado do placar top-1 da matriz
conjunta) e testa a hipotese de que, quando os dois DIVERGEM, o pick de
placar_exato tende a pegar o lado de MAIS valor (maior edge model-vs-mercado)
que o de favoritismo -- explicacao candidata pro achado da analise anterior
(placar_exato acerta menos mas perde MENOS dinheiro que favoritismo).

Edge de um lado = p_model_lado - p_fair_open_lado (positivo = modelo acha o
lado mais provavel do que o mercado de-vigado (Shin) acha). So calculavel
onde odd_open_H/D/A E p_fair_open_H/D/A existem (~4955/8117).

Nao mexe em model_artifacts/predictor.py/app real. Pesquisa/produto, nao gate.

Saida: prints + `data/reports/adhoc_valuebet_w2/discordance_summary.csv` e
`..._edge_paired.csv` (uma linha por fixture discordante, p/ auditoria).

Uso: python scripts/adhoc_w2_discordance_edge.py
"""
from __future__ import annotations

import json
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
PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
OUT_DIR = ROOT / "data" / "reports" / "adhoc_valuebet_w2"

STAKE = 1.0


def placar_exato_pick(pred: dict, home: str, away: str) -> str:
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Dataset valuebet: {len(df)} fixtures | predictions: {len(preds)} fixtures")

    # ---- picks ----
    df["pick_favoritismo"] = np.select(
        [df["p_model_H"] >= df[["p_model_H", "p_model_D", "p_model_A"]].max(axis=1),
         df["p_model_D"] >= df[["p_model_H", "p_model_D", "p_model_A"]].max(axis=1)],
        ["H", "D"], default="A",
    )
    # np.select acima com >= em duas condicoes pode marcar H mesmo quando D e o
    # max e H empata por float -- refaz de forma inambigua com idxmax por linha.
    probs = df[["p_model_H", "p_model_D", "p_model_A"]].rename(
        columns={"p_model_H": "H", "p_model_D": "D", "p_model_A": "A"})
    df["pick_favoritismo"] = probs.idxmax(axis=1)

    pred_rows = []
    for r in preds.itertuples(index=False):
        pred = json.loads(r.prediction_json)
        pred_rows.append(dict(fixture_id=r.fixture_id,
                               pick_placar_exato=placar_exato_pick(pred, r.home_team, r.away_team)))
    pe = pd.DataFrame(pred_rows)
    print(f"placar_exato extraido: {len(pe)} linhas (dedup fixture_id: {pe['fixture_id'].nunique()})")

    merged = df.merge(pe, on="fixture_id", how="left", validate="one_to_one")
    assert merged["pick_placar_exato"].notna().all(), "fixture sem placar_exato -- merge quebrado"

    # ---- 1) taxa de discordancia na base completa ----
    merged["discorda"] = merged["pick_favoritismo"] != merged["pick_placar_exato"]
    n_total = len(merged)
    n_disc = int(merged["discorda"].sum())
    print(f"\n=== Discordancia favoritismo vs placar_exato (base completa, N={n_total}) ===")
    print(f"Discordam: {n_disc}/{n_total} ({100*n_disc/n_total:.2f}%)")
    print(f"Concordam: {n_total-n_disc}/{n_total} ({100*(n_total-n_disc)/n_total:.2f}%)")

    # taxa de acerto de cada estrategia, geral e por concordancia/discordancia (contexto)
    for grp_name, grp in (("geral", merged), ("concordam", merged[~merged["discorda"]]),
                          ("discordam", merged[merged["discorda"]])):
        acc_fav = (grp["pick_favoritismo"] == grp["actual_result"]).mean()
        acc_pe = (grp["pick_placar_exato"] == grp["actual_result"]).mean()
        print(f"  [{grp_name}, n={len(grp)}] acc favoritismo={100*acc_fav:.1f}%  acc placar_exato={100*acc_pe:.1f}%")

    summary_rows = [dict(metrica="n_total", valor=n_total),
                     dict(metrica="n_discordam", valor=n_disc),
                     dict(metrica="pct_discordam", valor=round(100*n_disc/n_total, 2))]

    # ---- 2) edge medio do lado escolhido (favoritismo vs placar_exato) nos
    # jogos de DISCORDANCIA, restrito a quem tem odd_open_H/D/A E
    # p_fair_open_H/D/A (nao infere) ----
    has_odds = merged["p_fair_open_H"].notna() & merged["odd_open_H"].notna()
    disc = merged[merged["discorda"] & has_odds].copy()
    print(f"\n=== Edge nos jogos de DISCORDANCIA com odds de abertura disponivel: {len(disc)}/{n_disc} ===")

    def edge_of(row, side_col):
        side = row[side_col]
        return row[f"p_model_{side}"] - row[f"p_fair_open_{side}"]

    def odd_of(row, side_col):
        side = row[side_col]
        return row[f"odd_open_{side}"]

    disc["edge_favoritismo"] = disc.apply(lambda r: edge_of(r, "pick_favoritismo"), axis=1)
    disc["edge_placar_exato"] = disc.apply(lambda r: edge_of(r, "pick_placar_exato"), axis=1)
    disc["odd_favoritismo"] = disc.apply(lambda r: odd_of(r, "pick_favoritismo"), axis=1)
    disc["odd_placar_exato"] = disc.apply(lambda r: odd_of(r, "pick_placar_exato"), axis=1)
    disc["won_favoritismo"] = disc["pick_favoritismo"] == disc["actual_result"]
    disc["won_placar_exato"] = disc["pick_placar_exato"] == disc["actual_result"]

    print(f"\nEdge medio (p_model_lado - p_fair_open_lado) do lado ESCOLHIDO:")
    print(f"  favoritismo:  media={disc['edge_favoritismo'].mean():.4f}  mediana={disc['edge_favoritismo'].median():.4f}")
    print(f"  placar_exato: media={disc['edge_placar_exato'].mean():.4f}  mediana={disc['edge_placar_exato'].median():.4f}")

    diff = disc["edge_placar_exato"] - disc["edge_favoritismo"]
    print(f"\nDiferenca pareada (placar_exato - favoritismo), por jogo: media={diff.mean():.4f} desvio={diff.std():.4f}")
    t_stat, t_p = stats.ttest_rel(disc["edge_placar_exato"], disc["edge_favoritismo"])
    w_stat, w_p = stats.wilcoxon(disc["edge_placar_exato"], disc["edge_favoritismo"])
    print(f"Teste t pareado: t={t_stat:.3f} p={t_p:.4f}")
    print(f"Wilcoxon (pareado, nao-parametrico): W={w_stat:.1f} p={w_p:.4f}")

    # bootstrap CI da diferenca media
    rng = np.random.default_rng(42)
    boot_means = np.array([diff.sample(frac=1.0, replace=True, random_state=int(rng.integers(1e9))).mean()
                            for _ in range(5000)])
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    print(f"Bootstrap 95% CI da diferenca media de edge: [{ci_low:.4f}, {ci_high:.4f}]  (n={len(disc)})")

    # odds medias e ROI real de cada lado nos jogos de discordancia (concreto,
    # complementa "edge" com dinheiro de verdade)
    print(f"\nOdd media do lado escolhido: favoritismo={disc['odd_favoritismo'].mean():.3f}  "
          f"placar_exato={disc['odd_placar_exato'].mean():.3f}")
    print(f"Taxa de acerto (so discordancia): favoritismo={100*disc['won_favoritismo'].mean():.1f}%  "
          f"placar_exato={100*disc['won_placar_exato'].mean():.1f}%")

    for name, won_col, odd_col in (("favoritismo", "won_favoritismo", "odd_favoritismo"),
                                    ("placar_exato", "won_placar_exato", "odd_placar_exato")):
        n = len(disc)
        retorno = (disc[won_col] * disc[odd_col] * STAKE).sum()
        stake_total = n * STAKE
        roi = 100 * (retorno - stake_total) / stake_total
        print(f"ROI real (odds de abertura, discordancia, n={n}): {name}={roi:.2f}%")
        summary_rows.append(dict(metrica=f"roi_discordancia_{name}", valor=round(roi, 2)))

    summary_rows.append(dict(metrica="n_discordancia_com_odds", valor=len(disc)))
    summary_rows.append(dict(metrica="edge_medio_favoritismo", valor=round(disc["edge_favoritismo"].mean(), 4)))
    summary_rows.append(dict(metrica="edge_medio_placar_exato", valor=round(disc["edge_placar_exato"].mean(), 4)))
    summary_rows.append(dict(metrica="diff_media_pareada", valor=round(diff.mean(), 4)))
    summary_rows.append(dict(metrica="diff_bootstrap_ci_low", valor=round(ci_low, 4)))
    summary_rows.append(dict(metrica="diff_bootstrap_ci_high", valor=round(ci_high, 4)))
    summary_rows.append(dict(metrica="ttest_pareado_p", valor=round(t_p, 4)))
    summary_rows.append(dict(metrica="wilcoxon_pareado_p", valor=round(w_p, 4)))

    pd.DataFrame(summary_rows).to_csv(OUT_DIR / "discordance_summary.csv", index=False)
    disc[["fixture_id", "country", "tournament", "date", "home_team", "away_team",
          "pick_favoritismo", "pick_placar_exato", "actual_result",
          "edge_favoritismo", "edge_placar_exato", "odd_favoritismo", "odd_placar_exato",
          "won_favoritismo", "won_placar_exato"]].to_csv(OUT_DIR / "discordance_edge_paired.csv", index=False)
    print(f"\n>> CSVs salvos em {OUT_DIR}")

    # ---- 3) ceticismo: sera que o "edge maior de placar_exato" e so porque
    # placar_exato tende a escolher lados de odd mais alta (zebra) por
    # construcao (empates 0x0/1x1 sao score mais provavel MESMO quando H/D/A
    # favorece o mandante) -- checa distribuicao de odds/lado escolhido ----
    print("\n=== Contexto: distribuicao do LADO escolhido em discordancia ===")
    print("favoritismo:")
    print(disc["pick_favoritismo"].value_counts())
    print("placar_exato:")
    print(disc["pick_placar_exato"].value_counts())


if __name__ == "__main__":
    main()
