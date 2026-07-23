#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_metrics_fair_odds.py
=====================================
Vitrine de desempenho (PLANO 3) — o ATIVO da plataforma: odd justa REAL e
onde procurar valor entre casas.

Ideia (definida pelo dono): o modelo estima a probabilidade real do evento e
devolve a odd justa (even = 1/p). Medimos o quao bem o modelo identifica essa
odd justa comparando com a odd justa do MERCADO (odd de fechamento sem a
margem da casa) e reportamos:

  1. VIES do modelo (erro medio, sistematico) vs a odd justa do mercado — se ~0,
     o modelo nao super/subprecifica.
  2. PRECISAO (erro absoluto medio / RMSE em probabilidade) — o quao perto a odd
     justa do modelo fica da real. E o "erro em cima da previsao".
  3. UPLIFT DE BREAK-EVEN (por mercado x competicao): quanto a odd oferecida
     precisa subir pra alcancar a odd justa = a margem embutida da casa (medida
     pelo de-vig real por jogo).
  4. GAP ENTRE CASAS (melhor casa `Max` vs media `Avg`, no lado recomendado,
     MEDIANA pra nao inflar por azarao) — prova de que o valor e alcancavel
     comparando casas.

Verdade de mercado = `p_fair_close_*` do valuebet_dataset (de-vig real das odds
de fechamento). O overround empirico medido fica ~6-7% (backtest_margin_fit.md);
a suposicao de "6%" do dono e so uma ancora — aqui usamos o de-vig real por jogo.

HONESTIDADE: viés ~0 confirma que o modelo NAO bate o mercado (bateria W1-W4) —
o valor real e o line-shopping (achar a casa que paga acima da justa), nao
apostar no fluxo. Sem promessa de lucro.

Uso: python scripts/adhoc_metrics_fair_odds.py
Saida: data/reports/performance/fair_odds.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "data" / "built"
OUT_DIR = ROOT / "data" / "reports" / "performance"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_LEAGUES = ["Brasileirao Serie A", "Premier League", "La Liga", "Serie A Italia"]
MARGIN_ANCORA = 0.06  # ancora do dono (documental); calculo real usa de-vig por jogo


def _shopping_gap() -> pd.DataFrame:
    """Gap melhor-casa (Max) vs media (Avg) por (fixture_id, market, side),
    usando odds de fechamento. Liga odds_normalized -> fixture_id via matched."""
    od = pd.read_parquet(BUILT / "backtest_odds_normalized.parquet")
    mt = pd.read_parquet(BUILT / "backtest_matched.parquet")
    mt = mt[mt["covered"] == True][["date", "home_team_norm", "away_team_norm", "fixture_id"]]
    key = ["date", "home_team_norm", "away_team_norm"]
    od = od[od["closing"] == True]
    mx = od[od["book"] == "Max"][key + ["market", "side", "value"]].rename(columns={"value": "max_odd"})
    av = od[od["book"] == "Avg"][key + ["market", "side", "value"]].rename(columns={"value": "avg_odd"})
    g = mx.merge(av, on=key + ["market", "side"]).merge(mt, on=key)
    g = g[(g["max_odd"] > 1) & (g["avg_odd"] > 1)].dropna(subset=["fixture_id"])
    g["gap"] = g["max_odd"] / g["avg_odd"] - 1.0
    g["fixture_id"] = g["fixture_id"].astype("int64")
    return g[["fixture_id", "market", "side", "gap"]]


def _sel_1x2(v: pd.DataFrame):
    P = v[["p_model_H", "p_model_D", "p_model_A"]].values
    idx = P.argmax(1)
    side = np.array(["H", "D", "A"])[idx]
    r = np.arange(len(v))
    return side, P[r, idx], \
        v[["p_fair_close_H", "p_fair_close_D", "p_fair_close_A"]].values[r, idx], \
        v[["odd_close_H", "odd_close_D", "odd_close_A"]].values[r, idx]


def _sel_ou(v: pd.DataFrame):
    over = v["p_model_over"].values > 0.5
    side = np.where(over, "over", "under")
    p_model = np.where(over, v["p_model_over"], v["p_model_under"]).astype(float)
    p_fair = np.where(over, v["p_fair_close_over"], v["p_fair_close_under"]).astype(float)
    offered = np.where(over, v["odd_close_over"], v["odd_close_under"]).astype(float)
    return side, p_model, p_fair, offered


