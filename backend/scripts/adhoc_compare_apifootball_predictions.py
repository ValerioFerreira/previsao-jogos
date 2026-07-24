#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_compare_apifootball_predictions.py
==================================================
Compara em escala o nosso modelo (Dixon-Coles NB, `predictor.py`) contra o
endpoint nativo `/predictions` da api-football, no mesmo conjunto de jogos
(`data/built/backtest_predictions.parquet`, 8117 fixtures out-of-sample já
finalizados, 2025-01-11 a 2026-05-31, coletado por
`scripts/fetch_predictions_baseline.py`).

Segue o padrão de `scripts/adhoc_metrics_hitrates.py` (mesmas métricas de
`research_clubs/protocol.py`).

MERCADO COMPARÁVEL COM PROBABILIDADE (log-loss/Brier/ECE/acurácia):
  - 1X2: nosso `vencedor.probabilidades[home_team/Empate/away_team]` vs
    `predictions.percent.{home,draw,away}` do vendor.

MERCADO SÓ COM SUGESTÃO DIRECIONAL (sem probabilidade real do vendor):
  - O/U total de gols: nosso `over_2_5.resposta` (linha FIXA 2.5) vs
    `predictions.under_over` do vendor (string tipo "+1.5"/"-2.5" — SINAL +
    LINHA PRÓPRIA, quase sempre null; quando presente, a linha nem sempre é
    2.5). Reportado à parte, como acerto direcional na própria linha de cada
    um — NÃO é comparação de probabilidade calibrada.

NÃO COMPARÁVEL (vendor não expõe probabilidade nem contagem esperada real):
  - BTTS: vendor não tem campo equivalente (só ratings `comparison.*`/
    `teams.{home,away}.league.goals.for/against`, que são estatísticas
    descritivas de forma, não uma probabilidade calibrada do confronto).
  - Dupla chance: derivável do nosso 1X2, mas o vendor só expõe
    `predictions.win_or_draw` (booleano, não probabilidade).
  - Gols esperados por time (`gols_equipe`): vendor não expõe um valor
    esperado real, só ratings de forma (`comparison.goals`).
  - Placar exato: vendor não expõe.

