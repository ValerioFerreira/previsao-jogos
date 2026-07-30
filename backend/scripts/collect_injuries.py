#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
scripts/collect_injuries.py — coleta de lesões/desfalques por liga e temporada.
================================================================================

Fecha a lacuna registrada em `backend/docs/RELATORIO_NOVAS_VARIAVEIS.md` §1.5: o
endpoint `/injuries` da API-Football sempre esteve disponível, mas só era chamado sob
demanda para uma partida de seleção — nunca em massa para clubes. Sem esse dado, a
ausência de jogador é tratada como binário grosseiro (ou ignorada), e o candidato mais
bem ranqueado da pesquisa ("dedução de rating por lesão ponderada por status", §3 item 3)
não tinha como ser testado sob o gate §6.

## Por que é barato e por que é retroativo (medido em 2026-07-30)

`GET /injuries?league=39&season=2025` devolveu **3.417 registros numa única resposta**,
`paging.total = 1` — a API não pagina este endpoint por liga/temporada. Cada registro já
vem amarrado a um `fixture_id` específico, ou seja, **é histórico, não só o "quem está
fora hoje"**. Isso permite construir a feature sobre o dataset de treino inteiro, e não
apenas para partidas futuras.

Custo total da varredura completa: ~83 ligas × 7 temporadas ≈ **600 chamadas**.

## Cobertura real (sondada, não presumida)

Não existe para todo o histórico. Amostra medida:

    Premier League : 2020=598  2021=2563 2022=3056 2023=3853 2024=3168 2025=3417
    La Liga        : 2020=648  2021=2492 2022=2653 2023=2836 2024=2424 2025=3107
    Brasileirão A  : 2020..2023=0        2024=1668 2025=3621 2026=2382
    Libertadores   : 2020..2024=0        2025=109
    MLS            : 2020=0    2021=2067 ...       2025=3535 2026=3108

Ou seja: grandes ligas europeias a partir de 2020/21, Brasileirão a partir de 2024,
competições continentais sul-americanas praticamente ausentes. **Qualquer modelo que use
esta feature precisa tratar "sem dado" como categoria própria, nunca como "zero lesões"** —
senão a ausência de cobertura vira sinal falso de elenco cheio.

Uso:
  python -m scripts.collect_injuries                      # 83 ligas × 2020-2026
  python -m scripts.collect_injuries --current-only       # só a temporada corrente (diário)
  python -m scripts.collect_injuries --seasons 2023,2024  # temporadas específicas
  python -m scripts.collect_injuries --scope selecao      # ligas de seleção
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests  # noqa: E402

from scripts.fetch_odds import BASE, load_key  # noqa: E402
from scripts.prefetch_clubs import LEAGUES as CLUB_LEAGUES  # noqa: E402
from scripts import quota_tracker  # noqa: E402

DB_PATH = ROOT / "data" / "injuries.sqlite"

