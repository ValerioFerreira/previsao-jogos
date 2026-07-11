#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_clubs.py
=========================
PREFETCH do detalhe completo (statistics/events/lineups/players) dos jogos dos CLUBES —
a próxima adição ao sistema. Só roda com a cota OCIOSA (as seleções já saturaram; sobra
~70k/dia). Grava numa tabela SEPARADA `club_match_detail_cache` (com league_id) para NÃO
contaminar os modelos de seleção, que varrem apenas `match_detail_cache`.

Ordem de PRIORIDADE (Brasil primeiro, depois Europa) — cobre uma liga inteira antes de ir
para a próxima, do mais recente ao mais antigo. Cache-first (pula o que já tem), guarda de
cota (para na margem) e resumível — o backfill se completa ao longo dos dias.

Uso: python scripts/prefetch_clubs.py [--max 60000] [--margin 200] [--from 2026] [--to 2015]
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get

def _get_throttled(path, **params):
    """_get() com throttle: 450 req/min = 0.15s entre requests."""
    result = _get(path, **params)
    time.sleep(0.15)
    return result

# (league_id, nome) na ordem de prioridade: Brasil -> Europa.
LEAGUES = [
    (71, "Brasileirao Serie A"),
    (72, "Brasileirao Serie B"),
    (73, "Copa do Brasil"),
    (39, "Premier League"),
    (140, "La Liga"),
    (135, "Serie A (Italia)"),
    (78, "Bundesliga"),
    (61, "Ligue 1"),
]
FINISHED = {"FT", "AET", "PEN"}
TABLE = "club_match_detail_cache"


def ensure_table():
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            "key TEXT PRIMARY KEY, fixture_id BIGINT, league_id INT, season INT, raw TEXT, "
            "cached_at TIMESTAMPTZ DEFAULT now())"
        ))


def cached_ids() -> set:
    from app.db.connection import engine
    with engine.connect() as c:
        rows = c.execute(text(f"SELECT fixture_id FROM {TABLE}")).fetchall()
    return {r[0] for r in rows if r[0] is not None}


def put(fixture_id, league_id, season, raw):
    from app.db.connection import engine
    key = f"club|{league_id}|{fixture_id}"
    with engine.begin() as c:
        c.execute(text(
            f"INSERT INTO {TABLE} (key, fixture_id, league_id, season, raw, cached_at) "
            "VALUES (:k,:f,:l,:s,:r, now()) ON CONFLICT (key) DO UPDATE SET raw=EXCLUDED.raw, cached_at=now()"
        ), {"k": key, "f": fixture_id, "l": league_id, "s": season, "r": json.dumps(raw, ensure_ascii=False)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60000)
    ap.add_argument("--margin", type=int, default=200)
    ap.add_argument("--from", dest="ffrom", type=int, default=2026)
    ap.add_argument("--to", dest="fto", type=int, default=2015)
    a = ap.parse_args()

    ensure_table()
    have = cached_ids()
    state = {"calls": 0, "novos": 0, "jacache": len(have), "falhas": 0, "rem": None, "parou": None}

    def budget_ok():
        if state["calls"] >= a.max:
            state["parou"] = "MAX"; return False
        if state["rem"] is not None and state["rem"] <= a.margin:
            state["parou"] = "LIMITE_DIARIO"; return False
        return True

    print(f"Clubs prefetch | ja em cache: {len(have)} fixtures | ligas: {[n for _, n in LEAGUES]}", flush=True)
    for league_id, nome in LEAGUES:
        if not budget_ok():
            break
        print(f"== Liga {nome} ({league_id}) ==", flush=True)
        for season in range(a.ffrom, a.fto - 1, -1):
            if not budget_ok():
                break
            try:
                fxs, rem = _get_throttled("/fixtures", league=league_id, season=season)
                state["calls"] += 1
                if rem is not None:
                    state["rem"] = int(rem)
            except Exception as e:
                print(f"  [AVISO] {nome}/{season}: {e}", flush=True); continue
            finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            todo = [f for f in finished if (f.get("fixture") or {}).get("id") not in have]
            print(f"  {season}: {len(finished)} encerrados, {len(todo)} a baixar | cota ~{state['rem']}", flush=True)
            for f in todo:
                if not budget_ok():
                    break
                fid = (f.get("fixture") or {}).get("id")
                if not fid:
                    continue
                try:
                    resp, rem = _get_throttled("/fixtures", id=fid)
                    state["calls"] += 1
                    if rem is not None:
                        state["rem"] = int(rem)
                    if resp:
                        put(fid, league_id, season, resp[0]); have.add(fid); state["novos"] += 1
                    else:
                        state["falhas"] += 1
                except Exception as e:
                    state["falhas"] += 1
                    print(f"    [AVISO] fixture {fid}: {e}", flush=True)

    print(f">> Clubs: {state['novos']} novos | {state['falhas']} falhas | {state['calls']} chamadas | "
          f"cota ~{state['rem']} | parou por: {state['parou'] or 'FIM (tudo coberto)'}", flush=True)


if __name__ == "__main__":
    main()
