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

Estilo "dashboard gerencial": KPIs em cards no topo, cards de mercado
clicaveis (filtram a tabela abaixo), graficos e tabelas dentro de cards.

Financeiro cobre SOMENTE mercados com odds REAIS (resultado, over/under 2,5
gols, handicap asiatico de gols) -- os UNICOS 3 com odds de verdade em
`/data-test`. Odds inferidas (aplicando margem observada as demais
estimativas do modelo) foram REMOVIDAS do dashboard por pedido do dono --
ainda podem ser recalculadas via `backtest_infer_margins.py` se precisar,
mas nao aparecem mais aqui.

A aba Precisao mede o modelo contra o RESULTADO REAL da partida (placar/
box-score), nao envolve odds -- por isso continua cobrindo todos os
mercados avaliados (chutes/escanteios/cartoes inclusive), mesmo os que nao
tem odds reais. "Inferido" aqui e so sobre ODDS, nao sobre a avaliacao de
acerto do modelo.

Uso: python scripts/backtest_build_dashboard.py
"""
from __future__ import annotations

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
MIN_N_COMPARACAO = 20  # amostra minima p/ entrar nas comparacoes/graficos (evita ruido de N pequeno)

MARKET_LABELS = {
    "resultado": "Resultado", "gols_ou25": "Gols O/U 2,5", "handicap_gols": "Handicap asiatico",
    "ambas_marcam": "Ambas Marcam", "gols_total": "Gols (total)", "gols_home": "Gols (mandante)",
    "gols_away": "Gols (visitante)", "gols_1t_total": "Gols 1T (total)", "gols_2t_total": "Gols 2T (total)",
    "chutes_total": "Chutes (total)", "chutes_home": "Chutes (mandante)", "chutes_away": "Chutes (visitante)",
    "chutes_a_gol_total": "Chutes a gol (total)", "chutes_a_gol_home": "Chutes a gol (mandante)",
    "chutes_a_gol_away": "Chutes a gol (visitante)", "escanteios_total": "Escanteios (total)",
    "escanteios_home": "Escanteios (mandante)", "escanteios_away": "Escanteios (visitante)",
    "cartoes_total": "Cartoes (total)", "cartoes_home": "Cartoes (mandante)", "cartoes_away": "Cartoes (visitante)",
    "cartoes_amarelos_total": "Cartoes amarelos (total)", "cartoes_amarelos_home": "Cartoes amarelos (mandante)",
    "cartoes_amarelos_away": "Cartoes amarelos (visitante)", "cartoes_vermelhos_total": "Cartoes vermelhos (total)",
    "cartoes_vermelhos_home": "Cartoes vermelhos (mandante)", "cartoes_vermelhos_away": "Cartoes vermelhos (visitante)",
    "resultado_favoritismo": "Resultado (favoritismo)", "resultado_placar_exato": "Resultado (placar exato)",
}


def market_label(m: str) -> str:
    return MARKET_LABELS.get(m, m.replace("_", " ").capitalize())


def fmt_brl(v: float) -> str:
    """Formata em pt-BR (milhar '.', decimal ',') -- p/ exibicao apenas (nao usado em celula
    de tabela sortavel, essas ficam com ponto decimal simples pra nao quebrar o parseFloat do JS)."""
    neg = v < 0
    s = f"{abs(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{'-' if neg else ''}R$ {s}"


def fmt_int_brl(v: int) -> str:
    return f"{v:,}".replace(",", ".")


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


def kpi_card(label: str, value: str, sub: str = "", tone: str = "neutral") -> str:
    return f"""
    <div class="kpi-card tone-{tone}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-sub">{sub}</div>
    </div>"""


def market_card(title: str, sub: str, n: int, metric_label: str, metric_value: str, tone: str,
                onclick: str = "") -> str:
    click_attr = f" onclick='{onclick}' tabindex=\"0\"" if onclick else ""
    cls = "market-card clickable" if onclick else "market-card"
    return f"""
    <div class="{cls} tone-{tone}"{click_attr}>
      <div class="market-card-title">{title}</div>
      <div class="market-card-sub">{sub} &middot; N={n}</div>
      <div class="market-card-metric">{metric_value}</div>
      <div class="market-card-metric-label">{metric_label}</div>
    </div>"""


def filterable_table_html(df: pd.DataFrame, table_id: str, filter_cols: list[str],
                           pct_cols: tuple[str, ...] = ("roi_pct", "taxa_acerto_pct", "taxa_pct")) -> str:
    """Tabela HTML + filtros <select> em JS puro (sem libs), colunas ordenaveis por clique no
    cabecalho -- tudo client-side sobre os dados ja embutidos, sem nenhuma chamada de rede."""
    cols = list(df.columns)
    data = df.to_dict("records")
    filters_html = []
    for c in filter_cols:
        opts = sorted({str(r[c]) for r in data})
        options = "".join(f'<option value="{o}">{o}</option>' for o in opts)
        filters_html.append(
            f'<label>{c}<select onchange="filterTable_{table_id}()" id="{table_id}_f_{c}">'
            f'<option value="">(todos)</option>{options}</select></label>')

    thead = "".join(
        f'<th onclick="sortTable_{table_id}({i})" class="sortable">{c}<span class="sort-arrow"></span></th>'
        for i, c in enumerate(cols))
    rows_html = []
    for r in data:
        attrs = " ".join(f'data-{c}="{r[c]}"' for c in filter_cols)
        tds = []
        for c in cols:
            v = r[c]
            cell_cls = ""
            if c in pct_cols and isinstance(v, (int, float)) and not pd.isna(v):
                cell_cls = ' class="pos"' if v >= 0 else ' class="neg"'
            tds.append(f"<td{cell_cls}>{v}</td>")
        rows_html.append(f"<tr {attrs}>{''.join(tds)}</tr>")

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
    var sortDir_{table_id} = {{}};
    function sortTable_{table_id}(colIdx) {{
        var table = document.getElementById("{table_id}");
        var tbody = table.querySelector("tbody");
        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        var dir = sortDir_{table_id}[colIdx] = !sortDir_{table_id}[colIdx];
        rows.sort(function(a, b) {{
            var av = a.children[colIdx].innerText, bv = b.children[colIdx].innerText;
            var an = parseFloat(av.replace(",", ".")), bn = parseFloat(bv.replace(",", "."));
            var cmp = (!isNaN(an) && !isNaN(bn)) ? (an - bn) : av.localeCompare(bv);
            return dir ? cmp : -cmp;
        }});
        rows.forEach(function(r) {{ tbody.appendChild(r); }});
        table.querySelectorAll("th .sort-arrow").forEach(function(s) {{ s.textContent = ""; }});
        table.querySelectorAll("th")[colIdx].querySelector(".sort-arrow").textContent = dir ? " \\u25B2" : " \\u25BC";
    }}
    """
    return f"""
    <div class="filters">{"".join(filters_html)}</div>
    <div class="table-wrap"><table id="{table_id}"><thead><tr>{thead}</tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>
    <script>{script}</script>
    """


