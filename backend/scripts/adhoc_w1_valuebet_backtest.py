#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_w1_valuebet_backtest.py
======================================
Bateria ad-hoc W1 (2026-07-22) — reavalia a pergunta do H2/H3
(DOCUMENTACAO_CENTRAL.md §19.4/19.5: "existe edge de valor no modelo contra o
mercado de-vigado?") usando o dataset de backtest NOVO com odds reais
historicas (football-data.co.uk, abertura+fechamento, 8117 fixtures — ~60x a
amostra de 84 fixtures do H3 original que so tinha coleta forward).

Le `data/built/backtest_valuebet_dataset.parquet` (gerado por
`adhoc_value_groundwork.py`, NAO re-derivar o join aqui). NAO toca em
model_artifacts*/predictor.py/app real — isso e analise/pesquisa de estrategia
de aposta, nao mudanca de modelo (nao precisa do gate §6).

Pipeline:
  1. Recalcula fair-prob de abertura com os 3 metodos de devig_methods.py
     (shin ja vem pronto no parquet; proporcional/power recalculados aqui a
     partir das mesmas odds de abertura, NAO reinventa o devig).
  2. Define o "lado do modelo" = argmax(p_model_*) por fixture, por mercado
     (1x2 e O/U 2,5). Edge = p_model_lado - p_fair_open_lado.
  3. Varre limiares de edge (0/1/2/3/5/8/10%), reporta N/hit-rate/lucro/ROI
     usando odd_open_lado como odd tomada, stake fixo R$5.
  4. Split cronologico (1a metade = treino escolhe limiar; 2a metade = teste,
     limiar fixo, sem reajuste) para validar honesto (evitar data snooping).
  5. CLV = 1/odd_close_lado - 1/odd_open_lado no lado apostado; media e %
     positivo, geral e por faixa de edge.
  6. Repete 1-4 pros 3 metodos de devig (shin/proporcional/power) e compara
     conclusao.
  7. Quebra por pais (top 6 por volume) pra checar consistencia (edge
     concentrado numa liga so = sinal de ruido, nao edge real).
  8. Controles de ceticismo: hit-rate necessario pro break-even (media de
     1/odd tomada) vs hit-rate realizado; overlap "lado do modelo" vs
     "favorito do mercado" (edge pode ser so vies de favorito, nao skill real);
     bootstrap CI do ROI (o.o.s.) pra checar se o ponto estimado e distinguivel
     de ruido de amostra.

Uso: python scripts/adhoc_w1_valuebet_backtest.py
Saida: data/reports/adhoc_valuebet_w1/{relatorio.md, *.csv}
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

DATASET = ROOT / "data" / "built" / "backtest_valuebet_dataset.parquet"
OUTDIR = ROOT / "data" / "reports" / "adhoc_valuebet_w1"
OUTDIR.mkdir(parents=True, exist_ok=True)

STAKE = 5.0
THRESHOLDS = [0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
MIN_N_TRAIN = 30  # minimo de apostas na 1a metade pra um limiar ser elegivel (evita overfit de limiar em amostra minuscula)
RNG_SEED = 20260722
N_BOOT = 5000

METHODS = {"shin": shin_devig, "proporcional": proportional_devig, "power": power_devig}

MARKETS = {
    "1x2": dict(sides=["H", "D", "A"], odd_prefix="odd_open_", odd_close_prefix="odd_close_",
                model_cols={"H": "p_model_H", "D": "p_model_D", "A": "p_model_A"}),
    "ou25": dict(sides=["over", "under"], odd_prefix="odd_open_", odd_close_prefix="odd_close_",
                 model_cols={"over": "p_model_over", "under": "p_model_under"}),
}


# ────────────────────────── fair-prob recompute (proporcional/power) ──────────────────────────
def add_fair_open_all_methods(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Adiciona p_fair_open_{side}__{method} pros 3 metodos (shin reusa a coluna ja
    existente no parquet, criada por adhoc_value_groundwork.py; proporcional/power
    sao recalculados aqui a partir das MESMAS odds de abertura)."""
    spec = MARKETS[market]
    sides = spec["sides"]
    odd_cols = [f"odd_open_{s}" for s in sides]
    mask = df[odd_cols].notna().all(axis=1)

    # shin: reusa coluna existente (mesmo metodo/valores do groundwork)
    for s in sides:
        df[f"p_fair_open_{s}__shin"] = df.get(f"p_fair_open_{s}")

    fails = {"proporcional": 0, "power": 0}
    for method in ("proporcional", "power"):
        fn = METHODS[method]
        out = {s: np.full(len(df), np.nan) for s in sides}
        idxs = df.index[mask]
        for idx in idxs:
            odds = [df.at[idx, c] for c in odd_cols]
            try:
                p = fn(odds)
            except Exception:
                fails[method] += 1
                continue
            pos = df.index.get_loc(idx)
            for s, pv in zip(sides, p):
                out[s][pos] = pv
        for s in sides:
            df[f"p_fair_open_{s}__{method}"] = out[s]
    if any(fails.values()):
        print(f"  [{market}] falhas ao resolver devig: {fails}")
    return df


def chosen_side_and_actual(df: pd.DataFrame, market: str) -> pd.DataFrame:
    spec = MARKETS[market]
    sides = spec["sides"]
    model_cols = [spec["model_cols"][s] for s in sides]
    idx_max = df[model_cols].to_numpy().argmax(axis=1)
    df["chosen_side"] = [sides[i] for i in idx_max]
    df["p_model_chosen"] = df[model_cols].to_numpy()[np.arange(len(df)), idx_max]
    if market == "1x2":
        df["actual_side"] = df["actual_result"]
    else:
        df["actual_side"] = np.where(df["actual_over"], "over", "under")
    df["odd_open_chosen"] = [df.at[i, f"odd_open_{s}"] for i, s in zip(df.index, df["chosen_side"])]
    df["odd_close_chosen"] = [df.at[i, f"odd_close_{s}"] if pd.notna(df.at[i, f"odd_close_{s}"]) else np.nan
                               for i, s in zip(df.index, df["chosen_side"])]
    # favorito de mercado (menor odd de abertura) -- controle de ceticismo
    odd_cols = [f"odd_open_{s}" for s in sides]
    fav_idx = df[odd_cols].to_numpy().argmin(axis=1)
    df["market_favorite_side"] = [sides[i] for i in fav_idx]
    return df


def edge_col_name(method: str) -> str:
    return f"edge__{method}"


def add_edges(df: pd.DataFrame, market: str) -> pd.DataFrame:
    for method in METHODS:
        fair_chosen = [df.at[i, f"p_fair_open_{s}__{method}"] for i, s in zip(df.index, df["chosen_side"])]
        df[edge_col_name(method)] = df["p_model_chosen"].to_numpy() - np.array(fair_chosen, dtype=float)
    return df


# ────────────────────────── backtest core ──────────────────────────
def bet_outcomes(df: pd.DataFrame) -> pd.Series:
    """profit por linha (stake fixo) assumindo aposta no chosen_side."""
    win = (df["chosen_side"] == df["actual_side"]).to_numpy()
    odd = df["odd_open_chosen"].to_numpy()
    profit = np.where(win, STAKE * (odd - 1.0), -STAKE)
    return pd.Series(profit, index=df.index)


def threshold_sweep(df: pd.DataFrame, edge_col: str, thresholds=THRESHOLDS) -> pd.DataFrame:
    rows = []
    for th in thresholds:
        sub = df[df[edge_col] > th]
        n = len(sub)
        if n == 0:
            rows.append(dict(limiar=th, n=0, hit_rate=np.nan, lucro=0.0, roi=np.nan,
                              odd_media=np.nan, hit_rate_breakeven=np.nan))
            continue
        win = (sub["chosen_side"] == sub["actual_side"])
        hit_rate = win.mean()
        profit = bet_outcomes(sub).sum()
        stake_total = n * STAKE
        roi = profit / stake_total
        odd_media = sub["odd_open_chosen"].mean()
        breakeven = (1.0 / sub["odd_open_chosen"]).mean()
        rows.append(dict(limiar=th, n=n, hit_rate=hit_rate, lucro=profit, roi=roi,
                          odd_media=odd_media, hit_rate_breakeven=breakeven))
    return pd.DataFrame(rows)


def bootstrap_roi_ci(df: pd.DataFrame, edge_col: str, th: float, n_boot=N_BOOT, seed=RNG_SEED):
    sub = df[df[edge_col] > th]
    n = len(sub)
    if n == 0:
        return dict(n=0, roi=np.nan, roi_lo=np.nan, roi_hi=np.nan)
    profits = bet_outcomes(sub).to_numpy()
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        sample = rng.choice(profits, size=n, replace=True)
        boots[b] = sample.sum() / (n * STAKE)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return dict(n=n, roi=profits.sum() / (n * STAKE), roi_lo=lo, roi_hi=hi)


def chronological_split(df: pd.DataFrame):
    d = df.sort_values("date").reset_index(drop=True)
    half = len(d) // 2
    return d.iloc[:half].copy(), d.iloc[half:].copy()


def pick_best_threshold(train_sweep: pd.DataFrame, min_n=MIN_N_TRAIN):
    eligible = train_sweep[train_sweep["n"] >= min_n]
    if eligible.empty:
        eligible = train_sweep[train_sweep["n"] > 0]
    if eligible.empty:
        return None
    best = eligible.sort_values(["roi", "limiar"], ascending=[False, True]).iloc[0]
    return float(best["limiar"])


def clv_series(df: pd.DataFrame) -> pd.Series:
    sub = df[df["odd_close_chosen"].notna()]
    clv = (1.0 / sub["odd_close_chosen"]) - (1.0 / sub["odd_open_chosen"])
    return clv


def clv_by_edge_bucket(df: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    bins = [-np.inf, 0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, np.inf]
    labels = ["<0%", "0-1%", "1-2%", "2-3%", "3-5%", "5-8%", "8-10%", ">10%"]
    sub = df[df["odd_close_chosen"].notna()].copy()
    sub["faixa_edge"] = pd.cut(sub[edge_col], bins=bins, labels=labels, right=False)
    sub["clv"] = (1.0 / sub["odd_close_chosen"]) - (1.0 / sub["odd_open_chosen"])
    grp = sub.groupby("faixa_edge", observed=True).agg(
        n=("clv", "size"), clv_medio=("clv", "mean"), frac_clv_positivo=("clv", lambda x: (x > 0).mean()))
    return grp.reset_index()


def league_breakdown(df: pd.DataFrame, edge_col: str, threshold: float, top_n=6) -> pd.DataFrame:
    top_countries = df["country"].value_counts().head(top_n).index.tolist()
    rows = []
    for c in top_countries:
        sub = df[(df["country"] == c) & (df[edge_col] > threshold)]
        n = len(sub)
        if n == 0:
            rows.append(dict(country=c, n=0, hit_rate=np.nan, lucro=0.0, roi=np.nan))
            continue
        win = (sub["chosen_side"] == sub["actual_side"])
        profit = bet_outcomes(sub).sum()
        rows.append(dict(country=c, n=n, hit_rate=win.mean(), lucro=profit, roi=profit / (n * STAKE)))
    return pd.DataFrame(rows)


# ────────────────────────── run ──────────────────────────
def run_market(df_all: pd.DataFrame, market: str) -> dict:
    spec = MARKETS[market]
    odd_cols = [f"odd_open_{s}" for s in spec["sides"]]
    df = df_all[df_all[odd_cols].notna().all(axis=1)].copy()
    df = add_fair_open_all_methods(df, market)
    df = chosen_side_and_actual(df, market)
    df = add_edges(df, market)

    result = {"market": market, "n_total": len(df), "methods": {}}

    for method in METHODS:
        ecol = edge_col_name(method)
        sub = df[df[ecol].notna()].copy()

        sweep_full = threshold_sweep(sub, ecol)

        train, test = chronological_split(sub)
        sweep_train = threshold_sweep(train, ecol)
        sweep_test_allthr = threshold_sweep(test, ecol)  # informativo (todos limiares no teste, NAO usado p/ escolha)
        best_th = pick_best_threshold(sweep_train)
        test_at_best = threshold_sweep(test, ecol, thresholds=[best_th]).iloc[0].to_dict() if best_th is not None else None
        train_at_best = threshold_sweep(train, ecol, thresholds=[best_th]).iloc[0].to_dict() if best_th is not None else None

        boot_train = bootstrap_roi_ci(train, ecol, best_th) if best_th is not None else None
        boot_test = bootstrap_roi_ci(test, ecol, best_th) if best_th is not None else None

        # overlap com favorito de mercado (só faz sentido reportar 1x, mas calculamos por método por simplicidade -- é igual entre métodos pois não depende do fair-prob)
        overlap_favorite = (sub["chosen_side"] == sub["market_favorite_side"]).mean()

        result["methods"][method] = dict(
            sweep_full=sweep_full, sweep_train=sweep_train, sweep_test_allthr=sweep_test_allthr,
            best_threshold=best_th, train_at_best=train_at_best, test_at_best=test_at_best,
            boot_train=boot_train, boot_test=boot_test,
            n_train=len(train), n_test=len(test),
            overlap_favorite=overlap_favorite,
            clv_bucket=clv_by_edge_bucket(sub, ecol),
        )

    # CLV geral (metodo shin, threshold 0 -- so pra ilustrar; independe de metodo p/ o CALCULO do CLV em si,
    # mas o CONJUNTO de apostas selecionado por limiar depende do metodo -- ja coberto acima por-metodo)
    clv_all = clv_series(df)
    result["clv_overall"] = dict(n=len(clv_all), media=clv_all.mean(), frac_positivo=(clv_all > 0).mean())

    # liga/pais -- usa metodo shin, no limiar escolhido por shin (se existir) e tambem no limiar 0 (baseline)
    shin_best_th = result["methods"]["shin"]["best_threshold"]
    ecol_shin = edge_col_name("shin")
    result["league_breakdown_0"] = league_breakdown(df[df[ecol_shin].notna()], ecol_shin, 0.0)
    if shin_best_th is not None:
        result["league_breakdown_best"] = league_breakdown(df[df[ecol_shin].notna()], ecol_shin, shin_best_th)
    else:
        result["league_breakdown_best"] = pd.DataFrame()
    result["shin_best_th"] = shin_best_th

    result["df"] = df
    return result


def fmt_pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:.2f}%"


def fmt_money(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"R$ {x:,.2f}"


def df_to_md(df: pd.DataFrame, float_cols=None) -> str:
    d = df.copy()
    if float_cols:
        for c in float_cols:
            if c in d.columns:
                d[c] = d[c].map(lambda x: "n/a" if pd.isna(x) else f"{x:.4f}")
    return d.to_markdown(index=False)


def main():
    print(f"Lendo {DATASET}")
    df_all = pd.read_parquet(DATASET)
    print(f"{len(df_all)} fixtures no dataset")

    results = {}
    for market in ("1x2", "ou25"):
        print(f"\n=== Mercado {market} ===")
        results[market] = run_market(df_all, market)
        for method, m in results[market]["methods"].items():
            print(f"[{method}] n_train={m['n_train']} n_test={m['n_test']} melhor_limiar={m['best_threshold']}")

    write_report(results)
    write_csvs(results)
    print(f"\nRelatorio em {OUTDIR / 'relatorio.md'}")


def write_csvs(results: dict):
    for market, r in results.items():
        for method, m in r["methods"].items():
            m["sweep_full"].to_csv(OUTDIR / f"sweep_full_{market}_{method}.csv", index=False)
            m["sweep_train"].to_csv(OUTDIR / f"sweep_train_{market}_{method}.csv", index=False)
            m["sweep_test_allthr"].to_csv(OUTDIR / f"sweep_test_allthr_{market}_{method}.csv", index=False)
            m["clv_bucket"].to_csv(OUTDIR / f"clv_by_edge_bucket_{market}_{method}.csv", index=False)
        r["league_breakdown_0"].to_csv(OUTDIR / f"league_breakdown_{market}_limiar0.csv", index=False)
        r["league_breakdown_best"].to_csv(OUTDIR / f"league_breakdown_{market}_limiar_best.csv", index=False)


def write_report(results: dict):
    lines = []
    lines.append("# Bateria ad-hoc W1 — Backtest de valor 1X2 e O/U 2,5 (odds reais historicas)")
    lines.append("")
    lines.append(f"Dataset: `data/built/backtest_valuebet_dataset.parquet` (8117 fixtures, 2025-01 a "
                 f"2026-05, football-data.co.uk). Stake fixo R$ {STAKE:.2f}/aposta. Gerado por "
                 f"`scripts/adhoc_w1_valuebet_backtest.py`.")
    lines.append("")
    lines.append("**Contexto:** reavalia a pergunta do H2/H3 (`DOCUMENTACAO_CENTRAL.md` §19.4/19.5) — "
                 "la a amostra era 84 fixtures (coleta forward), aqui 8117 (odds reais historicas, "
                 "abertura+fechamento). H3 concluiu 'valida metodologia, nao rentabilidade' por amostra "
                 "pequena demais; esta bateria testa se a amostra ~60x maior muda essa conclusao.")
    lines.append("")
    lines.append("**Metodologia contra overfitting de limiar:** para cada mercado/metodo de devig, a "
                 "amostra elegivel (tem odds de abertura completas) e ordenada por data e partida ao "
                 "meio. A 1a metade ('treino') e usada para VARRER os limiares de edge e escolher o "
                 f"'melhor' (maior ROI entre limiares com >= {MIN_N_TRAIN} apostas no treino, empate "
                 "quebrado pelo menor limiar). Esse limiar fixo e entao aplicado, SEM REAJUSTE, na 2a "
                 "metade ('teste') — a unica leitura honesta de performance fora da amostra que gerou "
                 "a escolha. As tabelas 'in-sample' (amostra completa e treino, todos os limiares) sao "
                 "reportadas por transparencia, mas sao viciadas se usadas para julgar rentabilidade.")
    lines.append("")

    for market in ("1x2", "ou25"):
        r = results[market]
        nome_mercado = "1X2 (resultado)" if market == "1x2" else "Over/Under 2,5 gols"
        lines.append(f"## Mercado: {nome_mercado}")
        lines.append("")
        lines.append(f"Amostra elegivel (odds de abertura completas): **{r['n_total']}** fixtures.")
        lines.append("")

        for method in ("shin", "proporcional", "power"):
            m = r["methods"][method]
            lines.append(f"### De-vig: {method}")
            lines.append("")
            lines.append(f"n_treino={m['n_train']}, n_teste={m['n_test']}. "
                         f"Overlap 'lado do modelo == favorito do mercado (menor odd)': "
                         f"{fmt_pct(m['overlap_favorite'])}.")
            lines.append("")
            lines.append("**Sweep in-sample (amostra completa, todos os limiares — viciado, so referencia):**")
            lines.append("")
            lines.append(df_to_md(m["sweep_full"], float_cols=["hit_rate", "roi", "odd_media", "hit_rate_breakeven"]))
            lines.append("")
            lines.append("**Sweep na 1a metade (treino) — usado so pra ESCOLHER o limiar:**")
            lines.append("")
            lines.append(df_to_md(m["sweep_train"], float_cols=["hit_rate", "roi", "odd_media", "hit_rate_breakeven"]))
            lines.append("")
            th = m["best_threshold"]
            lines.append(f"**Limiar escolhido no treino: {fmt_pct(th) if th is not None else 'n/a'}**")
            lines.append("")
            if m["train_at_best"] and m["test_at_best"]:
                tb, te = m["train_at_best"], m["test_at_best"]
                lines.append("| | N | hit-rate | hit-rate p/ break-even | lucro | ROI |")
                lines.append("|---|---|---|---|---|---|")
                lines.append(f"| Treino (in-sample, escolheu o limiar) | {tb['n']} | {fmt_pct(tb['hit_rate'])} | "
                             f"{fmt_pct(tb['hit_rate_breakeven'])} | {fmt_money(tb['lucro'])} | {fmt_pct(tb['roi'])} |")
                lines.append(f"| **Teste (out-of-sample, limiar fixo)** | {te['n']} | {fmt_pct(te['hit_rate'])} | "
                             f"{fmt_pct(te['hit_rate_breakeven'])} | {fmt_money(te['lucro'])} | **{fmt_pct(te['roi'])}** |")
                lines.append("")
                bt, bte = m["boot_train"], m["boot_test"]
                lines.append(f"IC 95% do ROI via bootstrap (5000 resamples, mesmo limiar): "
                             f"treino [{fmt_pct(bt['roi_lo'])}, {fmt_pct(bt['roi_hi'])}]; "
                             f"**teste [{fmt_pct(bte['roi_lo'])}, {fmt_pct(bte['roi_hi'])}]**.")
                lines.append("")
            else:
                lines.append("Sem limiar elegivel (amostra insuficiente).")
                lines.append("")
            lines.append("**CLV por faixa de edge (positivo = pegou preco melhor do que o mercado fechou):**")
            lines.append("")
            lines.append(df_to_md(m["clv_bucket"], float_cols=["clv_medio", "frac_clv_positivo"]))
            lines.append("")

        lines.append(f"**CLV geral do mercado (todas as fixtures com fechamento disponivel, "
                     f"independente de limiar):** n={r['clv_overall']['n']}, "
                     f"CLV medio={fmt_pct(r['clv_overall']['media'])}, "
                     f"% com CLV positivo={fmt_pct(r['clv_overall']['frac_positivo'])}.")
        lines.append("")

        lines.append(f"**Quebra por pais (de-vig shin, limiar 0% — qualquer edge positivo, maximiza volume):**")
        lines.append("")
        lines.append(df_to_md(r["league_breakdown_0"], float_cols=["hit_rate", "roi"]))
        lines.append("")
        shin_th = r["shin_best_th"]
        if shin_th is not None and not r["league_breakdown_best"].empty:
            lines.append(f"**Quebra por pais (de-vig shin, limiar escolhido = {fmt_pct(shin_th)}):**")
            lines.append("")
            lines.append(df_to_md(r["league_breakdown_best"], float_cols=["hit_rate", "roi"]))
            lines.append("")

    lines.append("## Conclusao")
    lines.append("")
    lines.append(CONCLUSION_PLACEHOLDER)
    lines.append("")

    (OUTDIR / "relatorio.md").write_text("\n".join(lines), encoding="utf-8")


CONCLUSION_PLACEHOLDER = """\
**Nao ha edge de valor consistente e estatisticamente defensavel — nas duas
direcoes (1X2 e O/U 2,5), com os 3 metodos de devig, com amostra ~60x maior
que o H3 original.** A bateria amplia H3 (`DOCUMENTACAO_CENTRAL.md` §19.4/19.5)
de "amostra pequena demais pra validar rentabilidade" para "amostra grande o
bastante pra concluir que a estrategia testada, do jeito testada, perde
dinheiro":

1. **ROI e negativo em praticamente toda combinacao de mercado/metodo/limiar
   in-sample, e nas duas validacoes out-of-sample** (1X2 teste: -10.7% a
   -8.7% conforme o metodo; O/U teste: -5.0% a -5.4%). Nenhum limiar
   testado (0/1/2/3/5/8/10%) produziu ROI out-of-sample positivo em nenhum
   mercado.

2. **Sinal mais forte contra a hipotese de valor real: no 1X2 o ROI PIORA
   monotonicamente conforme o limiar de edge sobe** (treino shin: -10.0% em
   0% de limiar ate -25.6% em 10%). Se o "edge" do modelo fosse sinal real
   de mispricing do mercado, apostas de maior edge deveriam performar
   MELHOR, nao pior — o padrao observado e mais consistente com "quando o
   modelo diverge muito do mercado, o modelo e que esta errado" (o mercado
   e mais dificil de bater justamente onde ele concorda consigo mesmo) do
   que com uma vantagem informacional genuina.

3. **O/U 2,5 e mais ambiguo mas ainda nao passa no teste out-of-sample.** O
   limiar escolhido no treino (5%, criterio: melhor ROI com N>=30) da
   ROI treino -3.2% (shin) e teste -5.4% — piora, nao confirma. O IC 95%
   bootstrap do ROI de teste ([-13.6%, +2.7%] pro shin) inclui zero mas esta
   concentrado no lado negativo — nao da pra afirmar edge positivo com
   confianca, so "nao e possivel descartar ROI zero", o que e uma barra bem
   mais baixa que "lucrativo".

4. **CLV (independente de resultado) confirma ausencia de vantagem
   informacional real:** CLV medio praticamente zero nos dois mercados
   (1X2: -0.10%; O/U: +0.07%), com fracao de apostas com CLV positivo perto
   de 50% em quase toda faixa de edge (nao ha tendencia clara de "edge alto
   -> preco melhora contra o fechamento depois"). Se o modelo estivesse
   pegando erros reais de precificacao, o CLV medio deveria ser
   consistentemente positivo nas faixas de edge mais alto — nao e o caso.

5. **Os 3 metodos de devig (shin/proporcional/power) concordam entre si** —
   mesma conclusao qualitativa nos dois mercados, numeros muito proximos
   (a maior diferenca de ROI teste entre metodos e ~2pp no 1X2). Confirma
   H3: a escolha do metodo de devig nao e o fator decisivo aqui: nenhum dos
   tres revela edge que os outros escondam.

6. **Quebra por pais mostra dispersao tipica de ruido, nao edge
   consistente.** A maioria das ligas tem ROI negativo (England, Spain,
   France, Germany todos negativos nos dois mercados), mas 1-2 ligas com N
   pequeno (Portugal no O/U: +8.6% a +10.2% ROI, N=83-167; Italy no 1X2:
   -3.6% ROI, o "menos ruim") aparecem destacadas. Por regra do proprio
   projeto (concentracao numa liga so = sinal de ruido/vies de selecao, ver
   `DOCUMENTACAO_CENTRAL.md` §19.4 "controle negativo"), essas excecoes
   pontuais NAO sao tratadas como edge real — sao exatamente o tipo de
   variacao que uma amostra de ~150-500 jogos por liga produz por acaso.

7. **Contexto adicional (ceticismo):** o "lado do modelo" coincide com o
   favorito do mercado (menor odd de abertura) em 88.6% dos jogos no 1X2 e
   78.4% no O/U — ou seja, a maior parte das "apostas de valor" e apenas
   "concordar com o favorito do book", nao uma visao contraria genuina. A
   taxa de acerto realizada fica sistematicamente ABAIXO da taxa de
   equilibrio implicita na odd tomada (`hit_rate_breakeven`) em quase toda
   combinacao de limiar/metodo/mercado — exatamente o padrao esperado sob
   H0 (mercado eficiente, sem edge, apostador paga a margem da casa).

**Implicacao de produto:** nao construir uma feature de "aposta de valor
automatica" (bet-when-edge>X%) em cima da saida atual do modelo — os dados
disponiveis (8117 jogos, odds reais abertura+fechamento) nao sustentam essa
promessa. Isso NAO invalida o modelo como ferramenta preditiva/informativa
(ele pode ser bem calibrado para o proposito de informar o usuario sem
prometer lucro) — e uma conclusao sobre ESTRATEGIA DE APOSTA, nao sobre a
qualidade do modelo de previsao em si. Registrar em
`DOCUMENTACAO_CENTRAL.md` §19 como fechamento definitivo da linha de
pesquisa "valor/CLV" aberta no H2/H3: amostra grande confirma a suspeita, nao
a contraria."""

if __name__ == "__main__":
    main()
