#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_consolidate.py
==============================
Fase 9 — lê todos os CSVs de resultado produzidos pelas fases 1-8 e monta um
relatório executivo consolidado (Markdown), respondendo às duas perguntas da
diretriz original:
  1. Os modelos de seleções continuam os melhores quando treinados com clubes?
  2. O conhecimento de clubes melhora as previsões de seleções?

Não decide sozinho a exceção de push — apenas resume os números para decisão.

Uso: python scripts/clubs_consolidate.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "data" / "reports"
OUT_MD = ROOT / "docs" / "RELATORIO_FINAL_PESQUISA_CLUBES.md"


def _read(path, label):
    if not path.exists():
        return f"⚠️ {label}: não encontrado ({path.relative_to(ROOT)})\n"
    try:
        df = pd.read_csv(path)
        return df
    except Exception as e:
        return f"⚠️ {label}: erro ao ler ({e})\n"


def section_fase1():
    p = REPORTS / "clubs_battery" / "_ranking.csv"
    if not p.exists():
        return "## Fase 1 — Bateria de resultado\n⚠️ não encontrado\n"
    df = pd.read_csv(p)
    return "## Fase 1 — Bateria de resultado (ranking)\n\n" + \
        df[["modelo", "logloss", "rps", "brier", "ece", "accuracy"]].to_markdown(index=False) + "\n"


def section_fase2():
    out = ["## Fase 2 — Contagem, calibração, tuning DC\n"]
    counts_dir = REPORTS / "clubs_counts"
    if counts_dir.exists():
        out.append("### Cascata de contagem (mercados)\n")
        for f in sorted(counts_dir.glob("*.csv")):
            df = pd.read_csv(f)
            media = df[df["fold"] == "MEDIA"]
            if len(media):
                r = media.iloc[0]
                out.append(f"- **{f.stem}**: log-loss={r['logloss']:.4f} MAE={r['mae']:.3f} "
                          f"cobertura80={r['coverage80']:.3f}\n")
    tuning = REPORTS / "clubs_dc_tuning.csv"
    if tuning.exists():
        df = pd.read_csv(tuning)
        summ = df.groupby(["n_estimators", "max_depth", "learning_rate"])[
            ["logloss", "rps"]].mean().sort_values("logloss").head(5)
        out.append("\n### Tuning DC-NB — top 5 configs\n\n" + summ.to_markdown() + "\n")
        prod = df[(df.n_estimators == 100) & (df.max_depth == 3) & (df.learning_rate == 0.05)]
        if len(prod):
            out.append(f"\nProdução (100,3,0.05): log-loss médio = {prod['logloss'].mean():.4f}\n")
    return "".join(out)


def section_fase3():
    p = REPORTS / "clubs_transfer_selections.csv"
    out = ["## Fase 3 — Transferência clubes -> seleções (Linha A)\n"]
    if not p.exists():
        out.append("⚠️ não executado\n")
        return "".join(out)
    df = pd.read_csv(p)
    summ = df.groupby("mode")[["logloss", "rps", "ece"]].mean().sort_values("logloss")
    out.append(summ.to_markdown() + "\n")
    baseline_ll = summ.loc["baseline", "logloss"] if "baseline" in summ.index else None
    if baseline_ll:
        for mode in summ.index:
            if mode == "baseline":
                continue
            delta = summ.loc[mode, "logloss"] - baseline_ll
            out.append(f"\n- {mode}: delta log-loss vs produção = {delta:+.4f} "
                      f"{'(MELHOR)' if delta < 0 else '(pior)'}")
    return "".join(out) + "\n"


def section_fase4():
    d = REPORTS / "clubs_hypotheses"
    out = ["## Fase 4 — Hipóteses descartadas revisitadas\n"]
    if not d.exists():
        out.append("⚠️ não executado\n")
        return "".join(out)
    for f in sorted(d.glob("*.csv")):
        try:
            df = pd.read_csv(f)
            if "delta" in df.columns:
                delta = df.iloc[-1]["delta"] if len(df) else None
                melhora = df.iloc[-1].get("melhora") if len(df) else None
                out.append(f"- **{f.stem}**: delta={delta:+.4f} | passou_todos_folds={melhora}\n")
            else:
                out.append(f"- **{f.stem}**: {len(df)} linhas (ver CSV)\n")
        except Exception:
            pass
    return "".join(out)