PLOTLY_LAYOUT = dict(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, -apple-system, Segoe UI, Arial, sans-serif", size=13, color="#1e293b"),
                      margin=dict(t=48, l=8, r=8, b=8))
COLOR_POS, COLOR_NEG, COLOR_ACCENT = "#16a34a", "#dc2626", "#4f46e5"


def cumulative_profit_chart(bets: pd.DataFrame, top_n: int = 6) -> str:
    grp = bets.groupby(["market", "strategy"]).size().sort_values(ascending=False)
    top_keys = grp.head(top_n).index.tolist()
    fig = go.Figure()
    palette = ["#4f46e5", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#7c3aed"]
    for idx, (market, strategy) in enumerate(top_keys):
        sub = bets[(bets["market"] == market) & (bets["strategy"] == strategy)].copy()
        sub = sub.sort_values("date")
        sub["profit"] = sub["won"] * sub["odd"] * STAKE - STAKE
        sub["cum_profit"] = sub["profit"].cumsum()
        label = f"{market_label(market)} / {strategy}"
        fig.add_trace(go.Scatter(x=sub["date"], y=sub["cum_profit"], mode="lines", name=label,
                                  line=dict(width=2.5, color=palette[idx % len(palette)])))
    fig.update_layout(title="Lucro acumulado -- mercados reais (top por volume de apostas)",
                       xaxis_title="Data", yaxis_title="Lucro acumulado (R$)", height=420,
                       hovermode="x unified", legend=dict(orientation="h", y=-0.2), **PLOTLY_LAYOUT)
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
    return plotly_div(fig, include_plotlyjs=True, output_type="div")


def roi_bar_chart(fin_summary: pd.DataFrame) -> str:
    sub = fin_summary[fin_summary["apostas"] >= MIN_N_COMPARACAO].sort_values("roi_pct")
    sub = sub.assign(label=sub["market"].map(market_label) + " / " + sub["strategy"] + " (" + sub["book"] + ")")
    fig = go.Figure(go.Bar(x=sub["roi_pct"], y=sub["label"], orientation="h",
                            marker_color=np.where(sub["roi_pct"] >= 0, COLOR_POS, COLOR_NEG),
                            text=sub["roi_pct"].map(lambda v: f"{v:+.1f}%"), textposition="outside"))
    fig.update_layout(title=f"ROI por mercado/estrategia -- mercados reais (N≥{MIN_N_COMPARACAO})",
                       xaxis_title="ROI (%)", height=max(320, 34 * len(sub)), **PLOTLY_LAYOUT)
    return plotly_div(fig, include_plotlyjs=False, output_type="div")


def accuracy_bar_chart(acc_summary: pd.DataFrame) -> str:
    sub = acc_summary[acc_summary["n"] >= MIN_N_COMPARACAO].sort_values("taxa_pct")
    sub = sub.assign(label=sub["market"].map(market_label))
    fig = go.Figure(go.Bar(x=sub["taxa_pct"], y=sub["label"], orientation="h",
                            marker_color=COLOR_ACCENT,
                            text=sub["taxa_pct"].map(lambda v: f"{v:.1f}%"), textposition="outside"))
    fig.add_vline(x=50, line_dash="dot", line_color="#94a3b8")
    fig.update_layout(title=f"Taxa de acerto por mercado (N≥{MIN_N_COMPARACAO})",
                       xaxis_title="Taxa de acerto (%)", height=max(320, 26 * len(sub)), **PLOTLY_LAYOUT)
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
    bets_real = bets[bets["section"] == "real"].copy()

    print(">> Agregando financeiro (somente mercados reais)...")
    fin_by_league = agg_financial(bets_real, ["market", "strategy", "book", "country", "tournament"])
    fin_overall = agg_financial(bets_real, ["market", "strategy", "book"])
    fin_market_strategy = agg_financial(bets_real, ["market", "strategy"]).sort_values("apostas", ascending=False)

    print(">> Agregando precisao...")
    acc_by_market, acc_resultado = agg_accuracy(grades, ["market"])
    acc_by_league, _ = agg_accuracy(grades, ["market", "country", "tournament"])
    acc_summary_for_chart = pd.concat([
        acc_by_market[["market", "n", "taxa_pct"]],
        acc_resultado[["market", "n", "taxa_pct"]],
    ], ignore_index=True)

    print(">> Gerando graficos...")
    chart_profit = cumulative_profit_chart(bets_real)
    chart_roi = roi_bar_chart(fin_overall)
    chart_acc = accuracy_bar_chart(acc_summary_for_chart)

    print(">> Montando KPIs e comparacoes...")
    total_jogos = int(grades["fixture_id"].nunique())
    total_apostas_real = int(fin_overall["apostas"].sum())
    lucro_total_real = float(fin_overall["lucro_liquido"].sum())
    roi_medio_real = round(100 * lucro_total_real / (total_apostas_real * STAKE), 2) if total_apostas_real else float("nan")
    period_ini, period_fim = bets_real["date"].min(), bets_real["date"].max()

    def _acc_row(market_name):
        row = acc_resultado[acc_resultado["market"] == market_name]
        return row.iloc[0] if len(row) else None

    fav = _acc_row("resultado_favoritismo")
    placar = _acc_row("resultado_placar_exato")

    kpis_html = "".join([
        kpi_card("Periodo coberto", f"{period_ini.strftime('%b/%Y')} - {period_fim.strftime('%b/%Y')}",
                 f"{total_jogos} jogos analisados"),
        kpi_card("Apostas simuladas", fmt_int_brl(total_apostas_real),
                 "somente mercados com odds reais", tone="neutral"),
        kpi_card("Lucro liquido", fmt_brl(lucro_total_real),
                 f"stake R$ {STAKE:.2f}/aposta", tone="pos" if lucro_total_real >= 0 else "neg"),
        kpi_card("ROI medio", f"{roi_medio_real:+.2f}%", "todas as estrategias ingenuas somadas",
                 tone="pos" if roi_medio_real >= 0 else "neg"),
        kpi_card("Acerto -- favoritismo", f"{fav['taxa_pct']:.1f}%" if fav is not None else "-",
                 f"N={int(fav['n'])}" if fav is not None else "", tone="accent"),
        kpi_card("Acerto -- placar exato", f"{placar['taxa_pct']:.1f}%" if placar is not None else "-",
                 f"N={int(placar['n'])}" if placar is not None else "", tone="accent"),
    ])

    market_cards_html = []
    for _, r in fin_market_strategy.iterrows():
        tone = "pos" if r["roi_pct"] >= 0 else "neg"
        market_cards_html.append(market_card(
            market_label(r["market"]), r["strategy"], int(r["apostas"]),
            "ROI", f"{r['roi_pct']:+.1f}%", tone,
            onclick=(f'document.getElementById("fin_real_f_market").value="{market_label(r["market"])}";'
                     f'filterTable_fin_real();'
                     f'document.getElementById("fin-real-table").scrollIntoView({{behavior:"smooth"}});')
        ))
    market_cards_html = "".join(market_cards_html)

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

    comparacoes_html = "".join([
        kpi_card("Liga mais lucrativa", str(melhor_liga.index[0][1]) if len(melhor_liga) else "-",
                 f"{fmt_brl(melhor_liga.iloc[0])} (N&ge;{MIN_N_COMPARACAO})" if len(melhor_liga) else "", tone="pos"),
        kpi_card("Liga menos lucrativa", str(pior_liga.index[0][1]) if len(pior_liga) else "-",
                 f"{fmt_brl(pior_liga.iloc[0])} (N&ge;{MIN_N_COMPARACAO})" if len(pior_liga) else "", tone="neg"),
        kpi_card("Mercado mais lucrativo", market_label(melhor_mercado_fin.index[0]) if len(melhor_mercado_fin) else "-",
                 f"ROI medio {melhor_mercado_fin.iloc[0]:+.1f}%" if len(melhor_mercado_fin) else "", tone="pos"),
        kpi_card("Mercado menos lucrativo", market_label(pior_mercado_fin.index[0]) if len(pior_mercado_fin) else "-",
                 f"ROI medio {pior_mercado_fin.iloc[0]:+.1f}%" if len(pior_mercado_fin) else "", tone="neg"),
        kpi_card("Maior taxa de acerto", market_label(melhor_mercado_acc["market"].iloc[0]) if len(melhor_mercado_acc) else "-",
                 f"{melhor_mercado_acc['taxa_pct'].iloc[0]:.1f}%" if len(melhor_mercado_acc) else "", tone="accent"),
        kpi_card("Menor taxa de acerto", market_label(pior_mercado_acc["market"].iloc[0]) if len(pior_mercado_acc) else "-",
                 f"{pior_mercado_acc['taxa_pct'].iloc[0]:.1f}%" if len(pior_mercado_acc) else "", tone="accent"),
    ])

    int_cols_fin = ["apostas", "vencedoras", "perdedoras"]
    real_table = filterable_table_html(
        fin_by_league.assign(market=lambda d: d["market"].map(market_label),
                              **{c: fin_by_league[c].astype(int) for c in int_cols_fin}),
        "fin_real", ["market", "strategy", "book", "country", "tournament"])
    acc_table = filterable_table_html(
        acc_by_league.assign(market=lambda d: d["market"].map(market_label),
                              n=acc_by_league["n"].astype(int), acertos=acc_by_league["acertos"].astype(int)),
        "acc", ["market", "country", "tournament"])

    html = f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest 2025 -- ApostaInfo (local)</title>
<style>
:root {{
  --bg: #f1f3f9; --card: #ffffff; --border: #e2e8f0; --text: #1e293b; --muted: #64748b;
  --accent: #4f46e5; --accent-soft: #eef2ff; --pos: #16a34a; --pos-soft: #f0fdf4;
  --neg: #dc2626; --neg-soft: #fef2f2; --radius: 14px;
  --shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 14px rgba(15,23,42,.06);
}}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--bg);
       color: var(--text); }}
