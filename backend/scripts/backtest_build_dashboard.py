#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_build_dashboard.py
====================================
Etapa 6/7/8 do modulo de backtest: monta um unico HTML autocontido
(`data/reports/backtest_dashboard.html`) com os resultados ja calculados
(backtest_bets.parquet + backtest_grades.parquet). Sem servidor, sem
dependencia de rede -- Plotly embutido inline (offline), filtros em
JavaScript puro sobre os dados ja agregados (nenhum recalculo ao abrir).

Abas: Financeiro (Real x Inferido bem separados) / Precisao / Comparacoes.

Uso: python scripts/backtest_build_dashboard.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import plot as plotly_div

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BETS = ROOT / "data" / "built" / "backtest_bets.parquet"
GRADES = ROOT / "data" / "built" / "backtest_grades.parquet"
OUT = ROOT / "data" / "reports" / "backtest_dashboard.html"

STAKE = 5.0
MIN_N_COMPARACAO = 20  # amostra minima p/ entrar nas comparacoes melhor/pior (evita ruido de N pequeno)


def agg_financial(bets: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    def _agg(g):
        n = len(g)
        wins = int(g["won"].sum())
        stake_total = n * STAKE
        retorno = float((g["won"] * g["odd"] * STAKE).sum())
        lucro = retorno - stake_total
        return pd.Series({
            "apostas": n, "vencedoras": wins, "perdedoras": n - wins,
            "stake_total": round(stake_total, 2), "retorno_bruto": round(retorno, 2),
            "lucro_liquido": round(lucro, 2),
            "roi_pct": round(100 * lucro / stake_total, 2) if n else np.nan,
            "yield_pct": round(100 * lucro / stake_total, 2) if n else np.nan,
            "taxa_acerto_pct": round(100 * wins / n, 1) if n else np.nan,
            "odd_media": round(float(g["odd"].mean()), 3) if n else np.nan,
            "odd_mediana": round(float(g["odd"].median()), 3) if n else np.nan,
        })
    return bets.groupby(group_cols, dropna=False).apply(_agg, include_groups=False).reset_index()


def agg_accuracy(grades: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    sub = grades[grades["market"] != "resultado"].copy()
    sub = sub[sub["pred"] != "PUSH"] if "pred" in sub.columns else sub

    def _agg(g):
        n = len(g)
        acertos = int(g["correct"].sum())
        return pd.Series({"n": n, "acertos": acertos,
                           "taxa_pct": round(100 * acertos / n, 1) if n else np.nan})
    acc = sub.groupby(group_cols, dropna=False).apply(_agg, include_groups=False).reset_index()

    res = grades[grades["market"] == "resultado"]
    res_agg = res.groupby(["strategy"] + [c for c in group_cols if c != "market"], dropna=False).apply(
        lambda g: pd.Series({"n": len(g), "acertos": int(g["correct"].sum()),
                              "taxa_pct": round(100 * g["correct"].sum() / len(g), 1) if len(g) else np.nan}),
        include_groups=False).reset_index()
    res_agg["market"] = "resultado_" + res_agg["strategy"]
    return acc, res_agg


def filterable_table_html(df: pd.DataFrame, table_id: str, filter_cols: list[str]) -> str:
    """Tabela HTML + filtros <select> em JS puro (sem libs) -- filtra client-side
    sobre os dados ja embutidos, sem nenhuma chamada de rede."""
    cols = list(df.columns)
    data = df.to_dict("records")
    filters_html = []
    for c in filter_cols:
        opts = sorted({str(r[c]) for r in data})
        options = "".join(f'<option value="{o}">{o}</option>' for o in opts)
        filters_html.append(
            f'<label>{c}: <select onchange="filterTable_{table_id}()" id="{table_id}_f_{c}">'
            f'<option value="">(todos)</option>{options}</select></label>')

    thead = "".join(f"<th>{c}</th>" for c in cols)
    rows_html = []
    for r in data:
        attrs = " ".join(f'data-{c}="{r[c]}"' for c in filter_cols)
        tds = "".join(f"<td>{r[c]}</td>" for c in cols)
        rows_html.append(f"<tr {attrs}>{tds}</tr>")

    script = f"""
    function filterTable_{table_id}() {{
        var filters = {{}};
        {"".join(f'filters["{c}"] = document.getElementById("{table_id}_f_{c}").value;' for c in filter_cols)}
        var rows = document.querySelectorAll("#{table_id} tbody tr");
        rows.forEach(function(row) {{
            var show = true;
            for (var key in filters) {{
                if (filters[key] && row.getAttribute("data-" + key) !== filters[key]) show = false;
            }}
            row.style.display = show ? "" : "none";
        }});
    }}
    """
    return f"""
    <div class="filters">{"".join(filters_html)}</div>
    <table id="{table_id}"><thead><tr>{thead}</tr></thead><tbody>{"".join(rows_html)}</tbody></table>
    <script>{script}</script>
    """


def cumulative_profit_chart(bets: pd.DataFrame, top_n: int = 8) -> str:
    grp = bets.groupby(["section", "market", "strategy"]).size().sort_values(ascending=False)
    top_keys = grp.head(top_n).index.tolist()
    fig = go.Figure()
    for section, market, strategy in top_keys:
        sub = bets[(bets["section"] == section) & (bets["market"] == market) & (bets["strategy"] == strategy)].copy()
        sub = sub.sort_values("date")
        sub["profit"] = sub["won"] * sub["odd"] * STAKE - STAKE
        sub["cum_profit"] = sub["profit"].cumsum()
        label = f"[{section}] {market}/{strategy}"
        fig.add_trace(go.Scatter(x=sub["date"], y=sub["cum_profit"], mode="lines", name=label))
    fig.update_layout(title="Lucro acumulado (top mercados por volume de apostas)",
                       xaxis_title="Data", yaxis_title="Lucro acumulado (R$)", height=500,
                       template="plotly_white")
    return plotly_div(fig, include_plotlyjs=True, output_type="div")


def roi_bar_chart(fin_summary: pd.DataFrame) -> str:
    sub = fin_summary[fin_summary["apostas"] >= MIN_N_COMPARACAO].sort_values("roi_pct")
    fig = go.Figure(go.Bar(x=sub["roi_pct"], y=sub["label"], orientation="h",
                            marker_color=np.where(sub["roi_pct"] >= 0, "seagreen", "firebrick")))
    fig.update_layout(title=f"ROI por mercado/estrategia (N>={MIN_N_COMPARACAO})",
                       xaxis_title="ROI (%)", height=max(400, 24 * len(sub)), template="plotly_white")
    return plotly_div(fig, include_plotlyjs=False, output_type="div")


def accuracy_bar_chart(acc_summary: pd.DataFrame) -> str:
    sub = acc_summary[acc_summary["n"] >= MIN_N_COMPARACAO].sort_values("taxa_pct")
    fig = go.Figure(go.Bar(x=sub["taxa_pct"], y=sub["market"], orientation="h", marker_color="steelblue"))
    fig.update_layout(title=f"Taxa de acerto por mercado (N>={MIN_N_COMPARACAO})",
                       xaxis_title="Taxa de acerto (%)", height=max(400, 24 * len(sub)), template="plotly_white")
    return plotly_div(fig, include_plotlyjs=False, output_type="div")


def main():
    print("=" * 80)
    print(" DASHBOARD LOCAL -- backtest 2025")
    print("=" * 80)

    if not BETS.exists() or not GRADES.exists():
        raise SystemExit(f"{BETS} / {GRADES} nao encontrados -- rode as etapas anteriores primeiro.")

    bets = pd.read_parquet(BETS)
    grades = pd.read_parquet(GRADES)
    bets["date"] = pd.to_datetime(bets["date"])

    print(">> Agregando financeiro...")
    fin_by_league = agg_financial(bets, ["section", "market", "strategy", "book", "country", "tournament"])
    fin_overall = agg_financial(bets, ["section", "market", "strategy", "book"])
    fin_overall["label"] = fin_overall["section"] + "/" + fin_overall["market"] + "/" + fin_overall["strategy"] + " (" + fin_overall["book"] + ")"

    print(">> Agregando precisao...")
    acc_by_market, acc_resultado = agg_accuracy(grades, ["market"])
    acc_by_league, _ = agg_accuracy(grades, ["market", "country", "tournament"])
    acc_summary_for_chart = pd.concat([
        acc_by_market.rename(columns={"n": "n", "taxa_pct": "taxa_pct"})[["market", "n", "taxa_pct"]],
        acc_resultado.rename(columns={"n": "n", "taxa_pct": "taxa_pct"})[["market", "n", "taxa_pct"]],
    ], ignore_index=True)

    print(">> Gerando graficos...")
    chart_profit = cumulative_profit_chart(bets)
    chart_roi = roi_bar_chart(fin_overall)
    chart_acc = accuracy_bar_chart(acc_summary_for_chart)

    print(">> Montando comparacoes...")
    fin_valid = fin_by_league[fin_by_league["apostas"] >= MIN_N_COMPARACAO]
    by_league_roi = fin_valid.groupby(["country", "tournament"])["lucro_liquido"].sum().sort_values()
    melhor_liga = by_league_roi.tail(1)
    pior_liga = by_league_roi.head(1)
    by_market_roi = fin_overall[fin_overall["apostas"] >= MIN_N_COMPARACAO].groupby("market")["roi_pct"].mean().sort_values()
    melhor_mercado_fin = by_market_roi.tail(1)
    pior_mercado_fin = by_market_roi.head(1)
    acc_valid = acc_summary_for_chart[acc_summary_for_chart["n"] >= MIN_N_COMPARACAO].sort_values("taxa_pct")
    melhor_mercado_acc = acc_valid.tail(1)
    pior_mercado_acc = acc_valid.head(1)

    comparacoes_html = f"""
    <h3>Liga</h3>
    <p>Melhor (lucro liquido somado, N&gt;={MIN_N_COMPARACAO}): <b>{melhor_liga.index[0] if len(melhor_liga) else '-'}</b>
       (R${melhor_liga.iloc[0]:.2f})</p>
    <p>Pior: <b>{pior_liga.index[0] if len(pior_liga) else '-'}</b> (R${pior_liga.iloc[0]:.2f})</p>
    <h3>Mercado (financeiro)</h3>
    <p>Mais lucrativo (ROI medio): <b>{melhor_mercado_fin.index[0] if len(melhor_mercado_fin) else '-'}</b>
       ({melhor_mercado_fin.iloc[0]:.1f}%)</p>
    <p>Menos lucrativo: <b>{pior_mercado_fin.index[0] if len(pior_mercado_fin) else '-'}</b>
       ({pior_mercado_fin.iloc[0]:.1f}%)</p>
    <h3>Mercado (precisao)</h3>
    <p>Maior taxa de acerto: <b>{melhor_mercado_acc['market'].iloc[0] if len(melhor_mercado_acc) else '-'}</b>
       ({melhor_mercado_acc['taxa_pct'].iloc[0] if len(melhor_mercado_acc) else '-'}%)</p>
    <p>Menor taxa de acerto: <b>{pior_mercado_acc['market'].iloc[0] if len(pior_mercado_acc) else '-'}</b>
       ({pior_mercado_acc['taxa_pct'].iloc[0] if len(pior_mercado_acc) else '-'}%)</p>
    <h3>Temporada</h3>
    <p>Unica temporada disponivel nos dados (2025/26) -- comparacao melhor/pior temporada
       nao se aplica ainda (precisa de mais de uma temporada coletada em `/data-test`).</p>
    """

    real_table = filterable_table_html(
        fin_by_league[fin_by_league["section"] == "real"].drop(columns=["section"]),
        "fin_real", ["market", "strategy", "book", "country", "tournament"])
    inferred_table = filterable_table_html(
        fin_by_league[fin_by_league["section"] == "inferido"].drop(columns=["section"]),
        "fin_inf", ["market", "strategy", "country", "tournament"])
    acc_table = filterable_table_html(acc_by_league, "acc", ["market", "country", "tournament"])

    html = f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Backtest 2025 -- ApostaInfo (local)</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 24px; color: #1a1a1a; }}
h1 {{ font-size: 1.4rem; }} h2 {{ margin-top: 2.5rem; border-bottom: 2px solid #ddd; padding-bottom: .3rem; }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 1rem; }}
.tab-btn {{ padding: 8px 16px; cursor: pointer; border: 1px solid #ccc; border-radius: 6px 6px 0 0; background: #f0f0f0; }}
.tab-btn.active {{ background: #fff; border-bottom: 1px solid #fff; font-weight: bold; }}
.tab-content {{ display: none; }} .tab-content.active {{ display: block; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .85rem; }}
th, td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: right; }}
th {{ background: #fafafa; position: sticky; top: 0; }}
td:first-child, th:first-child {{ text-align: left; }}
.filters {{ margin: .5rem 0; }} .filters select {{ margin-right: 12px; }}
.warn {{ background: #fff3cd; border: 1px solid #ffe08a; padding: 10px; border-radius: 6px; margin: 1rem 0; }}
</style></head>
<body>
<h1>Backtest local 2025 -- precisao e retorno financeiro (modelo congelado, sem vazamento)</h1>
<p>Gerado a partir de <code>/data-test</code> (football-data.co.uk) cruzado com o sistema de previsao,
usando um artefato treinado SO com dados anteriores a 2025/26 (ver <code>backtest_train_frozen_model.py</code>).</p>

<div class="tabs">
  <div class="tab-btn active" onclick="showTab('financeiro')">Financeiro</div>
  <div class="tab-btn" onclick="showTab('precisao')">Precisao</div>
  <div class="tab-btn" onclick="showTab('comparacoes')">Comparacoes</div>
</div>

<div id="financeiro" class="tab-content active">
  <div class="warn"><b>Odds REAIS</b> (resultado, over/under 2,5 gols, handicap asiatico de gols) --
  os UNICOS 3 mercados com odds de verdade em <code>/data-test</code>.</div>
  {chart_profit}
  {chart_roi}
  <h2>Odds reais</h2>
  {real_table}
  <div class="warn"><b>Odds INFERIDAS</b> (escanteios/chutes/chutes a gol/cartoes) -- NAO sao odds reais,
  foram calculadas aplicando o padrao de margem observado nas odds reais as probabilidades do nosso
  modelo (ver <code>data/reports/backtest_margin_fit.md</code> pro ajuste). Trate como especulativo.</div>
  <h2>Odds inferidas</h2>
  {inferred_table}
</div>

<div id="precisao" class="tab-content">
  {chart_acc}
  <h2>Precisao por mercado e liga</h2>
  {acc_table}
</div>

<div id="comparacoes" class="tab-content">
  <h2>Comparacoes</h2>
  {comparacoes_html}
</div>

<script>
function showTab(id) {{
    document.querySelectorAll(".tab-content").forEach(function(el) {{ el.classList.remove("active"); }});
    document.querySelectorAll(".tab-btn").forEach(function(el) {{ el.classList.remove("active"); }});
    document.getElementById(id).classList.add("active");
    event.target.classList.add("active");
}}
</script>
</body></html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n>> Dashboard -> {OUT}")


if __name__ == "__main__":
    main()
