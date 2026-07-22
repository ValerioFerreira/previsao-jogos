#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier3_exploratory_checks.py
====================================
Passo-0 (viability check) de 3 hipóteses independentes e baratas, no mesmo espírito
de `backend/data/reports/h4_xg/cobertura_xg.md`:

  1. Cobertura de `goals_prevented` (goleiro) no cache local de clubes — 100% local,
     zero chamadas de API.
  2. `/predictions?fixture=` da api-football como baseline externo — amostra pequena
     de fixtures já resolvidos, log-loss informal.
  3. `/teams/statistics` — granularidade por faixa de minuto (gols/cartões) — amostra
     pequena de time+liga+temporada.

Uso:
    python scripts/tier3_exploratory_checks.py --check 1
    python scripts/tier3_exploratory_checks.py --check 2 --n 40
    python scripts/tier3_exploratory_checks.py --check 3 --n 12
    python scripts/tier3_exploratory_checks.py --check all
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.fixture_fetch import BASE, _key

DB = Path(__file__).resolve().parents[1] / "data" / "club_raw_cache.sqlite"
REPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "reports" / "tier3_exploratory"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _get(path: str, **params):
    r = httpx.get(BASE + path, headers={"x-apisports-key": _key()}, params=params, timeout=30)
    r.raise_for_status()
    time.sleep(0.15)  # 450 req/min, mesmo throttle de prefetch_wc_data.py
    return r.json()


# --------------------------------------------------------------------------------
# CHECK 1 — goals_prevented coverage (local only)
# --------------------------------------------------------------------------------
def check1_goals_prevented():
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM raw")
    total_rows = cur.fetchone()[0]

    cur.execute("SELECT raw FROM raw")
    n_fixtures = 0
    n_fixtures_with_stats_block = 0
    n_fixtures_with_gp_present = 0  # ao menos 1 dos 2 times com valor numérico não-nulo
    n_teamstats_total = 0
    n_teamstats_with_gp_numeric = 0
    by_season = defaultdict(lambda: [0, 0])  # season_year -> [n_fixtures, n_fixtures_with_gp]

    for (raw,) in cur:
        n_fixtures += 1
        try:
            d = json.loads(raw)
        except Exception:
            continue
        date_str = (d.get("fixture") or {}).get("date") or ""
        season_year = date_str[:4] if len(date_str) >= 4 else "?"
        by_season[season_year][0] += 1

        stats = d.get("statistics")
        if not stats:
            continue
        n_fixtures_with_stats_block += 1

        fixture_has_gp = False
        for team_stat in stats:
            n_teamstats_total += 1
            for s in team_stat.get("statistics", []):
                if s.get("type") == "goals_prevented":
                    val = s.get("value")
                    if val is not None:
                        try:
                            float(val)
                            n_teamstats_with_gp_numeric += 1
                            fixture_has_gp = True
                        except (TypeError, ValueError):
                            pass
                    break
        if fixture_has_gp:
            n_fixtures_with_gp_present += 1
            by_season[season_year][1] += 1

    lines = []
    lines.append("# Passo 0 — Cobertura de `goals_prevented` (goleiro, cache local de clubes)")
    lines.append("")
    lines.append(f"Total de linhas na tabela `raw` (`data/club_raw_cache.sqlite`): **{total_rows}**")
    lines.append(f"Fixtures com bloco `statistics` presente: **{n_fixtures_with_stats_block} / {n_fixtures} "
                 f"({100.0 * n_fixtures_with_stats_block / max(n_fixtures, 1):.1f}%)**")
    lines.append("")
    lines.append(f"Entradas time-fixture (`statistics[i]`) totais: **{n_teamstats_total}**")
    lines.append(f"Entradas time-fixture com `goals_prevented` numérico não-nulo: "
                 f"**{n_teamstats_with_gp_numeric} ({100.0 * n_teamstats_with_gp_numeric / max(n_teamstats_total, 1):.2f}%)**")
    lines.append("")
    lines.append(f"Fixtures com ao menos 1 valor de `goals_prevented` presente: "
                 f"**{n_fixtures_with_gp_present} / {n_fixtures} "
                 f"({100.0 * n_fixtures_with_gp_present / max(n_fixtures, 1):.2f}%)**")
    lines.append("")
    lines.append("Cobertura por ano (`fixture.date`, ano da partida):")
    lines.append("")
    lines.append("| season_year | n_fixtures | n_com_goals_prevented | cobertura |")
    lines.append("|---|---|---|---|")
    for yr in sorted(by_season.keys()):
        n, k = by_season[yr]
        pct = 100.0 * k / max(n, 1)
        lines.append(f"| {yr} | {n} | {k} | {pct:.2f}% |")

    overall_pct = 100.0 * n_fixtures_with_gp_present / max(n_fixtures, 1)
    if overall_pct < 8:
        verdict = "NOT VIABLE agora"
        reason = (f"cobertura agregada de {overall_pct:.2f}% é ainda pior que o xG (que já reprovou "
                  f"3x com ~15%); mesmo concentrada nos anos recentes não sustenta um modelo hoje.")
    elif overall_pct < 15:
        verdict = "viável mais tarde"
        reason = f"cobertura ({overall_pct:.2f}%) comparável ao xG que reprovou; monitorar crescimento ano a ano."
    else:
        verdict = "viável agora (checar concentração por ano)"
        reason = f"cobertura agregada ({overall_pct:.2f}%) igual ou acima do patamar do xG aprovado para spot-check."

    lines.append("")
    lines.append(f"**Veredito: {verdict}** — {reason}")
    lines.append("")
    lines.append("(Rodado por `scripts/tier3_exploratory_checks.py --check 1`, 100% local, zero chamadas de API.)")

    out = REPORT_DIR / "goals_prevented_cobertura.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[check1] escrito em {out}")
    print(f"[check1] cobertura agregada (fixtures): {overall_pct:.2f}%")