.page {{ max-width: 1320px; margin: 0 auto; padding: 28px 32px 64px; }}
header.top {{ margin-bottom: 22px; }}
header.top h1 {{ font-size: 1.5rem; margin: 0 0 6px; font-weight: 800; letter-spacing: -.02em; }}
header.top p {{ margin: 0; color: var(--muted); font-size: .88rem; max-width: 820px; line-height: 1.5; }}
header.top code {{ background: #e2e8f0; padding: 1px 5px; border-radius: 4px; font-size: .82em; }}

nav.tabs {{ display: flex; gap: 6px; margin: 22px 0 20px; border-bottom: 1px solid var(--border); }}
.tab-btn {{ padding: 10px 18px; cursor: pointer; border: none; background: none; font-size: .9rem;
           font-weight: 600; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px;
           transition: color .15s, border-color .15s; }}
.tab-btn:hover {{ color: var(--text); }}
.tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
.tab-content {{ display: none; }} .tab-content.active {{ display: block; animation: fadein .25s ease; }}
@keyframes fadein {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}

.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 24px; }}
.kpi-card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
            padding: 16px 18px; box-shadow: var(--shadow); }}
.kpi-label {{ font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }}
.kpi-value {{ font-size: 1.55rem; font-weight: 800; margin-top: 6px; letter-spacing: -.01em; }}
.kpi-sub {{ font-size: .78rem; color: var(--muted); margin-top: 4px; }}
.kpi-card.tone-pos .kpi-value {{ color: var(--pos); }} .kpi-card.tone-neg .kpi-value {{ color: var(--neg); }}
.kpi-card.tone-accent .kpi-value {{ color: var(--accent); }}