Uso: python scripts/adhoc_compare_apifootball_predictions.py
Saída: data/reports/adhoc_compare_apifootball/*.csv + RELATORIO_FINAL.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from research_clubs.protocol import (  # noqa: E402
    multiclass_logloss, brier_multiclass, ece_multiclass, accuracy,
)

PREDICTIONS_PARQUET = ROOT / "data" / "built" / "backtest_predictions.parquet"
VENDOR_DIR = ROOT / "data" / "raw" / "predictions_baseline"
OUT_DIR = ROOT / "data" / "reports" / "adhoc_compare_apifootball"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_LEAGUES = ["Brasileirao Serie A", "Premier League", "La Liga", "Serie A Italia"]
RESULT_IDX = {"H": 0, "D": 1, "A": 2}


# ─────────────────────────────────────────────────────────────────────────
# Extração
# ─────────────────────────────────────────────────────────────────────────
def _our_probs(row) -> tuple[float, float, float] | None:
    try:
        j = json.loads(row["prediction_json"])
    except (TypeError, ValueError):
        return None
    prob = (j.get("vencedor") or {}).get("probabilidades") or {}
    ph = prob.get(row["home_team"])
    pd_ = prob.get("Empate")
    pa = prob.get(row["away_team"])
    if ph is None or pd_ is None or pa is None:
        return None
    return float(ph) / 100.0, float(pd_) / 100.0, float(pa) / 100.0


def _our_over25(row) -> bool | None:
    try:
        j = json.loads(row["prediction_json"])
    except (TypeError, ValueError):
        return None
    resp = (j.get("over_2_5") or {}).get("resposta")
    if resp is None:
        return None
    return "Mais" in resp


def _pct(x) -> float | None:
    if x is None:
        return None
    try:
        return float(str(x).replace("%", "").strip()) / 100.0
    except ValueError:
        return None


def _load_vendor() -> pd.DataFrame:
    rows = []
    for f in VENDOR_DIR.glob("*.json"):
        try:
            fid = int(f.stem)
        except ValueError:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        pred = d.get("predictions") or {}
        percent = pred.get("percent") or {}
        ph, pdw, pa = _pct(percent.get("home")), _pct(percent.get("draw")), _pct(percent.get("away"))
        uo = pred.get("under_over")
        rows.append({"fixture_id": fid, "v_p_home": ph, "v_p_draw": pdw, "v_p_away": pa,
                     "v_under_over": uo})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────
# Métricas
# ─────────────────────────────────────────────────────────────────────────
def _metrics_1x2(y_idx: np.ndarray, P: np.ndarray) -> dict:
    P = P / P.sum(axis=1, keepdims=True)
    return {
        "n": int(len(y_idx)),
        "log_loss": round(multiclass_logloss(y_idx, P), 4),
        "brier": round(brier_multiclass(y_idx, P), 4),
        "ece": round(ece_multiclass(y_idx, P) * 100, 2),
        "acuracia": round(accuracy(y_idx, P) * 100, 1),
    }


def main() -> None:
    pred = pd.read_parquet(PREDICTIONS_PARQUET)
    pred["fixture_id"] = pred["fixture_id"].astype(int)

    vendor = _load_vendor()
    print(f"[compare] {len(pred)} fixtures no backtest do nosso modelo, "
          f"{len(vendor)} respostas cruas do vendor salvas em disco")

    # nosso 1X2
    our_probs = pred.apply(_our_probs, axis=1)
    pred["our_p_home"] = our_probs.map(lambda t: t[0] if t else None)
    pred["our_p_draw"] = our_probs.map(lambda t: t[1] if t else None)
    pred["our_p_away"] = our_probs.map(lambda t: t[2] if t else None)
    pred["our_over25"] = pred.apply(_our_over25, axis=1)

    pred["actual_result"] = np.select(
        [pred["home_score"] > pred["away_score"], pred["home_score"] < pred["away_score"]],
        ["H", "A"], default="D")
    pred["actual_total_goals"] = pred["home_score"] + pred["away_score"]

    df = pred.merge(vendor, on="fixture_id", how="left")

    n_total = len(df)
    n_our_usable = df[["our_p_home", "our_p_draw", "our_p_away"]].notna().all(axis=1).sum()
    n_vendor_saved = df["v_p_home"].notna().sum() + 0  # placeholder, recompute below
    vendor_usable_mask = df[["v_p_home", "v_p_draw", "v_p_away"]].notna().all(axis=1) & \
        ((df["v_p_home"] + df["v_p_draw"] + df["v_p_away"]) > 0)
    n_vendor_usable = int(vendor_usable_mask.sum())
    n_vendor_raw_files = int(df["v_under_over"].notna().sum() + vendor_usable_mask.sum())  # rough, informational

    both_mask = df[["our_p_home", "our_p_draw", "our_p_away"]].notna().all(axis=1) & vendor_usable_mask
    n_intersection = int(both_mask.sum())

    print(f"[compare] N total={n_total} | nosso usável={n_our_usable} | "
          f"vendor usável (percent completo)={n_vendor_usable} | interseção usável (1X2)={n_intersection}")

    sub = df[both_mask].copy()
    y_idx = sub["actual_result"].map(RESULT_IDX).to_numpy()

    P_our = sub[["our_p_home", "our_p_draw", "our_p_away"]].to_numpy(dtype=float)
    P_vendor = sub[["v_p_home", "v_p_draw", "v_p_away"]].to_numpy(dtype=float)

    # ---- (b) agregado das competições presentes no backtest ----
    m_our_all = _metrics_1x2(y_idx, P_our)
    m_vendor_all = _metrics_1x2(y_idx, P_vendor)
    summary_all = pd.DataFrame([
        {"lado": "nosso_modelo", **m_our_all},
        {"lado": "api_football_predictions", **m_vendor_all},
    ])
    summary_all.to_csv(OUT_DIR / "summary_all_28.csv", index=False)

    # ---- (a) 4 ligas-alvo ----
    tgt_mask = sub["tournament"].isin(TARGET_LEAGUES)
    sub_tgt = sub[tgt_mask]
    y_tgt = sub_tgt["actual_result"].map(RESULT_IDX).to_numpy()
    P_our_tgt = sub_tgt[["our_p_home", "our_p_draw", "our_p_away"]].to_numpy(dtype=float)
    P_vendor_tgt = sub_tgt[["v_p_home", "v_p_draw", "v_p_away"]].to_numpy(dtype=float)
    if len(sub_tgt) >= 10:
        m_our_tgt = _metrics_1x2(y_tgt, P_our_tgt)
        m_vendor_tgt = _metrics_1x2(y_tgt, P_vendor_tgt)
    else:
        m_our_tgt = {"n": len(sub_tgt)}
        m_vendor_tgt = {"n": len(sub_tgt)}
    summary_tgt = pd.DataFrame([
        {"lado": "nosso_modelo", **m_our_tgt},
        {"lado": "api_football_predictions", **m_vendor_tgt},
    ])
    summary_tgt.to_csv(OUT_DIR / "summary_target_leagues.csv", index=False)

    # ---- (c) por competição individual ----
    league_rows = []
    for lg, g in sub.groupby("tournament"):
        if len(g) < 10:
            continue
        yl = g["actual_result"].map(RESULT_IDX).to_numpy()
        Pol = g[["our_p_home", "our_p_draw", "our_p_away"]].to_numpy(dtype=float)
        Pvl = g[["v_p_home", "v_p_draw", "v_p_away"]].to_numpy(dtype=float)
        mo = _metrics_1x2(yl, Pol)
        mv = _metrics_1x2(yl, Pvl)
        league_rows.append({
            "tournament": lg, "n": len(g), "is_target": lg in TARGET_LEAGUES,
            "our_log_loss": mo["log_loss"], "our_brier": mo["brier"], "our_ece": mo["ece"], "our_acuracia": mo["acuracia"],
            "vendor_log_loss": mv["log_loss"], "vendor_brier": mv["brier"], "vendor_ece": mv["ece"], "vendor_acuracia": mv["acuracia"],
            "vencedor_logloss": "nosso" if mo["log_loss"] < mv["log_loss"] else "vendor",
        })
    league_df = pd.DataFrame(league_rows).sort_values("n", ascending=False)
    league_df.to_csv(OUT_DIR / "league_breakdown_1x2.csv", index=False)

    n_leagues_our_wins = int((league_df["vencedor_logloss"] == "nosso").sum())
    n_leagues_vendor_wins = int((league_df["vencedor_logloss"] == "vendor").sum())

    # ---- O/U 2.5 direcional (bloco separado, linhas potencialmente diferentes) ----
    ou_mask = df["our_over25"].notna() & df["v_under_over"].notna()
    ou_sub = df[ou_mask].copy()

    def _vendor_uo_dir_line(v):
        s = str(v)
        try:
            line = abs(float(s))
        except ValueError:
            return None, None
        direction_over = s.strip().startswith("+")
        return direction_over, line

    dirs_lines = ou_sub["v_under_over"].map(_vendor_uo_dir_line)
    ou_sub["vendor_dir_over"] = dirs_lines.map(lambda t: t[0])
    ou_sub["vendor_line"] = dirs_lines.map(lambda t: t[1])
    ou_sub = ou_sub[ou_sub["vendor_dir_over"].notna()]

    ou_sub["vendor_hit"] = (ou_sub["actual_total_goals"] > ou_sub["vendor_line"]) == ou_sub["vendor_dir_over"]
    ou_sub["our_hit_line25"] = (ou_sub["actual_total_goals"] > 2.5) == ou_sub["our_over25"]

    n_ou = len(ou_sub)
    n_ou_same_line = int((ou_sub["vendor_line"] == 2.5).sum())
    ou_report = pd.DataFrame([
        {"conjunto": "todos_com_under_over_do_vendor (linhas mistas)", "n": n_ou,
         "vendor_acerto_pct": round(100 * ou_sub["vendor_hit"].mean(), 1) if n_ou else None,
         "nosso_acerto_pct_linha_2.5": round(100 * ou_sub["our_hit_line25"].mean(), 1) if n_ou else None},
        {"conjunto": "so_linha_2.5_do_vendor (comparação estrita mesma linha)", "n": n_ou_same_line,
         "vendor_acerto_pct": round(100 * ou_sub.loc[ou_sub["vendor_line"] == 2.5, "vendor_hit"].mean(), 1) if n_ou_same_line else None,
         "nosso_acerto_pct_linha_2.5": round(100 * ou_sub.loc[ou_sub["vendor_line"] == 2.5, "our_hit_line25"].mean(), 1) if n_ou_same_line else None},
    ])
    ou_report.to_csv(OUT_DIR / "ou25_directional_hitrate.csv", index=False)

    # ---- Relatório final ----
    lines = []
    lines.append("# Comparação: nosso modelo (Dixon-Coles NB) vs `/predictions` da API-Football em escala")
    lines.append("")
    lines.append(f"Data: 2026-07-23. Fonte: `data/built/backtest_predictions.parquet` "
                 f"({n_total} fixtures, 2025-01-11 a 2026-05-31, {pred['tournament'].nunique()} competições) "
                 f"casada com `data/raw/predictions_baseline/*.json` "
                 f"(coletado por `scripts/fetch_predictions_baseline.py`).")
    lines.append("")
    lines.append(f"- Fixtures no backtest (nosso modelo): **{n_total}**")
    lines.append(f"- Respostas cruas do vendor salvas em disco: **{len(vendor)}**")
    lines.append(f"- Nosso modelo com 1X2 utilizável: **{n_our_usable}**")
    lines.append(f"- Vendor com `percent.{{home,draw,away}}` completo e utilizável: **{n_vendor_usable}**")
    lines.append(f"- Interseção usada nas métricas de 1X2 (ambos os lados utilizáveis): **{n_intersection}**")
    lines.append("")
    lines.append("## Mercado 1X2 (único mercado com probabilidade calibrada dos dois lados)")
    lines.append("")
    lines.append("### Agregado — todas as competições do backtest")
    lines.append("")
    lines.append("| lado | N | log_loss | brier | ece | acuracia |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in summary_all.iterrows():
        lines.append(f"| {r['lado']} | {r['n']} | {r['log_loss']} | {r['brier']} | {r['ece']}% | {r['acuracia']}% |")
    winner_all = "nosso_modelo" if m_our_all["log_loss"] < m_vendor_all["log_loss"] else "api_football_predictions"
    lines.append("")
    lines.append(f"**Vencedor (log-loss, agregado): {winner_all}**")
    lines.append("")
    lines.append("### 4 ligas-alvo (Brasileirão, Premier League, La Liga, Serie A Itália)")
    lines.append("")
    lines.append("| lado | N | log_loss | brier | ece | acuracia |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in summary_tgt.iterrows():
        if "log_loss" in r and pd.notna(r.get("log_loss")):
            lines.append(f"| {r['lado']} | {r['n']} | {r['log_loss']} | {r['brier']} | {r['ece']}% | {r['acuracia']}% |")
        else:
            lines.append(f"| {r['lado']} | {r['n']} | (amostra insuficiente) | | | |")
    if pd.notna(m_our_tgt.get("log_loss")) and pd.notna(m_vendor_tgt.get("log_loss")):
        winner_tgt = "nosso_modelo" if m_our_tgt["log_loss"] < m_vendor_tgt["log_loss"] else "api_football_predictions"
        lines.append("")
        lines.append(f"**Vencedor (log-loss, 4 ligas-alvo): {winner_tgt}**")
    lines.append("")
    lines.append(f"### Por competição individual (n≥10) — {len(league_df)} competições comparadas")
    lines.append("")
    lines.append(f"Nosso modelo ganhou em log-loss em **{n_leagues_our_wins}/{len(league_df)}** competições; "
                 f"o vendor ganhou em **{n_leagues_vendor_wins}/{len(league_df)}**.")
    lines.append("")
    lines.append("| competição | n | nosso_logloss | vendor_logloss | nosso_acc | vendor_acc | vencedor |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in league_df.iterrows():
        tag = " (alvo)" if r["is_target"] else ""
        lines.append(f"| {r['tournament']}{tag} | {r['n']} | {r['our_log_loss']} | {r['vendor_log_loss']} | "
                     f"{r['our_acuracia']}% | {r['vendor_acuracia']}% | {r['vencedor_logloss']} |")
    lines.append("")
    lines.append("## Mercado O/U total de gols — SOMENTE acerto direcional (não é probabilidade)")
    lines.append("")
    lines.append("O vendor não expõe uma probabilidade calibrada de over/under — só "
                 "`predictions.under_over`, uma sugestão binária com sinal (+/-) e uma linha PRÓPRIA "
                 "(nem sempre 2.5), presente em **apenas uma minoria** das respostas (a maioria vem "
                 "`null`). Comparação honesta: acerto direcional na própria linha de cada lado, e "
                 "também restrito só aos casos em que a linha do vendor coincide com 2.5 (nossa linha fixa).")
    lines.append("")
    lines.append("| conjunto | n | vendor_acerto% | nosso_acerto%(linha 2.5) |")
    lines.append("|---|---|---|---|")
    for _, r in ou_report.iterrows():
        lines.append(f"| {r['conjunto']} | {r['n']} | {r['vendor_acerto_pct']} | {r['nosso_acerto_pct_linha_2.5']} |")
    lines.append("")
    lines.append("## Mercados NÃO comparáveis (vendor não expõe probabilidade/contagem esperada equivalente)")
    lines.append("")
    lines.append("- **Ambas Marcam (BTTS)**: sem campo de probabilidade no vendor.")
    lines.append("- **Dupla chance**: vendor só tem `win_or_draw` booleano, não probabilidade.")
    lines.append("- **Gols esperados por time**: vendor só tem ratings de forma (`comparison.goals`), "
                 "não um valor esperado real calibrado pro confronto.")
    lines.append("- **Placar exato**: vendor não expõe.")
    lines.append("")
    lines.append("Estes mercados NÃO entram na comparação — não foi fabricada nenhuma métrica onde não "
                 "há dado comparável do lado do vendor.")
    lines.append("")
    lines.append("## Conclusão")
    lines.append("")
    if winner_all == "nosso_modelo":
        lines.append(f"O nosso modelo (Dixon-Coles NB) supera o `/predictions` da API-Football em log-loss "
                     f"1X2 no agregado ({m_our_all['log_loss']} vs {m_vendor_all['log_loss']}, "
                     f"N={n_intersection}), confirmando o piloto (n=40, log-loss vendor 2.0953, pior que o "
                     f"palpite uniforme ln(3)≈1.0986).")
    else:
        lines.append(f"**DIVERGÊNCIA DO PILOTO**: nesta amostra em escala (N={n_intersection}), o vendor "
                     f"({m_vendor_all['log_loss']}) superou nosso modelo ({m_our_all['log_loss']}) em "
                     f"log-loss 1X2 agregado — resultado PENDENTE de decisão do dono, não decidido aqui.")
    lines.append("")
    lines.append(f"Decisão registrada: {'NÃO construir nenhum badge de ensemble/convergência com o vendor em produção — o vendor não bate o nosso modelo nesta amostra.' if winner_all == 'nosso_modelo' else 'achado pendente — NÃO promover nada sozinho aqui (isso ativaria o gate §6, fora do escopo desta tarefa); decisão cabe ao dono.'}")

    (OUT_DIR / "RELATORIO_FINAL.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[compare] relatório salvo em {OUT_DIR / 'RELATORIO_FINAL.md'}")
    print(f"[compare] vencedor agregado (log-loss): {winner_all}")
    print(f"[compare] nosso: {m_our_all}")
    print(f"[compare] vendor: {m_vendor_all}")


if __name__ == "__main__":
    main()
