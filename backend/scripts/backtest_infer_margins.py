#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_infer_margins.py
==================================
Etapa 5 (peca nova) do modulo de backtest: `/data-test` so tem odds reais de
1X2, over/under 2,5 gols e handicap asiatico de gols -- NAO tem odds de
escanteios/chutes/cartoes. Em vez de simplesmente excluir esses mercados da
simulacao financeira, este script:

  1. Nos mercados com odds REAIS, compara a odd da casa (`Avg`, media de
     mercado) com a probabilidade do NOSSO modelo (congelado, sem vazamento)
     no mesmo jogo/mercado -- extrai a margem/overround real de cada aposta.
  2. Ajusta um modelo simples da margem (constante vs. dependente da
     "extremidade" da probabilidade -- vies favorito-azarao, ja documentado
     nesta pesquisa) separado para mercados de 2 vias (O/U) e 3 vias (1X2),
     reaproveitando `devig_methods.py` (de-vig proporcional/power/Shin, ja
     validado na bateria H1-H4).
  3. Aplica o modelo de margem ajustado nos mercados SEM odds reais
     (escanteios/chutes/chutes a gol/cartoes total/amarelo/vermelho),
     usando a propria estimativa do modelo como linha O/U (pedido do dono),
     para produzir uma ODD INFERIDA (marcada como tal, nunca misturada com
     odds reais).