.market-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 16px 0 26px; }}
.market-card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
               padding: 14px 16px; box-shadow: var(--shadow); }}
.market-card.clickable {{ cursor: pointer; transition: transform .12s, box-shadow .12s; }}
.market-card.clickable:hover {{ transform: translateY(-3px); box-shadow: 0 8px 20px rgba(15,23,42,.10); }}
.market-card.clickable:focus {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
.market-card-title {{ font-weight: 700; font-size: .92rem; }}
.market-card-sub {{ font-size: .74rem; color: var(--muted); margin-top: 2px; text-transform: capitalize; }}
.market-card-metric {{ font-size: 1.3rem; font-weight: 800; margin-top: 10px; }}
.market-card-metric-label {{ font-size: .7rem; color: var(--muted); }}
.market-card.tone-pos .market-card-metric {{ color: var(--pos); }}
.market-card.tone-neg .market-card-metric {{ color: var(--neg); }}

.card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
        box-shadow: var(--shadow); padding: 18px 20px; margin-bottom: 22px; }}
.card h2 {{ margin: 0 0 4px; font-size: 1.02rem; font-weight: 800; }}
.card .card-note {{ font-size: .8rem; color: var(--muted); margin: 0 0 14px; }}

.warn {{ background: var(--accent-soft); border: 1px solid #c7d2fe; color: #3730a3; padding: 12px 16px;
        border-radius: 10px; margin: 0 0 20px; font-size: .85rem; line-height: 1.5; }}