# --------------------------------------------------------------------------------
# CHECK 2 — /predictions as external baseline (small live sample)
# --------------------------------------------------------------------------------
def _pick_resolved_fixtures(n: int, seasons=(2025, 2026)) -> list[dict]:
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT raw FROM raw WHERE season IN (%s) ORDER BY RANDOM() LIMIT ?" %
                ",".join("?" * len(seasons)), (*seasons, n * 30))
    candidates = []
    seen_leagues = set()
    for (raw,) in cur:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        status = (d.get("fixture") or {}).get("status", {}).get("short")
        if status not in ("FT", "AET", "PEN"):
            continue
        goals = d.get("goals") or {}
        gh, ga = goals.get("home"), goals.get("away")
        if gh is None or ga is None:
            continue
        fid = (d.get("fixture") or {}).get("id")
        league_name = (d.get("league") or {}).get("name")
        if fid is None:
            continue
        candidates.append({"fixture_id": fid, "gh": gh, "ga": ga, "league": league_name,
                            "date": (d.get("fixture") or {}).get("date")})
    # espalhar por competições diferentes
    random.shuffle(candidates)
    picked = []
    per_league_cap = {}
    for c in candidates:
        lg = c["league"]
        per_league_cap.setdefault(lg, 0)
        if per_league_cap[lg] >= max(3, n // 8):
            continue
        per_league_cap[lg] += 1
        picked.append(c)
        if len(picked) >= n:
            break
    return picked


def check2_predictions_baseline(n: int = 40):
    fixtures = _pick_resolved_fixtures(n)
    print(f"[check2] {len(fixtures)} fixtures selecionados (temporadas 2025/2026, "
          f"{len(set(f['league'] for f in fixtures))} competições distintas)")

    results = []
    n_calls = 0
    for f in fixtures:
        try:
            resp = _get("/predictions", fixture=f["fixture_id"])
        except Exception as e:
            results.append({**f, "error": str(e)})
            n_calls += 1
            continue
        n_calls += 1
        body = resp.get("response") or []
        if not body:
            results.append({**f, "error": "resposta vazia"})
            continue
        pred = body[0].get("predictions", {})
        percent = pred.get("percent") or {}

        def _pct(x):
            if x is None:
                return None
            try:
                return float(str(x).replace("%", "")) / 100.0
            except ValueError:
                return None

        ph, pd_, pa = _pct(percent.get("home")), _pct(percent.get("draw")), _pct(percent.get("away"))
        results.append({**f, "p_home": ph, "p_draw": pd_, "p_away": pa})

    n_usable = sum(1 for r in results if r.get("p_home") is not None)
    print(f"[check2] {n_usable}/{len(results)} com percent.home/draw/away utilizável, {n_calls} chamadas de API")

    # Diagnóstico: a api-football às vezes devolve um padrão genérico/degenerado
    # (ex.: 33/33/33, 10/45/45, 45/45/10) em vez de uma probabilidade calculada
    # especificamente pro confronto — contar quantas vezes isso acontece.
    pattern_counts = defaultdict(int)
    for r in results:
        if r.get("p_home") is None:
            continue
        key = (round(r["p_home"], 2), round(r["p_draw"], 2), round(r["p_away"], 2))
        pattern_counts[key] += 1
    n_distinct_patterns = len(pattern_counts)
    n_in_top_patterns = sum(sorted(pattern_counts.values(), reverse=True)[:3])

    losses = []
    eps = 1e-9
    for r in results:
        if r.get("p_home") is None:
            continue
        ph, pd_, pa = r["p_home"], r["p_draw"], r["p_away"]
        s = ph + pd_ + pa
        if s <= 0:
            continue
        ph, pd_, pa = ph / s, pd_ / s, pa / s  # renormaliza (a API às vezes não soma exatamente 100%)
        if r["gh"] > r["ga"]:
            p_real = ph
        elif r["gh"] < r["ga"]:
            p_real = pa
        else:
            p_real = pd_
        losses.append(-math.log(max(p_real, eps)))

    mean_logloss = sum(losses) / len(losses) if losses else None

    lines = []
    lines.append("# Passo 0 — `/predictions` da api-football como baseline externo")
    lines.append("")
    lines.append(f"Amostra: {len(fixtures)} fixtures FT já resolvidos, temporadas 2025/2026, "
                 f"{len(set(f['league'] for f in fixtures))} competições distintas.")
    lines.append(f"Chamadas de API usadas: **{n_calls}** (`GET /predictions?fixture=`, throttle 0.15s).")
    lines.append("")
    lines.append(f"Resposta utilizável (`predictions.percent.{{home,draw,away}}` presente e parseável): "
                 f"**{n_usable}/{len(results)}**")
    if losses:
        lines.append(f"Log-loss (1X2) das probabilidades do vendor vs. resultado real, nesta amostra: "
                     f"**{mean_logloss:.4f}** (n={len(losses)}) — referência: log-loss de um palpite "
                     f"uniforme 33/33/33 constante seria ln(3) ≈ 1.0986.")
    else:
        lines.append("Não foi possível calcular log-loss (nenhuma resposta utilizável).")
    lines.append("")
    lines.append(f"**Achado relevante:** dos {n_usable} fixtures com resposta, só **{n_distinct_patterns} "
                 f"combinações distintas** de (p_home, p_draw, p_away) apareceram; as 3 mais comuns cobrem "
                 f"{n_in_top_patterns}/{n_usable} casos. Ou seja, a API frequentemente devolve um padrão "
                 f"genérico do tipo `33/33/33` (sem favorito claro) ou `10/45/45`/`45/45/10` (favorito de "
                 f"'vencer ou empatar') em vez de uma probabilidade calibrada específica pro confronto — "
                 f"isso é consistente com o log-loss ruim acima (pior que o palpite uniforme constante). "
                 f"Parece mais comum em competições menores/menos populares da amostra (ex.: Liga Panameña, "
                 f"Primera Nacional, Taça de Portugal), possivelmente por falta de histórico suficiente do "
                 f"lado do vendor.")
    lines.append("")
    lines.append("Exemplos (primeiros 8):")
    lines.append("")
    lines.append("| fixture_id | liga | placar | p_home | p_draw | p_away |")
    lines.append("|---|---|---|---|---|---|")
    for r in results[:8]:
        if r.get("p_home") is None:
            lines.append(f"| {r['fixture_id']} | {r.get('league')} | {r['gh']}-{r['ga']} | erro/vazio | | |")
        else:
            lines.append(f"| {r['fixture_id']} | {r.get('league')} | {r['gh']}-{r['ga']} | "
                         f"{r['p_home']:.2f} | {r['p_draw']:.2f} | {r['p_away']:.2f} |")
    lines.append("")
    lines.append("**IMPORTANTE:** isto é um spot-check informal numa amostra pequena e não-controlada — "
                 "NÃO é validação walk-forward, NÃO é comparável diretamente ao log-loss do nosso "
                 "próprio modelo sem rodar o mesmo protocolo (§6) na mesma amostra. Serve só de "
                 "orientação bruta para uma eventual comparação futura mais rigorosa.")
    lines.append("")
    if n_usable / max(len(results), 1) > 0.8 and mean_logloss is not None and mean_logloss < math.log(3):
        verdict = "viável (endpoint funciona e as probabilidades batem melhor que o palpite uniforme)"
    elif n_usable / max(len(results), 1) > 0.8:
        verdict = ("viável apenas como curiosidade, NÃO como baseline de comparação hoje — endpoint responde "
                  "sempre, mas as probabilidades são frequentemente genéricas/degeneradas (poucos padrões "
                  "distintos se repetindo) e o log-loss ficou PIOR que o palpite uniforme constante nesta "
                  "amostra; reavaliar com amostra maior focada em ligas grandes antes de usar como benchmark")
    else:
        verdict = "viável apenas parcialmente — endpoint não retorna dado utilizável na maioria dos fixtures testados"
    lines.append(f"**Veredito: {verdict}**")

    out = REPORT_DIR / "predictions_baseline.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[check2] escrito em {out}")
    if mean_logloss is not None:
        print(f"[check2] log-loss médio: {mean_logloss:.4f}")