Uso: python scripts/backtest_infer_margins.py
"""
from __future__ import annotations

import json
import math
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

from scripts.devig_methods import proportional_devig  # noqa: E402

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_INFERRED = ROOT / "data" / "built" / "backtest_inferred_odds.parquet"
OUT_REPORT = ROOT / "data" / "reports" / "backtest_margin_fit.md"

# Mercados sem odds reais no data-test -- cada um mapeado pro campo do JSON de
# previsao de onde tirar a PMF (distribuicao) e a estimativa (linha O/U). Nomes
# IDENTICOS aos de backtest_grade_accuracy.py::COUNT_MARKETS (f"{name}_{side}")
# -- e a chave de juncao entre precisao e financeiro inferido.
NO_ODDS_MARKETS = [
    ("chutes_home", ["chutes_equipe", "{home}"]),
    ("chutes_away", ["chutes_equipe", "{away}"]),
    ("chutes_total", ["chutes"]),  # "chutes" ja e o no flat (nao aninhado sob "total")
    ("chutes_a_gol_home", ["chutes_a_gol", "{home}"]),
    ("chutes_a_gol_away", ["chutes_a_gol", "{away}"]),
    ("chutes_a_gol_total", ["chutes_a_gol", "total"]),
    ("escanteios_home", ["escanteios", "{home}"]),
    ("escanteios_away", ["escanteios", "{away}"]),
    ("escanteios_total", ["escanteios", "total"]),
    ("cartoes_home", ["cartoes", "{home}"]),
    ("cartoes_away", ["cartoes", "{away}"]),
    ("cartoes_total", ["cartoes", "total"]),
    ("cartoes_amarelos_home", ["cartoes_amarelos", "{home}"]),
    ("cartoes_amarelos_away", ["cartoes_amarelos", "{away}"]),
    ("cartoes_amarelos_total", ["cartoes_amarelos", "total"]),
    ("cartoes_vermelhos_home", ["cartoes_vermelhos", "{home}"]),
    ("cartoes_vermelhos_away", ["cartoes_vermelhos", "{away}"]),
    ("cartoes_vermelhos_total", ["cartoes_vermelhos", "total"]),
]


def p_over_at_estimate(node: dict) -> tuple[float, float] | None:
    """P(Over na PROPRIA estimativa do modelo) a partir da distribuicao (PMF) crua
    -- a linha e um valor continuo (a media), diferente das linhas fixas (5.5/6.5..)
    ja tabeladas em `linhas`. Over = P(contagem >= ceil(estimativa)). Retorna
    (estimativa, p_over) ou None se o no nao existir."""
    if node is None or "distribuicao" not in node:
        return None
    pmf = np.asarray(node["distribuicao"], dtype=float)
    est = float(node["estimativa"])
    cut = math.ceil(est)
    if float(cut) == est:
        # Empate exato (estimativa cai bem num inteiro) -- caso raro, tratado como
        # "push" nao usavel para O/U estrito (ver backtest_grade_accuracy.py).
        return est, float("nan")
    cut = max(0, min(cut, len(pmf)))
    p_over = float(pmf[cut:].sum())
    return est, p_over


def get_node(pred: dict, path: list[str], home: str, away: str):
    node = pred
    for key in path:
        key = key.format(home=home, away=away)
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def collect_real_market_observations(preds: pd.DataFrame, odds: pd.DataFrame, matched: pd.DataFrame):
    """Para cada partida com previsao + odds reais, junta (nosso_prob, odd_book,
    overround) por mercado -- fonte para o ajuste de margem. Indexado por
    (source, div, date, home_raw, away_raw) -- evita filtrar o parquet de odds
    inteiro a cada partida (O(n_fixtures * n_odds) seria lento demais)."""
    matched_ok = matched[matched["fixture_id"].notna()].copy()
    matched_ok["fixture_id"] = matched_ok["fixture_id"].astype("int64")

    odds_avg = odds[odds["book"].isin(["Avg", "AvgC"])].copy()
    odds_idx: dict[tuple, list] = {}
    for r in odds_avg.itertuples(index=False):
        key = (r.source, r.div, r.date, r.home_team_raw, r.away_team_raw)
        odds_idx.setdefault(key, []).append(r)

    pred_by_fx = {r.fixture_id: json.loads(r.prediction_json) for r in preds.itertuples(index=False)}

    rows = []
    for mrow in matched_ok.itertuples(index=False):
        pred = pred_by_fx.get(mrow.fixture_id)
        if pred is None:
            continue
        odds_rows = odds_idx.get((mrow.source, mrow.div, mrow.date, mrow.home_team_raw, mrow.away_team_raw))
        if not odds_rows:
            continue

        keys = [k for k in pred["vencedor"]["probabilidades"].keys() if k != "Empate"]
        if len(keys) != 2:
            continue
        home_name, away_name = keys[0], keys[1]
        p_h = pred["vencedor"]["probabilidades"][home_name] / 100.0
        p_d = pred["vencedor"]["probabilidades"]["Empate"] / 100.0
        p_a = pred["vencedor"]["probabilidades"][away_name] / 100.0

        odds_map_1x2, odds_map_ou = {}, {}
        for r in odds_rows:
            if r.market == "1x2":
                odds_map_1x2.setdefault(r.side, r.value)
            elif r.market == "ou25":
                odds_map_ou.setdefault(r.side, r.value)

        if all(s in odds_map_1x2 for s in ("H", "D", "A")):
            ours = [p_h, p_d, p_a]
            devig = proportional_devig([odds_map_1x2["H"], odds_map_1x2["D"], odds_map_1x2["A"]])
            overround = sum(1.0 / odds_map_1x2[s] for s in ("H", "D", "A")) - 1.0
            for i, side in enumerate(("H", "D", "A")):
                rows.append(dict(market_kind="3way", market="1x2", fixture_id=mrow.fixture_id, side=side,
                                  our_prob=ours[i], devig_prob=devig[i],
                                  book_odd=odds_map_1x2[side], overround=overround))

        if all(s in odds_map_ou for s in ("over", "under")):
            p_over = pred["over_2_5"]["prob_sim"] / 100.0
            devig = proportional_devig([odds_map_ou["over"], odds_map_ou["under"]])
            overround = (1.0 / odds_map_ou["over"] + 1.0 / odds_map_ou["under"]) - 1.0
            rows.append(dict(market_kind="2way", market="ou25", fixture_id=mrow.fixture_id, side="over",
                              our_prob=p_over, devig_prob=devig[0],
                              book_odd=odds_map_ou["over"], overround=overround))
            rows.append(dict(market_kind="2way", market="ou25", fixture_id=mrow.fixture_id, side="under",
                              our_prob=1 - p_over, devig_prob=devig[1],
                              book_odd=odds_map_ou["under"], overround=overround))
    return pd.DataFrame(rows)


def fit_margin_model(obs: pd.DataFrame, market_kind: str):
    """Ajusta overround ~ a + b*|our_prob-0.5| (linear); reporta R2. Se o ajuste
    for fraco, o coeficiente b fica perto de 0 e o modelo colapsa na media
    constante -- reportado com transparencia, nao escondido."""
    sub = obs[obs["market_kind"] == market_kind]
    if len(sub) < 20:
        return None
    x = np.abs(sub["our_prob"].to_numpy() - 0.5)
    y = sub["overround"].to_numpy()
    if np.allclose(x, x[0]):
        a, b = float(y.mean()), 0.0
        r2 = 0.0
    else:
        b, a = np.polyfit(x, y, 1)
        pred = a + b * x
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"a": float(a), "b": float(b), "r2": float(r2), "n": int(len(sub)),
            "overround_medio": float(y.mean()), "overround_min": float(y.min()),
            "overround_max": float(y.max())}


def apply_margin_to_prob(p: float, model: dict) -> float:
    """Aplica overround = a + b*|p-0.5| a uma prob. do NOSSO modelo (2 vias:
    p e 1-p), devolvendo a odd sintetica do lado `p` -- simula como uma casa
    precificaria essa mesma probabilidade dado o padrao de margem observado."""
    overround = max(0.0, model["a"] + model["b"] * abs(p - 0.5))
    total = 1.0 + overround
    # distribui o overround proporcionalmente as duas pernas (mesma logica do
    # de-vig proporcional invertido: infla cada perna por 'total', preservando
    # a razao p/(1-p) crua do modelo).
    raw = np.array([p, 1 - p]) * total
    return raw[0]


def main():
    print("=" * 80)
    print(" INFERENCIA DE MARGEM -- odds sinteticas p/ mercados sem odds reais")
    print("=" * 80)

    if not PREDICTIONS.exists():
        raise SystemExit(f"{PREDICTIONS} nao existe -- rode backtest_generate_predictions.py primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    odds = pd.read_parquet(ODDS)
    matched = pd.read_parquet(MATCHED)

    print(">> Coletando observacoes de margem real (1X2 + O/U 2,5 gols)...")
    obs = collect_real_market_observations(preds, odds, matched)
    print(f"   {len(obs)} observacoes (lado x partida)")

    report = ["# Ajuste do modelo de margem (vig) -- data-test 2025\n"]
    models = {}
    for kind in ("3way", "2way"):
        m = fit_margin_model(obs, kind)
        models[kind] = m
        report.append(f"## Mercado {kind}\n")
        if m is None:
            report.append("Amostra insuficiente (<20 observacoes) -- nao ajustado.\n")
            continue
        report.append(f"- N observacoes: {m['n']}")
        report.append(f"- Overround medio: {100*m['overround_medio']:.2f}% "
                       f"(min {100*m['overround_min']:.2f}%, max {100*m['overround_max']:.2f}%)")
        report.append(f"- Ajuste linear: overround = {m['a']:.4f} + {m['b']:.4f} * |p-0.5|")
        report.append(f"- R2: {m['r2']:.3f} "
                       f"({'padrao explica bem a variacao' if m['r2'] > 0.15 else 'fraco -- overround perto de constante, aplicado como media'})")
        report.append("")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print(f">> Relatorio do ajuste -> {OUT_REPORT}")

    # ---- aplicar aos mercados sem odds reais (usa o modelo 2way -- mesma estrutura O/U) ----
    model_2way = models.get("2way")
    if model_2way is None:
        print(">> Sem modelo 2way ajustado -- nao e possivel inferir odds. Abortando essa etapa.")
        return

    rows = []
    for r in preds.itertuples(index=False):
        pred = json.loads(r.prediction_json)
        for market_name, path in NO_ODDS_MARKETS:
            node = get_node(pred, path, r.home_team, r.away_team)
            res = p_over_at_estimate(node) if node else None
            if res is None:
                continue
            est, p_over = res
            if math.isnan(p_over):
                continue
            odd_over = 1.0 / apply_margin_to_prob(p_over, model_2way)
            odd_under = 1.0 / apply_margin_to_prob(1 - p_over, model_2way)
            rows.append(dict(fixture_id=r.fixture_id, market=market_name, linha=est,
                              p_over_modelo=p_over, odd_over_inferida=round(odd_over, 3),
                              odd_under_inferida=round(odd_under, 3), inferred=True))

    out = pd.DataFrame(rows)
    OUT_INFERRED.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_INFERRED, index=False)
    print(f">> {len(out)} odds inferidas ({len(NO_ODDS_MARKETS)} mercados x partidas) -> {OUT_INFERRED}")


if __name__ == "__main__":
    main()