.filters {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 0 0 12px; }}
.filters label {{ font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }}
.filters select {{ display: block; margin-top: 4px; font-size: .85rem; padding: 5px 8px; border-radius: 6px;
                   border: 1px solid var(--border); background: #fff; color: var(--text); min-width: 130px; }}

.table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }}
table {{ border-collapse: collapse; width: 100%; font-size: .82rem; }}
th, td {{ padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }}
th {{ background: #f8fafc; position: sticky; top: 0; font-weight: 700; color: var(--muted); cursor: pointer;
     user-select: none; font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; }}
th:hover {{ color: var(--accent); }}
.sort-arrow {{ font-size: .65rem; }}
td:first-child, th:first-child {{ text-align: left; }}
tbody tr:hover {{ background: #f8fafc; }}
td.pos {{ color: var(--pos); font-weight: 600; }} td.neg {{ color: var(--neg); font-weight: 600; }}
</style></head>
<body>
<div class="page">

<header class="top">
  <h1>Backtest local 2025 -- precisao e retorno financeiro</h1>
  <p>Modelo CONGELADO (treinado so com dados anteriores a 2025/26, sem vazamento) rodado contra
  <code>/data-test</code> (football-data.co.uk). Financeiro cobre apenas mercados com odds REAIS
  (resultado, over/under 2,5 gols, handicap asiatico) -- estrategias ingenuas (sempre favorito, sempre
  over, etc.), sem edge, servem de referencia de custo de mercado, nao de recomendacao de aposta.</p>
</header>

<div class="kpi-grid">{kpis_html}</div>

<nav class="tabs">
  <button class="tab-btn active" onclick="showTab(event,'financeiro')">Financeiro</button>
  <button class="tab-btn" onclick="showTab(event,'precisao')">Precisao</button>
  <button class="tab-btn" onclick="showTab(event,'comparacoes')">Comparacoes</button>
</nav>

<div id="financeiro" class="tab-content active">
  <div class="warn"><b>Somente odds reais.</b> Escanteios/chutes/cartoes nao tem odds de mercado em
  <code>/data-test</code> e por isso ficam FORA do financeiro (avaliados so na aba Precisao, contra o
  box-score real, sem envolver dinheiro). <b>Brasileirao:</b> parte dos jogos usados aqui (93 de 306,
  filtre por country=Brazil na tabela abaixo) sao anteriores ao corte de treino do modelo congelado
  (2025-07-01) -- potencialmente vistos no treino (achado de auditoria 2026-07-22, impacto pequeno em
  precisao/taxa de acerto, maior em ROI -- detalhe em <code>data/reports/adhoc_valuebet_w3/</code>).</div>

  <div class="market-grid">{market_cards_html}</div>

  <div class="card">{chart_profit}</div>
  <div class="card">{chart_roi}</div>

  <div class="card" id="fin-real-table">
    <h2>Detalhe por liga e casa de apostas</h2>
    <p class="card-note">Clique num card de mercado acima pra filtrar, ou use os filtros abaixo. Clique no cabecalho pra ordenar.</p>
    {real_table}
  </div>
</div>

<div id="precisao" class="tab-content">
  <div class="warn">Mede a estimativa do modelo contra o resultado REAL da partida (placar/box-score) --
  nao envolve odds, por isso inclui todos os mercados (inclusive os sem odds reais, como chutes/escanteios/cartoes).</div>
  <div class="card">{chart_acc}</div>
  <div class="card">
    <h2>Precisao por mercado e liga</h2>
    <p class="card-note">Clique no cabecalho pra ordenar; use os filtros pra restringir por liga.</p>
    {acc_table}
  </div>
</div>

<div id="comparacoes" class="tab-content">
  <div class="kpi-grid">{comparacoes_html}</div>
  <div class="card">
    <p class="card-note">Temporada: unica disponivel nos dados (2025/26) -- comparacao melhor/pior
    temporada nao se aplica ainda (precisa de mais de uma temporada coletada em <code>/data-test</code>).</p>
  </div>
</div>

</div>
<script>
function showTab(evt, id) {{
    document.querySelectorAll(".tab-content").forEach(function(el) {{ el.classList.remove("active"); }});
    document.querySelectorAll(".tab-btn").forEach(function(el) {{ el.classList.remove("active"); }});
    document.getElementById(id).classList.add("active");
    evt.currentTarget.classList.add("active");
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
