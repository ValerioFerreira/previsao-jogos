#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
scripts/build_squad_context_features.py — contexto de elenco, técnico e desfalques.
====================================================================================

Gera features de **contexto de time** que hoje não existem no dataset de treino, lendo
apenas dados que já estão em disco. Custo de cota da API-Football: **zero**.

## De onde vem cada coisa

Achado de 2026-07-30: `coach.id` e `formation` **já vêm dentro do blob** de cada partida
(`lineups[].coach.id`, `lineups[].formation`, `lineups[].startXI[].player.id`), guardado em
`data/club_raw_cache.sqlite` desde sempre. Ou seja, troca de técnico, formação e
continuidade de escalação são deriváveis para as 273 mil partidas já coletadas sem gastar
uma requisição — não é preciso chamar `/coachs` nem `/transfers`, como se supunha no
`backend/docs/RELATORIO_NOVAS_VARIAVEIS.md`. Desfalques vêm de `data/injuries.sqlite`
(`scripts/collect_injuries.py`).

## Regra point-in-time (a que já reprovou hipótese neste projeto)

Toda feature derivada de partidas usa **somente jogos anteriores** ao da linha — a
escalação e o técnico da própria partida nunca entram, porque o blob só existe depois do
jogo. Concretamente, para o jogo `t` do time A, tudo é calculado sobre `t-1, t-2, ...`.

Exceção deliberada e declarada: as colunas `*_inj_*` usam a lista de desfalques **da própria
partida**. Isso é legítimo — a lista de lesionados/suspensos é pública antes do apito, e é
assim que ela seria usada em produção. Está separada em colunas próprias justamente para
que o gate §6 possa testá-la isolada e para que ninguém a confunda com as demais.

## Armadilha de cobertura (não ignore)

A cobertura de `/injuries` é desigual: grandes europeias a partir de 2020/21, Brasileirão só
a partir de 2024, Libertadores quase nada. Por isso sai também `{lado}_inj_has_data`: sem
ele, "0 desfalques" por falta de cobertura vira sinal falso de elenco cheio. **Nenhum modelo
deve consumir a contagem sem consumir a flag.**

Uso:
  python -m scripts.build_squad_context_features                 # clubes (padrão)
  python -m scripts.build_squad_context_features --scope selecao
  python -m scripts.build_squad_context_features --limit 5000    # amostra p/ teste rápido

Saída: data/built/squad_context_features.parquet — uma linha por fixture, colunas
`home_*`/`away_*`, pronta para join por `fixture_id` no dataset de treino.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd  # noqa: E402

CLUB_DB = ROOT / "data" / "club_raw_cache.sqlite"
SELECAO_DB = ROOT / "data" / "raw_cache.sqlite"
INJ_DB = ROOT / "data" / "injuries.sqlite"
OUT_PATH = ROOT / "data" / "built" / "squad_context_features.parquet"

FINISHED = {"FT", "AET", "PEN"}
RECENT_N = 5          # janela curta usada nas médias de continuidade/estabilidade
NEW_SPELL_MAX = 3     # até N jogos, o técnico ainda conta como "recém-chegado"


def _extract(raw: dict) -> dict | None:
    """Reduz o blob da partida ao mínimo necessário. Retorna None se inutilizável."""
    fx = raw.get("fixture") or {}
    fid = fx.get("id")
    date = (fx.get("date") or "")[:10]
    if not fid or not date:
        return None
    if ((fx.get("status") or {}).get("short")) not in FINISHED:
        return None
    teams = raw.get("teams") or {}
    home_id = ((teams.get("home") or {}).get("id"))
    away_id = ((teams.get("away") or {}).get("id"))
    if not (home_id and away_id):
        return None

    # lineups vem como lista de 0..2 blocos, um por time — a ordem não é garantida.
    per_team: dict[int, dict] = {}
    for blk in (raw.get("lineups") or []):
        tid = ((blk.get("team") or {}).get("id"))
        if not tid:
            continue
        xi = []
        for slot in (blk.get("startXI") or []):
            pid = ((slot.get("player") or {}).get("id"))
            if pid:
                xi.append(int(pid))
        per_team[int(tid)] = {
            "coach_id": ((blk.get("coach") or {}).get("id")),
            "formation": blk.get("formation"),
            "xi": frozenset(xi),
        }

    return {
        "fixture_id": int(fid),
        "date": date,
        "league_id": ((raw.get("league") or {}).get("id")),
        "season": ((raw.get("league") or {}).get("season")),
        "home_team_id": int(home_id),
        "away_team_id": int(away_id),
        "home_lineup": per_team.get(int(home_id)),
        "away_lineup": per_team.get(int(away_id)),
    }


