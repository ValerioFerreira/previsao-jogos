#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_value_groundwork.py
==================================
Groundwork pra bateria de pesquisa ad-hoc (2026-07-22, pos-modulo de backtest
#21-30): junta modelo (prediction_json) + odds reais (abertura E fechamento,
book "Avg") + de-vig (Shin, `devig_methods.py`, ja testado/recomendado no H3)
pra TODOS os 8117 jogos casados com odds reais (nao so as 4 ligas do pedido
anterior) -- amostra ~100x maior que os 84 fixtures do H3/H2 original
(`DOCUMENTACAO_CENTRAL.md` §19.4/19.5, "amostra pequena demais pra validar
rentabilidade"). Aqui usamos odds HISTORICAS reais (nao snapshot forward),
entao temos fechamento de verdade pra CLV, coisa que o H3 original nao tinha.

Saida: data/built/backtest_valuebet_dataset.parquet -- uma linha por fixture,
colunas de modelo/odds/de-vig/CLV pros mercados 1x2 e O/U 2,5. Todo agente da
bateria de pesquisa parte DESSE arquivo (nao re-deriva o join, que ja teve bug
de fixture_id str/int e de book/closing nesta mesma sessao).

Uso: python scripts/adhoc_value_groundwork.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from devig_methods import shin_devig  # noqa: E402

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"


def main():
    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)

    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    fx_to_key5 = dict(zip(matched_ok["fixture_id"],
                           zip(matched_ok["source"], matched_ok["div"], matched_ok["date"],
                               matched_ok["home_team_raw"], matched_ok["away_team_raw"])))

    def odds_dict(market, book="Avg"):
        sub = odds[(odds["market"] == market) & (odds["book"] == book)]
        open_d, close_d = {}, {}
        for r in sub.itertuples(index=False):
            k = (r.source, r.div, r.date, r.home_team_raw, r.away_team_raw)
            (close_d if r.closing else open_d).setdefault(k, {})[r.side] = r.value
        return open_d, close_d

    open_1x2, close_1x2 = odds_dict("1x2")
    open_ou25, close_ou25 = odds_dict("ou25")

    preds["prediction"] = preds["prediction_json"].map(json.loads)

    rows = []
    for r in preds.itertuples(index=False):
        fx = r.fixture_id
        key5 = fx_to_key5.get(fx)
        if key5 is None:
            continue
        pred = r.prediction
        home, away = r.home_team, r.away_team
        hg, ag = r.home_score, r.away_score
        actual = "H" if hg > ag else ("A" if ag > hg else "D")
        total = hg + ag

        probs = pred["vencedor"]["probabilidades"]
        p_home = probs.get(home, np.nan) / 100.0
        p_draw = probs.get("Empate", np.nan) / 100.0
        p_away = probs.get(away, np.nan) / 100.0
        p_over = pred["over_2_5"]["prob_sim"] / 100.0

        row = dict(fixture_id=fx, country=r.country, tournament=r.tournament, date=r.date,
                   home_team=home, away_team=away, home_score=hg, away_score=ag,
                   total_goals=total, actual_result=actual, actual_over=total > 2.5,
                   p_model_H=p_home, p_model_D=p_draw, p_model_A=p_away,
                   p_model_over=p_over, p_model_under=1 - p_over)

        o_open = open_1x2.get(key5)
        o_close = close_1x2.get(key5)
        for side in ("H", "D", "A"):
            row[f"odd_open_{side}"] = (o_open or {}).get(side)
            row[f"odd_close_{side}"] = (o_close or {}).get(side)
        if o_open and all(s in o_open for s in ("H", "D", "A")):
            p_fair = shin_devig([o_open["H"], o_open["D"], o_open["A"]])
            row["p_fair_open_H"], row["p_fair_open_D"], row["p_fair_open_A"] = p_fair
        if o_close and all(s in o_close for s in ("H", "D", "A")):
            p_fair = shin_devig([o_close["H"], o_close["D"], o_close["A"]])
            row["p_fair_close_H"], row["p_fair_close_D"], row["p_fair_close_A"] = p_fair

        g_open = open_ou25.get(key5)
        g_close = close_ou25.get(key5)
        row["odd_open_over"] = (g_open or {}).get("over")
        row["odd_open_under"] = (g_open or {}).get("under")
        row["odd_close_over"] = (g_close or {}).get("over")
        row["odd_close_under"] = (g_close or {}).get("under")
        if g_open and "over" in g_open and "under" in g_open:
            p_fair = shin_devig([g_open["over"], g_open["under"]])
            row["p_fair_open_over"], row["p_fair_open_under"] = p_fair
        if g_close and "over" in g_close and "under" in g_close:
            p_fair = shin_devig([g_close["over"], g_close["under"]])
            row["p_fair_close_over"], row["p_fair_close_under"] = p_fair

        rows.append(row)

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"{len(df)} fixtures -> {OUT}")
    print(f"1x2 abertura: {df['odd_open_H'].notna().sum()} | 1x2 fechamento: {df['odd_close_H'].notna().sum()}")
    print(f"ou25 abertura: {df['odd_open_over'].notna().sum()} | ou25 fechamento: {df['odd_close_over'].notna().sum()}")
    print(f"1x2 com fair-devig abertura: {df['p_fair_open_H'].notna().sum() if 'p_fair_open_H' in df else 0}")
    print(f"ou25 com fair-devig abertura: {df['p_fair_open_over'].notna().sum() if 'p_fair_open_over' in df else 0}")


if __name__ == "__main__":
    main()
