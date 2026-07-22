#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_simulate_financial.py
=======================================
Etapa 5/6 do modulo de backtest: simula apostas de R$5,00 (valor fixo, uma
aposta por mercado, nunca combinadas) usando as previsoes do modelo congelado.

Duas secoes, nunca misturadas:

  A) ODDS REAIS (resultado 1x2 com 2 estrategias, over/under 2,5 gols,
     handicap asiatico de gols) -- unicos 3 mercados com odds de verdade em
     `/data-test` (achado da Etapa 1). Cada casa de aposta detectada
     dinamicamente (nenhuma lista fixa) vira uma simulacao independente.
     Resultado usa o pick do modelo (favoritismo/placar-exato). O/U 2,5 e
     handicap seguem o padrao pedido p/ "demais mercados": simula SEMPRE
     apostar em cada lado (over E under; home-cobre E away-cobre),
     separadamente -- serve de diagnostico de vies, nao "segue o modelo".

  B) ODDS INFERIDAS (escanteios/chutes/chutes a gol/cartoes total-amarelo-
     vermelho) -- sem odds reais no dataset; usa a odd SINTETICA calculada
     por backtest_infer_margins.py a partir do padrao de margem das odds
     reais. Sempre marcada `inferred=True`, nunca comparada lado a lado com
     odds reais sem essa marcacao clara.

Uso: python scripts/backtest_simulate_financial.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
INFERRED = ROOT / "data" / "built" / "backtest_inferred_odds.parquet"
GRADES = ROOT / "data" / "built" / "backtest_grades.parquet"
OUT_BETS = ROOT / "data" / "built" / "backtest_bets.parquet"

STAKE = 5.0
HANDICAP_LINES = (-2.5, -1.5, -0.5, 0.5, 1.5)
HANDICAP_TOL = 0.01


def summarize(bets: pd.DataFrame) -> dict:
    n = len(bets)
    wins = int(bets["won"].sum())
    stake_total = n * STAKE
    retorno_bruto = float((bets["won"] * bets["odd"] * STAKE).sum())
    lucro = retorno_bruto - stake_total
    return {
        "apostas": n, "vencedoras": wins, "perdedoras": n - wins,
        "stake_total": round(stake_total, 2), "retorno_bruto": round(retorno_bruto, 2),
        "lucro_liquido": round(lucro, 2),
        "roi_pct": round(100 * lucro / stake_total, 2) if n else None,
        "yield_pct": round(100 * lucro / stake_total, 2) if n else None,
        "odd_media": round(float(bets["odd"].mean()), 3) if n else None,
        "odd_mediana": round(float(bets["odd"].median()), 3) if n else None,
    }