def load_matches(db_path: Path, limit: int | None) -> list[dict]:
    if not db_path.exists():
        raise SystemExit(f"espelho local nao encontrado: {db_path}")
    con = sqlite3.connect(str(db_path))
    sql = "SELECT raw FROM raw"
    if limit:
        sql += f" LIMIT {int(limit)}"
    out = []
    n = 0
    for (rawj,) in con.execute(sql):
        n += 1
        if n % 25000 == 0:
            print(f"  ... {n} blobs lidos, {len(out)} aproveitados", flush=True)
        try:
            rec = _extract(json.loads(rawj))
        except Exception:
            continue
        if rec:
            out.append(rec)
    con.close()
    print(f"  {n} blobs lidos, {len(out)} partidas encerradas com dado utilizavel", flush=True)
    return out


def _jaccard(a: frozenset, b: frozenset) -> float | None:
    if not a or not b:
        return None
    union = len(a | b)
    return (len(a & b) / union) if union else None


def build_team_history(matches: list[dict]) -> dict[int, list[dict]]:
    """Histórico por time, ordenado no tempo: [{date, coach_id, formation, xi}, ...]."""
    hist: dict[int, list[dict]] = defaultdict(list)
    for m in sorted(matches, key=lambda r: (r["date"], r["fixture_id"])):
        for side in ("home", "away"):
            lu = m[f"{side}_lineup"]
            if not lu:
                continue
            hist[m[f"{side}_team_id"]].append({
                "fixture_id": m["fixture_id"],
                "date": m["date"],
                "coach_id": lu["coach_id"],
                "formation": lu["formation"],
                "xi": lu["xi"],
            })
    return hist


def features_before(games: list[dict], idx: int, date: str) -> dict:
    """Features do time para a partida em `games[idx]`, usando SÓ `games[:idx]`.

    `idx` é a posição da partida corrente no histórico do time; nada em `games[idx:]`
    é lido. Quando não há jogo anterior, tudo sai como None (o modelo trata como
    ausente em vez de receber um zero que significaria outra coisa).
    """
    prev = games[:idx]
    if not prev:
        return {}
    last = prev[-1]
    out: dict = {}

    # --- técnico: quantos jogos e quantos dias no comando atual -------------------
    cur_coach = last["coach_id"]
    if cur_coach is not None:
        spell = 0
        spell_start = last["date"]
        for g in reversed(prev):
            if g["coach_id"] != cur_coach:
                break
            spell += 1
            spell_start = g["date"]
        out["coach_matches"] = spell
        out["coach_days"] = (pd.Timestamp(date) - pd.Timestamp(spell_start)).days
        out["coach_is_new"] = int(spell <= NEW_SPELL_MAX)
        # Trocou de técnico entre os dois últimos jogos?
        if len(prev) >= 2 and prev[-2]["coach_id"] is not None:
            out["coach_changed_last"] = int(prev[-2]["coach_id"] != cur_coach)

    # --- formação: estabilidade tática -------------------------------------------
    forms = [g["formation"] for g in prev[-RECENT_N:] if g["formation"]]
    if forms:
        modal = max(set(forms), key=forms.count)
        out["formation_stability"] = forms.count(modal) / len(forms)
        if len(forms) >= 2:
            out["formation_changed_last"] = int(forms[-1] != forms[-2])

    # --- continuidade de elenco ---------------------------------------------------
    xis = [g["xi"] for g in prev[-(RECENT_N + 1):] if g["xi"]]
    if len(xis) >= 2:
        pairs = [_jaccard(xis[i - 1], xis[i]) for i in range(1, len(xis))]
        pairs = [p for p in pairs if p is not None]
        if pairs:
            out["squad_continuity"] = sum(pairs) / len(pairs)
    # Núcleo fixo: jogadores presentes em TODAS as escalações recentes.
    if len(xis) >= 3:
        core = set(xis[0])
        for s in xis[1:]:
            core &= s
        out["squad_core_size"] = len(core)

    return out