def _agg(p_model, p_fair, offered, sides, fids, gap_lookup, market_key):
    """Metricas de um (mercado, liga)."""
    m = ~np.isnan(offered) & ~np.isnan(p_fair) & (p_fair > 0) & (p_model > 0)
    p_model, p_fair, offered, sides, fids = p_model[m], p_fair[m], offered[m], sides[m], fids[m]
    n = len(p_model)
    if n < 20:
        return None
    err_p = p_model - p_fair                       # + = modelo da MAIOR prob que o mercado
    fair_odd = 1.0 / p_fair                         # odd justa do mercado (lado recomendado)
    upl = fair_odd / offered - 1.0                  # quanto a odd precisa subir p/ chegar no justo
    # gap entre casas no lado recomendado
    gaps = []
    for fid, sd in zip(fids, sides):
        gv = gap_lookup.get((int(fid), market_key, sd))
        if gv is not None:
            gaps.append(gv)
    gaps = np.array(gaps) if gaps else np.array([np.nan])
    return {
        "n": int(n),
        "vies_prob_pp": round(float(err_p.mean()) * 100, 2),
        "precisao_mae_pp": round(float(np.abs(err_p).mean()) * 100, 2),
        "precisao_rmse_pp": round(float(np.sqrt((err_p ** 2).mean())) * 100, 2),
        "breakeven_uplift_mediano_pct": round(float(np.median(upl)) * 100, 2),
        "breakeven_uplift_medio_pct": round(float(np.mean(upl)) * 100, 2),
        "gap_melhor_casa_mediano_pct": round(float(np.nanmedian(gaps)) * 100, 2) if np.isfinite(np.nanmedian(gaps)) else None,
        "gap_cobertura_n": int(np.isfinite(gaps).sum()),
    }


def _handicap_frame() -> pd.DataFrame:
    """Monta prob-modelo vs odd real para HANDICAP ASIATICO, restrito as linhas
    .5 (onde o modelo produz prob direta via _hcap, em mercados_derivados.handicap).
    Odds reais de `backtest_odds_normalized` (linha em handicap_line, odds H/A em
    handicap), de-vig 2-vias. Retorna colunas p_model_home/p_fair_home/offered
    no lado RECOMENDADO (home se p_model>0.5 senao away) + tournament + fixture."""
    import json as _json
    p = pd.read_parquet(BUILT / "backtest_predictions.parquet",
                        columns=["fixture_id", "tournament", "home_team", "prediction_json"])
    mrows = []
    for r in p.itertuples():
        try:
            j = _json.loads(r.prediction_json)
        except (TypeError, ValueError):
            continue
        hc = (j.get("mercados_derivados") or {}).get("handicap")
        if not hc:
            continue
        d = hc.get(r.home_team) or hc.get(next(iter(hc)))
        for L in ("-1.5", "-0.5", "0.5", "1.5"):
            if L in d:
                mrows.append((int(r.fixture_id), r.tournament, float(L), d[L]["prob"] / 100.0))
    md = pd.DataFrame(mrows, columns=["fixture_id", "tournament", "line", "p_model_home"])

    o = pd.read_parquet(BUILT / "backtest_odds_normalized.parquet")
    mt = pd.read_parquet(BUILT / "backtest_matched.parquet")
    mt = mt[mt["covered"] == True][["date", "home_team_norm", "away_team_norm", "fixture_id"]].dropna(subset=["fixture_id"])
    mt["fixture_id"] = mt["fixture_id"].astype("int64")
    key = ["date", "home_team_norm", "away_team_norm"]
    lines = o[o["market"] == "handicap_line"][key + ["value"]].rename(columns={"value": "line"}).merge(mt, on=key)
    ha = o[(o["market"] == "handicap") & (o["book"] == "Avg")]
    haH = ha[ha["side"] == "H"].sort_values("closing").groupby(key, as_index=False)["value"].last().rename(columns={"value": "odd_H"})
    haA = ha[ha["side"] == "A"].sort_values("closing").groupby(key, as_index=False)["value"].last().rename(columns={"value": "odd_A"})
    odds = lines.merge(haH, on=key).merge(haA, on=key)
    odds["line"] = odds["line"].astype(float)

    j = md.merge(odds[["fixture_id", "line", "odd_H", "odd_A"]], on=["fixture_id", "line"])
    j = j[(j["odd_H"] > 1) & (j["odd_A"] > 1)].copy()
    j["p_fair_home"] = (1 / j["odd_H"]) / ((1 / j["odd_H"]) + (1 / j["odd_A"]))
    # lado recomendado: home se modelo>=0.5, senao away
    home_pick = j["p_model_home"] >= 0.5
    j["p_model"] = np.where(home_pick, j["p_model_home"], 1 - j["p_model_home"])
    j["p_fair"] = np.where(home_pick, j["p_fair_home"], 1 - j["p_fair_home"])
    j["offered"] = np.where(home_pick, j["odd_H"], j["odd_A"])
    j["side"] = np.where(home_pick, "H", "A")
    return j