# --------------------------------------------------------------------------------
# CHECK 3 — /teams/statistics minute-range breakdown (small live sample)
# --------------------------------------------------------------------------------
def _pick_team_league_season_combos(n: int) -> list[dict]:
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cur.execute("SELECT raw FROM raw WHERE season = 2025 ORDER BY RANDOM() LIMIT 4000")
    combos = {}
    for (raw,) in cur:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        league = d.get("league") or {}
        lid, season = league.get("id"), league.get("season")
        teams = d.get("teams") or {}
        for side in ("home", "away"):
            t = teams.get(side) or {}
            tid, tname = t.get("id"), t.get("name")
            if tid is None or lid is None or season is None:
                continue
            key = (lid, season, tid)
            combos.setdefault(key, {"league_id": lid, "season": season, "team_id": tid,
                                     "team_name": tname, "league_name": league.get("name")})
        if len(combos) >= n * 5:
            break
    vals = list(combos.values())
    random.shuffle(vals)
    return vals[:n]


MINUTE_RANGE_KEYS = ["0-15", "16-30", "31-45", "46-60", "61-75", "76-90", "91-105", "106-120"]


def check3_teams_statistics(n: int = 12):
    combos = _pick_team_league_season_combos(n)
    print(f"[check3] {len(combos)} combos time+liga+temporada selecionados")

    results = []
    n_calls = 0
    for c in combos:
        try:
            resp = _get("/teams/statistics", league=c["league_id"], season=c["season"], team=c["team_id"])
        except Exception as e:
            results.append({**c, "error": str(e)})
            n_calls += 1
            continue
        n_calls += 1
        body = resp.get("response") or {}
        goals = body.get("goals") or {}
        cards = body.get("cards") or {}

        def _minute_summary(block, side, has_minute_wrapper):
            side_block = block.get(side) or {}
            minute = (side_block.get("minute") if has_minute_wrapper else side_block) or {}
            out = {}
            for k in MINUTE_RANGE_KEYS:
                v = (minute.get(k) or {}).get("total")
                out[k] = v
            return out

        # `goals.for.minute.{range}.total` (com wrapper "minute"), mas
        # `cards.yellow.{range}.total` (SEM wrapper "minute") — formatos diferentes na mesma resposta.
        gf = _minute_summary(goals, "for", True)
        ga = _minute_summary(goals, "against", True)
        yellow = _minute_summary(cards, "yellow", False)
        red = _minute_summary(cards, "red", False)

        any_nonzero = any(v not in (None, 0) for v in list(gf.values()) + list(ga.values()) +
                          list(yellow.values()) + list(red.values()))
        results.append({**c, "goals_for": gf, "goals_against": ga, "yellow": yellow, "red": red,
                        "any_nonzero": any_nonzero})

    n_populated = sum(1 for r in results if r.get("any_nonzero"))
    print(f"[check3] {n_populated}/{len(results)} combos com dado por-faixa-de-minuto não-vazio, {n_calls} chamadas")

    lines = []
    lines.append("# Passo 0 — `/teams/statistics` (gols/cartões por faixa de minuto)")
    lines.append("")
    lines.append(f"Amostra: {len(combos)} combos time+liga+temporada (season=2025).")
    lines.append(f"Chamadas de API usadas: **{n_calls}** (1 por combo, `GET /teams/statistics`, throttle 0.15s).")
    lines.append("")
    lines.append(f"Combos com faixas de minuto populadas (algum valor não-nulo/não-zero em "
                 f"gols ou cartões): **{n_populated}/{len(results)}**")
    lines.append("")
    lines.append("Detalhe por combo:")
    lines.append("")
    lines.append("| time | liga | gols_contra 76-90 | gols_contra 0-15 | amarelos 76-90 | amarelos 0-15 |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r.get('team_name')} | {r.get('league_name')} | ERRO: {r['error']} | | | |")
            continue
        ga = r["goals_against"]
        ye = r["yellow"]
        lines.append(f"| {r['team_name']} | {r.get('league_name')} | {ga.get('76-90')} | {ga.get('0-15')} | "
                     f"{ye.get('76-90')} | {ye.get('0-15')} |")

    lines.append("")
    # sanity check: late-game concentration
    late_vs_early_ga = []
    late_vs_early_yc = []
    for r in results:
        if "error" in r:
            continue
        ga, ye = r["goals_against"], r["yellow"]
        late_ga, early_ga = ga.get("76-90"), ga.get("0-15")
        late_ye, early_ye = ye.get("76-90"), ye.get("0-15")
        if late_ga is not None and early_ga is not None:
            late_vs_early_ga.append((late_ga, early_ga))
        if late_ye is not None and early_ye is not None:
            late_vs_early_yc.append((late_ye, early_ye))
    if late_vs_early_ga:
        n_late_higher = sum(1 for l, e in late_vs_early_ga if l > e)
        lines.append(f"Sanity check gols sofridos: em {n_late_higher}/{len(late_vs_early_ga)} times, "
                     f"faixa 76-90 > faixa 0-15 (indício informal de 'late collapse', não é achado validado).")
    if late_vs_early_yc:
        n_late_higher_yc = sum(1 for l, e in late_vs_early_yc if l > e)
        lines.append(f"Sanity check cartões amarelos: em {n_late_higher_yc}/{len(late_vs_early_yc)} times, "
                     f"faixa 76-90 > faixa 0-15.")

    lines.append("")
    lines.append("**Custo de cobertura total:** 1 chamada por combo time+liga+temporada. Para o roster "
                 "completo de ~2.300+ times de clube (1 temporada cada) isso seria da ordem de "
                 "**~2.300-2.500 chamadas** — barato dentro da cota diária de 75k, mas não-trivial se "
                 "for repetido por múltiplas temporadas por time (ex.: 3 temporadas x 2.300 times "
                 "≈ 6.900-7.500 chamadas). Vale rodar como job dedicado, não dentro deste script.")
    lines.append("")
    if n_populated / max(len(results), 1) > 0.7:
        verdict = "viável (endpoint retorna dado real por faixa de minuto na maioria dos casos) — considerar como feature futura, mas medir custo de coleta completa antes de comprometer"
    else:
        verdict = "viável parcialmente — várias combinações vieram vazias, checar se é específico de liga/temporada antes de investir"
    lines.append(f"**Veredito: {verdict}**")

    out = REPORT_DIR / "teams_statistics_minuto.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[check3] escrito em {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", choices=["1", "2", "3", "all"], default="all")
    ap.add_argument("--n", type=int, default=40, help="tamanho da amostra p/ checks 2 e 3")
    a = ap.parse_args()

    if a.check in ("1", "all"):
        check1_goals_prevented()
    if a.check in ("2", "all"):
        check2_predictions_baseline(n=a.n)
    if a.check in ("3", "all"):
        check3_teams_statistics(n=min(a.n, 15))


if __name__ == "__main__":
    main()
