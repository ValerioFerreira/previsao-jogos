#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_serie_a.py
===========================
PREFETCH do detalhe completo (statistics/events/lineups/players) dos jogos do
**Campeonato Brasileiro Série A** (API-Football league=71), a PRÓXIMA adição ao sistema.
Grava numa tabela SEPARADA (`serie_a_detail_cache`) para NÃO contaminar os modelos de
seleção, que varrem `match_detail_cache`.

Roda só com a cota OCIOSA: o prefetch de seleções (all-nations) já saturou e sobra ~70k/dia.
Cache-first (pula o que já tem), guarda de cota (para na margem) e resumível — cobre as
temporadas do mais recente ao mais antigo ao longo dos dias.

Uso: python scripts/prefetch_serie_a.py [--max 40000] [--margin 200] [--from 2026] [--to 2015]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get

LEAGUE = 71  # Brasileirão Série A
FINISHED = {"FT", "AET", "PEN"}
TABLE = "serie_a_detail_cache"


def ensure_table():
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            "key TEXT PRIMARY KEY, fixture_id BIGINT, season INT, raw TEXT, "
            "cached_at TIMESTAMPTZ DEFAULT now())"
        ))


def cached_ids() -> set:
    from app.db.connection import engine
    with engine.connect() as c:
        rows = c.execute(text(f"SELECT fixture_id FROM {TABLE}")).fetchall()
    return {r[0] for r in rows if r[0] is not None}


def put(fixture_id, season, raw):
    from app.db.connection import engine
    key = f"seriea|{fixture_id}"
    with engine.begin() as c:
        c.execute(text(
            f"INSERT INTO {TABLE} (key, fixture_id, season, raw, cached_at) "
            "VALUES (:k,:f,:s,:r, now()) ON CONFLICT (key) DO UPDATE SET raw=EXCLUDED.raw, cached_at=now()"
        ), {"k": key, "f": fixture_id, "s": season, "r": json.dumps(raw, ensure_ascii=False)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40000)
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

    print(f"Serie A prefetch | ja em cache: {len(have)} fixtures", flush=True)
    for season in range(a.ffrom, a.fto - 1, -1):
        if not budget_ok():
            break
        try:
            fxs, rem = _get("/fixtures", league=LEAGUE, season=season)
            state["calls"] += 1
            if rem is not None:
                state["rem"] = int(rem)
        except Exception as e:
            print(f"  [AVISO] fixtures {season}: {e}", flush=True); continue
        finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
        print(f"  temporada {season}: {len(finished)} jogos encerrados | cota ~{state['rem']}", flush=True)
        for f in finished:
            if not budget_ok():
                break
            fid = (f.get("fixture") or {}).get("id")
            if not fid or fid in have:
                continue
            try:
                resp, rem = _get("/fixtures", id=fid)
                state["calls"] += 1
                if rem is not None:
                    state["rem"] = int(rem)
                if resp:
                    put(fid, season, resp[0]); have.add(fid); state["novos"] += 1
                else:
                    state["falhas"] += 1
            except Exception as e:
                state["falhas"] += 1
                print(f"    [AVISO] fixture {fid}: {e}", flush=True)

    print(f">> Serie A: {state['novos']} novos | {state['falhas']} falhas | {state['calls']} chamadas | "
          f"cota ~{state['rem']} | parou por: {state['parou'] or 'FIM'}", flush=True)


if __name__ == "__main__":
    main()