def main() -> None:
    v = pd.read_parquet(BUILT / "backtest_valuebet_dataset.parquet")
    v["fixture_id"] = v["fixture_id"].astype("int64")
    gap = _shopping_gap()
    gap_lookup = {(int(r.fixture_id), r.market, r.side): r.gap for r in gap.itertuples()}

    MARKETS = {"1x2": (_sel_1x2, "1x2"), "ou25": (_sel_ou, "ou25")}
    report = {
        "metodo": "Odd justa do modelo (1/p) vs odd justa do mercado (de-vig real das odds de "
        "fechamento). Vies = erro sistematico; precisao (MAE/RMSE em prob) = quao perto o modelo "
        "chega da odd justa; break-even uplift = margem embutida (quanto a odd precisa subir p/ "
        "chegar no justo); gap entre casas = melhor casa (Max) vs media (Avg) no lado recomendado.",
        "nota_margem": "Overround empirico medido ~6-7% (backtest_margin_fit.md); usamos o de-vig "
        "real por jogo, nao um 6% fixo. 'Max' e a melhor de ~10 casas (estatistica de extremo).",
        "nota_honestidade": "Vies ~0 confirma que o modelo nao bate o mercado — o valor esta em "
        "comparar casas (line-shopping), nao em apostar no fluxo. Sem promessa de lucro.",
        "mercados": {},
    }

    label = {"1x2": "Resultado (1X2)", "ou25": "Mais/Menos 2,5 gols"}
    for mk, (selfn, gapmk) in MARKETS.items():
        report["mercados"][label[mk]] = {"ligas": {}}
        groups = [(lg, lg) for lg in TARGET_LEAGUES] + [("Geral (ligas-alvo)", None)]
        for name, lg in groups:
            sub = v[v["tournament"].isin(TARGET_LEAGUES)] if lg is None else v[v["tournament"] == lg]
            side, p_model, p_fair, offered = selfn(sub)
            res = _agg(p_model, np.asarray(p_fair, float), np.asarray(offered, float),
                       np.asarray(side), sub["fixture_id"].values, gap_lookup, gapmk)
            if res:
                report["mercados"][label[mk]]["ligas"][name] = res

    # --- Handicap asiatico (linhas .5) ---
    hj = _handicap_frame()
    report["mercados"]["Handicap asiático (linhas .5)"] = {
        "nota": "Restrito as linhas .5 (onde o modelo produz prob direta). Odds reais de-vigadas "
        "2-vias. Pool geral e por liga com >=40 jogos.", "ligas": {}}
    hgroups = [(lg, lg) for lg in TARGET_LEAGUES] + [("Geral (ligas-alvo)", "TARGET"), ("Todas as ligas", None)]
    for name, lg in hgroups:
        if lg == "TARGET":
            sub = hj[hj["tournament"].isin(TARGET_LEAGUES)]
        elif lg is None:
            sub = hj
        else:
            sub = hj[hj["tournament"] == lg]
        if len(sub) < 40:
            continue
        res = _agg(sub["p_model"].values, sub["p_fair"].values, sub["offered"].values,
                   sub["side"].values, sub["fixture_id"].values, gap_lookup, "handicap")
        if res:
            report["mercados"]["Handicap asiático (linhas .5)"]["ligas"][name] = res

    out = OUT_DIR / "fair_odds.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Salvo: {out}\n")
    for mkt, d in report["mercados"].items():
        print(f"=== {mkt} ===")
        for lg, r in d["ligas"].items():
            print(f"  {lg:22s} n={r['n']:5d}  vies={r['vies_prob_pp']:+.2f}pp  "
                  f"precisao(MAE)={r['precisao_mae_pp']:.2f}pp  breakeven=+{r['breakeven_uplift_mediano_pct']:.2f}%  "
                  f"gap_casas={r['gap_melhor_casa_mediano_pct']}%")
        print()


if __name__ == "__main__":
    main()
