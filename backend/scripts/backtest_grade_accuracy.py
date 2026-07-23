#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_grade_accuracy.py
===================================
Etapa 2/7 do modulo de backtest: mede a PRECISAO real do modelo (sem envolver
dinheiro) em cada mercado, comparando a previsao do modelo congelado (gerada
por backtest_generate_predictions.py) com o resultado REAL de cada partida.

Resultado da partida -- duas estrategias INDEPENDENTES (pedido do dono):
  - Estrategia 1 (favoritismo): maior prob. entre mandante/empate/visitante.
  - Estrategia 2 (placar exato): H/D/A DERIVADO do placar mais provavel do
    modelo (top-1 da matriz conjunta) -- pode discordar da Estrategia 1
    (ex.: 1x1 = Empate mesmo com pequeno favoritismo H/D/A).

Demais mercados (chutes/chutes a gol/escanteios/cartoes total-amarelo-
vermelho, gols por 1o/2o tempo): classifica OVER/UNDER usando a PROPRIA
estimativa do modelo como linha de corte (regra do dono). Emp. exato
(real == estimativa, so possivel se a estimativa cair num inteiro) vira
"push" -- contado a parte, nao inflando nem penalizando a taxa de acerto.

Impedimentos e faltas: sem modelo em nenhum escopo pesquisado (clube nao tem
`offsides_nb`; nenhum escopo tem modelo de faltas por equipe) -- aparecem no
relatorio como "sem modelo, nao avaliavel", nunca com um numero fabricado.

Uso: python scripts/backtest_grade_accuracy.py
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

from scripts.battery_dataset import load_clubs_df  # noqa: E402

PREDICTIONS = ROOT / "data" / "built" / "backtest_predictions.parquet"
OUT_GRADES = ROOT / "data" / "built" / "backtest_grades.parquet"
OUT_REPORT = ROOT / "data" / "reports" / "backtest_accuracy_summary.md"

# (nome do mercado, caminho no JSON pra {home}/{away}/total, coluna real home,
#  coluna real away) -- todos O/U na propria estimativa do modelo. Nota: "chutes"
# (total) e um NO FLAT em predictor.py (nao aninhado sob "total", diferente dos
# outros 3 mercados) -- unico motivo do path_t assimetrico abaixo.
COUNT_MARKETS = [
    ("chutes", ["chutes_equipe", "{home}"], ["chutes_equipe", "{away}"], ["chutes"],
     "home_cur_sb_shots", "away_cur_sb_shots"),
    ("chutes_a_gol", ["chutes_a_gol", "{home}"], ["chutes_a_gol", "{away}"], ["chutes_a_gol", "total"],
     "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target"),
    ("escanteios", ["escanteios", "{home}"], ["escanteios", "{away}"], ["escanteios", "total"],
     "home_cur_sb_corners", "away_cur_sb_corners"),
    ("cartoes", ["cartoes", "{home}"], ["cartoes", "{away}"], ["cartoes", "total"],
     "home_cur_sb_cards", "away_cur_sb_cards"),
    ("cartoes_amarelos", ["cartoes_amarelos", "{home}"], ["cartoes_amarelos", "{away}"], ["cartoes_amarelos", "total"],
     "home_cur_sb_yellow", "away_cur_sb_yellow"),
    ("cartoes_vermelhos", ["cartoes_vermelhos", "{home}"], ["cartoes_vermelhos", "{away}"], ["cartoes_vermelhos", "total"],
     "home_cur_sb_red", "away_cur_sb_red"),
]

NOT_AVAILABLE_MARKETS = ["impedimentos (sem modelo para clube)", "faltas (sem modelo em nenhum escopo)"]


def get_node(pred: dict, path: list, home: str, away: str):
    node = pred
    for key in path:
        key = key.format(home=home, away=away)
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def grade_over_under(node: dict, real_value: float):
    if node is None or real_value is None or (isinstance(real_value, float) and math.isnan(real_value)):
        return None
    est = float(node["estimativa"])
    if real_value > est:
        return "OVER", est
    if real_value < est:
        return "UNDER", est
    return "PUSH", est