def section_fase5():
    p = REPORTS / "clubs_features_v2" / "_combo_final.csv"
    out = ["## Fase 5 — Features próprias de clubes (ablação)\n"]
    gdir = REPORTS / "clubs_features_v2"
    if gdir.exists():
        for f in sorted(gdir.glob("*.csv")):
            if f.name == "_combo_final.csv":
                continue
            try:
                df = pd.read_csv(f)
                delta = df.iloc[-1]["delta"]
                out.append(f"- **{f.stem}**: delta log-loss = {delta:+.4f}\n")
            except Exception:
                pass
    if p.exists():
        df = pd.read_csv(p)
        out.append(f"\n### Combinação final dos grupos que passaram\ndelta = "
                  f"{df.iloc[-1]['delta']:+.4f}\n")
    else:
        out.append("\n(combinação final não gerada — nenhum grupo passou isoladamente ou "
                  "fase ainda rodando)\n")
    return "".join(out)


def section_fase6():
    out = ["## Fase 6 — Bateria avançada Linha B\n"]
    adv = REPORTS / "clubs_advanced"
    if adv.exists():
        for name in ["state_space", "ensemble", "deep_tabular"]:
            f = adv / f"{name}.csv"
            if f.exists():
                df = pd.read_csv(f)
                delta = df.iloc[-1]["delta"]
                wins = df.iloc[:-1]["melhora"].sum()
                out.append(f"- **{name}**: {wins}/5 folds melhoram, delta={delta:+.4f}\n")
        gap = adv / "gap_counts_shots.csv"
        if gap.exists():
            df = pd.read_csv(gap)
            out.append(f"- **gap_counts (chutes)**: log-loss médio = {df['logloss'].mean():.4f}\n")
    sweep = REPORTS / "clubs_sweep"
    if sweep.exists():
        cb = sweep / "catboost_sweep.csv"
        if cb.exists():
            df = pd.read_csv(cb)
            best = df.groupby(["depth", "iterations", "l2_leaf_reg"])["logloss"].mean().idxmin()
            best_ll = df.groupby(["depth", "iterations", "l2_leaf_reg"])["logloss"].mean().min()
            out.append(f"- **sweep CatBoost**: melhor config {best} -> log-loss={best_ll:.4f}\n")
    return "".join(out)


def section_fase8():
    p = REPORTS / "clubs_value" / "paper_backtest.csv"
    out = ["## Fase 8 — Backtest de valor\n"]
    out.append("**Odds reais de clubes: 0 registros em `odds_registry`** (só seleções/Copa "
              "do Mundo). ROI real não pôde ser validado.\n\n")
    if p.exists():
        df = pd.read_csv(p)
        total_bets = df["n_bets"].sum()
        total_pnl = df["pnl"].sum()
        out.append(f"Backtest de papel (proxy, Kelly 1/4 contra frequência histórica): "
                  f"{total_bets} apostas simuladas, yield médio "
                  f"{100*total_pnl/max(total_bets,1):+.2f}% — **não interpretar como ROI de "
                  f"mercado real**, é só diagnóstico de edge relativo.\n")
    return "".join(out)


def main():
    sections = [
        "# Relatório Final — Pesquisa de Modelos para Clubes\n",
        "\n> Gerado automaticamente por `scripts/clubs_consolidate.py`. "
        "Consolida os resultados numéricos de todas as fases executadas na branch "
        "`clubs`. Decisões de promoção (exceção de push) ficam para revisão humana.\n\n",
        section_fase1(), "\n",
        section_fase2(), "\n",
        section_fase3(), "\n",
        section_fase4(), "\n",
        section_fase5(), "\n",
        section_fase6(), "\n",
        section_fase8(), "\n",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("".join(str(s) for s in sections), encoding="utf-8")
    print(f"Relatório salvo em {OUT_MD}")
    print("\n" + "".join(str(s) for s in sections))


if __name__ == "__main__":
    main()