# Antes de 2020 a API praticamente não tem cobertura de lesão em liga nenhuma (sondado).
DEFAULT_SEASON_FROM = 2020


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS injuries (
            fixture_id   INTEGER,
            fixture_date TEXT,
            league_id    INTEGER,
            season       INTEGER,
            team_id      INTEGER,
            team_name    TEXT,
            player_id    INTEGER,
            player_name  TEXT,
            type         TEXT,
            reason       TEXT,
            PRIMARY KEY (fixture_id, player_id)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_inj_team ON injuries(team_id, fixture_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_inj_league ON injuries(league_id, season)")
    # Registro de (liga, temporada) já varridos, para o run diário não repetir histórico.
    con.execute("""
        CREATE TABLE IF NOT EXISTS collected (
            league_id INTEGER, season INTEGER, n_rows INTEGER, collected_at TEXT,
            PRIMARY KEY (league_id, season)
        )
    """)
    con.commit()
    return con


def _selecao_league_ids() -> list[tuple[int, str]]:
    """Ligas de seleção = as que o coletor forward de seleções já usa como alvo."""
    from scripts.collect_odds_forward import target_league_ids
    return [(lid, f"selecao_{lid}") for lid in sorted(target_league_ids())]


def fetch_league_season(key: str, league_id: int, season: int) -> list[dict]:
    quota_tracker.throttle()
    r = requests.get(BASE + "/injuries", headers={"x-apisports-key": key},
                     params={"league": league_id, "season": season}, timeout=60)
    r.raise_for_status()
    quota_tracker.note_call()
    return r.json().get("response", []) or []


def store(con: sqlite3.Connection, rows: list[dict], league_id: int, season: int) -> int:
    out = []
    for it in rows:
        pl = it.get("player") or {}
        tm = it.get("team") or {}
        fx = it.get("fixture") or {}
        if not (fx.get("id") and pl.get("id")):
            continue
        out.append((
            fx.get("id"), (fx.get("date") or "")[:10], league_id, season,
            tm.get("id"), tm.get("name"), pl.get("id"), pl.get("name"),
            pl.get("type"), pl.get("reason"),
        ))
    if out:
        con.executemany("INSERT OR REPLACE INTO injuries VALUES (?,?,?,?,?,?,?,?,?,?)", out)
    con.execute("INSERT OR REPLACE INTO collected VALUES (?,?,?,?)",
                (league_id, season, len(out), dt.datetime.now().isoformat(timespec="seconds")))
    con.commit()
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Coleta /injuries por liga e temporada")
    ap.add_argument("--scope", choices=("clube", "selecao", "ambos"), default="clube")
    ap.add_argument("--season-from", type=int, default=DEFAULT_SEASON_FROM)
    ap.add_argument("--season-to", type=int, default=dt.date.today().year)
    ap.add_argument("--seasons", help="lista explícita, ex: 2024,2025 (ignora --season-from/to)")
    ap.add_argument("--current-only", action="store_true",
                    help="só a temporada corrente — modo do cron diário (~83 chamadas)")
    ap.add_argument("--buffer", type=int, default=500, help="para quando a cota chegar aqui")
    ap.add_argument("--redo", action="store_true",
                    help="revarre pares (liga, temporada) já coletados de temporadas fechadas")
    a = ap.parse_args()

    if a.seasons:
        seasons = [int(s) for s in a.seasons.split(",") if s.strip()]
    elif a.current_only:
        seasons = [dt.date.today().year]
    else:
        seasons = list(range(a.season_to, a.season_from - 1, -1))

    leagues: list[tuple[int, str]] = []
    if a.scope in ("clube", "ambos"):
        leagues += list(CLUB_LEAGUES)
    if a.scope in ("selecao", "ambos"):
        leagues += _selecao_league_ids()

    key = load_key()
    con = _init_db()

    # Temporada corrente e anterior nunca contam como "fechadas": ainda recebem registros.
    this_year = dt.date.today().year
    mutable = {this_year, this_year - 1}
    done = set()
    if not a.redo:
        done = {(l, s) for (l, s) in con.execute(
            "SELECT league_id, season FROM collected") if s not in mutable}

    print("=" * 78)
    print(f" COLETA DE LESOES -- {len(leagues)} ligas x {len(seasons)} temporadas "
          f"= {len(leagues) * len(seasons)} chamadas no maximo")
    print(f" Escopo: {a.scope} | temporadas: {seasons[0]}..{seasons[-1]} | "
          f"ja coletados (pulados): {len(done)}")
    print(f" Cota restante: {quota_tracker.remaining()}")
    print("=" * 78)

    n_calls = n_rows = n_skip = 0
    vazias = 0
    for league_id, league_name in leagues:
        for season in seasons:
            if (league_id, season) in done:
                n_skip += 1
                continue
            if quota_tracker.remaining() <= a.buffer:
                print(f"[AVISO] cota perto do limite ({quota_tracker.remaining()}) -- parando.")
                con.close()
                _summary(n_calls, n_rows, n_skip, vazias)
                return
            try:
                rows = fetch_league_season(key, league_id, season)
            except Exception as e:
                print(f"  ERRO {league_name} {season}: {type(e).__name__}")
                continue
            n_calls += 1
            got = store(con, rows, league_id, season)
            n_rows += got
            if got == 0:
                vazias += 1
            else:
                print(f"  OK  {league_name[:34]:34s} {season}  {got:5d} registros")

    con.close()
    _summary(n_calls, n_rows, n_skip, vazias)


def _summary(n_calls: int, n_rows: int, n_skip: int, vazias: int) -> None:
    print("\n" + "=" * 78)
    print(f"Chamadas: {n_calls} | registros gravados: {n_rows} | "
          f"pares pulados (ja coletados): {n_skip} | sem cobertura: {vazias}")
    con = sqlite3.connect(DB_PATH)
    try:
        total, fx, tm = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT fixture_id), COUNT(DISTINCT team_id) FROM injuries"
        ).fetchone()
        print(f"Acumulado no banco: {total} registros | {fx} fixtures | {tm} times")
        print("\nTop temporadas:")
        for season, n in con.execute(
                "SELECT season, COUNT(*) FROM injuries GROUP BY season ORDER BY season DESC LIMIT 10"):
            print(f"  {season}  {n}")
    finally:
        con.close()
    print(f"Cota restante: {quota_tracker.remaining()}")


if __name__ == "__main__":
    main()