def main():
    print("=" * 80)
    print(" GRADE DE PRECISAO -- modelo congelado vs. resultado real (2025)")
    print("=" * 80)

    if not PREDICTIONS.exists():
        raise SystemExit(f"{PREDICTIONS} nao existe -- rode backtest_generate_predictions.py primeiro.")

    preds = pd.read_parquet(PREDICTIONS)
    fixture_ids = preds["fixture_id"].astype("int64").tolist()

    print(">> Recarregando box-score real (chutes/escanteios/cartoes)...")
    feats = load_clubs_df(min_matches=0)
    # dedup defensivo (~70 fixture_id duplicados em 272.918 linhas, achado incidental).
    feats = feats[feats["fixture_id"].isin(fixture_ids)].drop_duplicates(subset=["fixture_id"]).set_index("fixture_id")

    rows = []
    for r in preds.itertuples(index=False):
        pred = json.loads(r.prediction_json)
        home, away = r.home_team, r.away_team
        actual_hg, actual_ag = r.home_score, r.away_score
        actual_result = home if actual_hg > actual_ag else (away if actual_ag > actual_hg else "Empate")

        base = dict(fixture_id=r.fixture_id, country=r.country, tournament=r.tournament, date=r.date)

        # ---- Resultado: estrategia 1 (favoritismo) ----
        pred_fav = pred["vencedor"]["vencedor"]
        rows.append(dict(base, market="resultado", strategy="favoritismo",
                          pred=pred_fav, actual=actual_result, correct=(pred_fav == actual_result)))

        # ---- Resultado: estrategia 2 (placar exato) ----
        top1 = pred["placar_exato"]["top"][0]
        i, j = top1["mandante"], top1["visitante"]
        pred_score = home if i > j else (away if j > i else "Empate")
        rows.append(dict(base, market="resultado", strategy="placar_exato",
                          pred=pred_score, actual=actual_result, correct=(pred_score == actual_result)))

        # ---- Ambas Marcam (BTTS) -- binario Sim/Nao, fora da lista original do
        # dono mas e um mercado que o sistema ja oferece (etapa 1 pede avaliar o
        # que existe); nao entra na simulacao financeira (sem odds reais e sem
        # "estimativa" continua pra inferir margem, so Sim/Nao). ----
        real_btts = "Sim" if (actual_hg > 0 and actual_ag > 0) else "Não"
        pred_btts = pred["ambas_marcam"]["resposta"]
        rows.append(dict(base, market="ambas_marcam", strategy="classificacao",
                          pred=pred_btts, actual=real_btts, correct=(pred_btts == real_btts)))

        # ---- Gols total (over/under na estimativa) ----
        real_total_goals = actual_hg + actual_ag
        g = grade_over_under(pred.get("gols"), real_total_goals)
        if g:
            rows.append(dict(base, market="gols_total", strategy="over_under",
                              pred=g[0], actual=real_total_goals, linha=g[1],
                              correct=(g[0] != "PUSH")))

        # ---- Gols por equipe ----
        for side, real_val in (("home", actual_hg), ("away", actual_ag)):
            node = pred.get("gols_equipe", {}).get(home if side == "home" else away)
            g = grade_over_under(node, real_val)
            if g:
                rows.append(dict(base, market=f"gols_{side}", strategy="over_under",
                                  pred=g[0], actual=real_val, linha=g[1], correct=(g[0] != "PUSH")))

        # ---- Gols 1o/2o tempo (unico "tempo" com dado real) ----
        ht_h, ht_a = feats.loc[r.fixture_id, "ht_home"] if r.fixture_id in feats.index else np.nan, \
                     feats.loc[r.fixture_id, "ht_away"] if r.fixture_id in feats.index else np.nan
        tempos = pred.get("tempos", {})
        if tempos and pd.notna(ht_h) and pd.notna(ht_a):
            g1t_h, g1t_a = float(ht_h), float(ht_a)
            g2t_h, g2t_a = actual_hg - g1t_h, actual_ag - g1t_a
            for periodo, (rh, ra) in (("1t", (g1t_h, g1t_a)), ("2t", (g2t_h, g2t_a))):
                node_total = tempos.get(f"gols_{periodo}", {}).get("total")
                g = grade_over_under(node_total, rh + ra)
                if g:
                    rows.append(dict(base, market=f"gols_{periodo}_total", strategy="over_under",
                                      pred=g[0], actual=rh + ra, linha=g[1], correct=(g[0] != "PUSH")))

        # ---- Mercados de contagem (chutes/escanteios/cartoes) ----
        real = feats.loc[r.fixture_id] if r.fixture_id in feats.index else None
        for name, path_h, path_a, path_t, col_h, col_a in COUNT_MARKETS:
            if real is None or col_h not in real or col_a not in real:
                continue
            rh, ra = real[col_h], real[col_a]
            if pd.isna(rh) or pd.isna(ra):
                continue
            for side, path, real_val in (("home", path_h, rh), ("away", path_a, ra), ("total", path_t, rh + ra)):
                node = get_node(pred, path, home, away)
                g = grade_over_under(node, real_val)
                if g:
                    rows.append(dict(base, market=f"{name}_{side}", strategy="over_under",
                                      pred=g[0], actual=real_val, linha=g[1], correct=(g[0] != "PUSH")))

    grades = pd.DataFrame(rows)
    # "actual" mistura tipo por mercado (nome de time/"Empate"/"Sim"-"Nao" pros
    # mercados de classificacao, numero pros over/under) -- parquet/arrow nao aceita
    # coluna object com tipos misturados, converte pra string (so uso descritivo/
    # auditoria aqui, "correct" ja vem computado a parte).
    grades["actual"] = grades["actual"].astype(str)
    OUT_GRADES.parent.mkdir(parents=True, exist_ok=True)
    grades.to_parquet(OUT_GRADES, index=False)
    print(f">> {len(grades)} avaliacoes de mercado -> {OUT_GRADES}")

    # ---- resumo ----
    lines = ["# Resumo de precisao -- modelo congelado 2025\n"]
    lines.append("## Resultado da partida\n")
    for strat in ("favoritismo", "placar_exato"):
        sub = grades[(grades["market"] == "resultado") & (grades["strategy"] == strat)]
        acc = sub["correct"].mean() if len(sub) else float("nan")
        lines.append(f"- **{strat}**: {sub['correct'].sum()}/{len(sub)} ({100*acc:.1f}%)")

    sub_btts = grades[grades["market"] == "ambas_marcam"]
    if len(sub_btts):
        acc = sub_btts["correct"].mean()
        lines.append(f"\n## Ambas Marcam (BTTS, fora da simulacao financeira -- sem odds reais)\n")
        lines.append(f"- **classificacao Sim/Nao**: {sub_btts['correct'].sum()}/{len(sub_btts)} ({100*acc:.1f}%)")

    lines.append("\n## Demais mercados (OVER/UNDER na estimativa do modelo)\n")
    lines.append("| Mercado | N | Acertos | Taxa | OVER | UNDER | PUSH |")
    lines.append("|---|---|---|---|---|---|---|")
    ou = grades[grades["strategy"] == "over_under"]
    for market, sub in ou.groupby("market"):
        n = len(sub)
        acc = sub["correct"].sum()
        n_over = (sub["pred"] == "OVER").sum()
        n_under = (sub["pred"] == "UNDER").sum()
        n_push = (sub["pred"] == "PUSH").sum()
        lines.append(f"| {market} | {n} | {acc} | {100*acc/n:.1f}% | {n_over} | {n_under} | {n_push} |")

    lines.append("\n## Mercados sem modelo (nao avaliaveis)\n")
    for m in NOT_AVAILABLE_MARKETS:
        lines.append(f"- {m}")

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f">> Resumo -> {OUT_REPORT}")


if __name__ == "__main__":
    main()