def load_injuries() -> tuple[dict[tuple[int, int], dict], set[tuple[int, int]]]:
    """(fixture_id, team_id) -> contagens; e o conjunto de (league_id, season) cobertos."""
    if not INJ_DB.exists():
        print("[AVISO] injuries.sqlite ausente — colunas *_inj_* sairao vazias", flush=True)
        return {}, set()
    con = sqlite3.connect(str(INJ_DB))
    counts: dict[tuple[int, int], dict] = {}
    for fid, tid, typ in con.execute("SELECT fixture_id, team_id, type FROM injuries"):
        if fid is None or tid is None:
            continue
        c = counts.setdefault((int(fid), int(tid)), {"missing": 0, "questionable": 0})
        if typ == "Missing Fixture":
            c["missing"] += 1
        else:
            c["questionable"] += 1
    covered = {(int(l), int(s)) for l, s, n in
               con.execute("SELECT league_id, season, n_rows FROM collected") if n and n > 0}
    con.close()
    print(f"  lesoes: {len(counts)} pares (fixture,time) | {len(covered)} pares (liga,temporada) cobertos",
          flush=True)
    return counts, covered


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=("clube", "selecao"), default="clube")
    ap.add_argument("--limit", type=int, help="le so N blobs (teste rapido)")
    ap.add_argument("--out", default=str(OUT_PATH))
    a = ap.parse_args()

    db = CLUB_DB if a.scope == "clube" else SELECAO_DB
    print("=" * 78)
    print(f" CONTEXTO DE ELENCO -- escopo {a.scope} | fonte {db.name}")
    print("=" * 78)

    matches = load_matches(db, a.limit)
    hist = build_team_history(matches)
    print(f"  {len(hist)} times com historico de escalacao", flush=True)

    # Posição de cada (time, fixture) dentro do histórico do time — é o que garante que
    # `features_before` receba um índice e nunca enxergue o futuro.
    pos: dict[tuple[int, int], int] = {}
    for tid, games in hist.items():
        for i, g in enumerate(games):
            pos[(tid, g["fixture_id"])] = i

    inj_counts, inj_covered = load_injuries()

    rows = []
    for m in matches:
        row = {"fixture_id": m["fixture_id"], "date": m["date"],
               "league_id": m["league_id"], "season": m["season"]}
        ls_covered = (m["league_id"], m["season"]) in inj_covered
        for side in ("home", "away"):
            tid = m[f"{side}_team_id"]
            i = pos.get((tid, m["fixture_id"]))
            feats = features_before(hist[tid], i, m["date"]) if i is not None else {}
            for k, v in feats.items():
                row[f"{side}_{k}"] = v
            c = inj_counts.get((m["fixture_id"], tid))
            row[f"{side}_inj_has_data"] = int(ls_covered)
            row[f"{side}_inj_missing"] = c["missing"] if c else (0 if ls_covered else None)
            row[f"{side}_inj_questionable"] = c["questionable"] if c else (0 if ls_covered else None)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    print("\n" + "=" * 78)
    print(f"Gravado: {out_path}  ({len(df)} linhas x {len(df.columns)} colunas)")
    print("\nPreenchimento por coluna:")
    for c in df.columns:
        if c in ("fixture_id", "date", "league_id", "season"):
            continue
        nn = df[c].notna().sum()
        print(f"  {c:32s} {nn:7d}  ({100*nn/len(df):5.1f}%)")
    print("\nATENCAO: *_inj_* usa a lista da PROPRIA partida (informacao publica pre-jogo);")
    print("todas as demais colunas usam somente partidas ANTERIORES. Use *_inj_has_data")
    print("junto com as contagens -- 0 sem cobertura nao e 0 desfalques.")


if __name__ == "__main__":
    main()