def build_1x2_bets(preds: pd.DataFrame, matched: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    o_1x2 = odds[(odds["market"] == "1x2") & (~odds["closing"])]
    o_idx = {}
    for r in o_1x2.itertuples(index=False):
        o_idx.setdefault((r.source, r.div, r.date, r.home_team_raw, r.away_team_raw, r.book), {})[r.side] = r.value

    pred_by_fx = {r.fixture_id: json.loads(r.prediction_json) for r in preds.itertuples(index=False)}
    real_by_fx = {r.fixture_id: (r.home_score, r.away_score, r.home_team, r.away_team, r.country, r.tournament, r.date)
                  for r in preds.itertuples(index=False)}

    rows = []
    for mrow in matched_ok.itertuples(index=False):
        fx = mrow.fixture_id
        pred = pred_by_fx.get(fx)
        real = real_by_fx.get(fx)
        if pred is None or real is None:
            continue
        hg, ag, home, away, country, tournament, date = real
        actual = "H" if hg > ag else ("A" if ag > hg else "D")

        for strat in ("favoritismo", "placar_exato"):
            if strat == "favoritismo":
                w = pred["vencedor"]["vencedor"]
            else:
                top1 = pred["placar_exato"]["top"][0]
                i, j = top1["mandante"], top1["visitante"]
                w = home if i > j else (away if j > i else "Empate")
            side = "H" if w == home else ("A" if w == away else "D")

            for book_key, book_odds in ((k, v) for k, v in o_idx.items()
                                         if k[:5] == (mrow.source, mrow.div, mrow.date, mrow.home_team_raw, mrow.away_team_raw)):
                book = book_key[5]
                odd = book_odds.get(side)
                if odd is None:
                    continue
                rows.append(dict(section="real", market="resultado", strategy=strat, book=book,
                                  country=country, tournament=tournament, date=date,
                                  fixture_id=fx, odd=odd, won=(side == actual)))
    return pd.DataFrame(rows)


def build_ou25_bets(preds: pd.DataFrame, matched: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    o_ou = odds[(odds["market"] == "ou25") & (~odds["closing"])]
    o_idx = {}
    for r in o_ou.itertuples(index=False):
        o_idx.setdefault((r.source, r.div, r.date, r.home_team_raw, r.away_team_raw, r.book), {})[r.side] = r.value

    real_by_fx = {r.fixture_id: (r.home_score, r.away_score, r.country, r.tournament, r.date)
                  for r in preds.itertuples(index=False)}

    rows = []
    for mrow in matched_ok.itertuples(index=False):
        fx = mrow.fixture_id
        real = real_by_fx.get(fx)
        if real is None:
            continue
        hg, ag, country, tournament, date = real
        actual_over = (hg + ag) > 2.5
        for book_key, book_odds in ((k, v) for k, v in o_idx.items()
                                     if k[:5] == (mrow.source, mrow.div, mrow.date, mrow.home_team_raw, mrow.away_team_raw)):
            book = book_key[5]
            for side, wins_if in (("over", actual_over), ("under", not actual_over)):
                odd = book_odds.get(side)
                if odd is None:
                    continue
                rows.append(dict(section="real", market="gols_ou25", strategy=f"sempre_{side}", book=book,
                                  country=country, tournament=tournament, date=date,
                                  fixture_id=fx, odd=odd, won=wins_if))
    return pd.DataFrame(rows)


def build_handicap_bets(preds: pd.DataFrame, matched: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")
    o_line = odds[(odds["market"] == "handicap_line") & (~odds["closing"])]
    o_odd = odds[(odds["market"] == "handicap") & (~odds["closing"])]

    # linha por (jogo, casa) -- cada casa pode cotar um handicap ligeiramente
    # diferente; so cai na linha generica "market" (AHh/BbAHh, sem casa) se a
    # propria casa nao tiver a sua (ex.: B365AH ausente mas B365AHH/AHA presentes).
    line_idx = {}
    for r in o_line.itertuples(index=False):
        line_idx[(r.source, r.div, r.date, r.home_team_raw, r.away_team_raw, r.book)] = r.value
    odd_idx = {}
    for r in o_odd.itertuples(index=False):
        odd_idx.setdefault((r.source, r.div, r.date, r.home_team_raw, r.away_team_raw, r.book), {})[r.side] = r.value

    real_by_fx = {r.fixture_id: (r.home_score, r.away_score, r.country, r.tournament, r.date)
                  for r in preds.itertuples(index=False)}

    rows = []
    for mrow in matched_ok.itertuples(index=False):
        fx = mrow.fixture_id
        real = real_by_fx.get(fx)
        if real is None:
            continue
        hg, ag, country, tournament, date = real
        key5 = (mrow.source, mrow.div, mrow.date, mrow.home_team_raw, mrow.away_team_raw)
        market_line = line_idx.get(key5 + ("market",))
        margin = hg - ag
        for book_key, book_odds in ((k, v) for k, v in odd_idx.items() if k[:5] == key5):
            book = book_key[5]
            line = line_idx.get(key5 + (book,), market_line)
            if line is None:
                continue
            nearest = min(HANDICAP_LINES, key=lambda x: abs(x - line))
            if abs(nearest - line) > HANDICAP_TOL:
                continue  # linha de quarto de gol (ex. -0.25) -- fora da grade suportada, nao fabricamos
            home_covers = (margin + nearest) > 0
            for side, wins_if in (("H", home_covers), ("A", not home_covers)):
                odd = book_odds.get(side)
                if odd is None:
                    continue
                rows.append(dict(section="real", market="handicap_gols", strategy=f"sempre_{'home' if side == 'H' else 'away'}_cobre",
                                  book=book, country=country, tournament=tournament, date=date,
                                  fixture_id=fx, odd=odd, linha=nearest, won=wins_if))
    return pd.DataFrame(rows)


def build_inferred_bets(grades: pd.DataFrame, inferred: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    meta = {r.fixture_id: (r.country, r.tournament, r.date) for r in preds.itertuples(index=False)}
    g = grades[grades["strategy"] == "over_under"][["fixture_id", "market", "pred"]]
    merged = inferred.merge(g, on=["fixture_id", "market"], how="inner")
    rows = []
    for r in merged.itertuples(index=False):
        m = meta.get(r.fixture_id)
        if m is None or r.pred == "PUSH":
            continue
        country, tournament, date = m
        for side, odd in (("over", r.odd_over_inferida), ("under", r.odd_under_inferida)):
            won = (r.pred == side.upper())
            rows.append(dict(section="inferido", market=r.market, strategy=f"sempre_{side}", book="modelo_inferido",
                              country=country, tournament=tournament, date=date,
                              fixture_id=r.fixture_id, odd=odd, won=won))
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print(" SIMULACAO FINANCEIRA -- R$5 fixos por aposta")
    print("=" * 80)

    for p in (PREDICTIONS, MATCHED, ODDS):
        if not p.exists():
            raise SystemExit(f"{p} nao existe -- rode as etapas anteriores primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    matched = pd.read_parquet(MATCHED)
    odds = pd.read_parquet(ODDS)

    print(">> Montando apostas -- resultado (1x2)...")
    bets_1x2 = build_1x2_bets(preds, matched, odds)
    print(f"   {len(bets_1x2)} apostas")

    print(">> Montando apostas -- over/under 2,5 gols...")
    bets_ou25 = build_ou25_bets(preds, matched, odds)
    print(f"   {len(bets_ou25)} apostas")

    print(">> Montando apostas -- handicap asiatico de gols...")
    bets_hcap = build_handicap_bets(preds, matched, odds)
    print(f"   {len(bets_hcap)} apostas")

    bets_inferred = pd.DataFrame()
    if INFERRED.exists() and GRADES.exists():
        print(">> Montando apostas -- mercados com odds INFERIDAS...")
        inferred = pd.read_parquet(INFERRED)
        grades = pd.read_parquet(GRADES)
        bets_inferred = build_inferred_bets(grades, inferred, preds)
        print(f"   {len(bets_inferred)} apostas")
    else:
        print(">> backtest_inferred_odds.parquet/backtest_grades.parquet ausentes -- pulando secao inferida")

    all_bets = pd.concat([bets_1x2, bets_ou25, bets_hcap, bets_inferred], ignore_index=True)
    all_bets["stake"] = STAKE
    OUT_BETS.parent.mkdir(parents=True, exist_ok=True)
    all_bets.to_parquet(OUT_BETS, index=False)
    print(f"\n>> {len(all_bets)} apostas simuladas (R${STAKE:.2f} cada) -> {OUT_BETS}")

    print("\n=== Resumo agregado por mercado/estrategia (todas as casas/ligas somadas) ===")
    for (section, market, strategy), sub in all_bets.groupby(["section", "market", "strategy"]):
        s = summarize(sub)
        print(f"[{section}] {market}/{strategy}: N={s['apostas']} ROI={s['roi_pct']}% "
              f"lucro=R${s['lucro_liquido']} odd_media={s['odd_media']}")


if __name__ == "__main__":
    main()
