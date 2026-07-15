#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/mirror_club_cache.py
============================
Cria o espelho LOCAL (SQLite) do bruto de CLUBES sem egress do Neon: lê apenas a
lista de fixture_ids do `club_match_detail_cache` (~2 MB) e re-baixa o detalhe
completo direto da API-Football para `data/club_raw_cache.sqlite`, usando a cota
ociosa do dia (as coletas já saturaram). Resumível e com guarda de cota.

Por que não puxar o raw do Neon: são ~2,4 GB de blobs — o projeto acabou de reduzir
o egress mensal para <0,5 GB (ARCHITECTURE.md §3.1). A API custa 1 chamada/jogo da
cota diária de 75k, que hoje está ociosa.

Uso: python scripts/mirror_club_cache.py [--max 60000] [--margin 1000]
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get

LOCAL_PATH = Path(__file__).resolve().parents[1] / "data" / "club_raw_cache.sqlite"


def _conn() -> sqlite3.Connection:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOCAL_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS raw (key TEXT PRIMARY KEY, fixture_id INTEGER, "
        "league_id INTEGER, season INTEGER, raw TEXT)"
    )
    return conn


def neon_id_list():
    """Só ids/league/season do Neon — colunas pequenas, sem blobs."""
    from app.db.connection import engine
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT fixture_id, league_id, season FROM club_match_detail_cache"
        )).fetchall()
    return [(int(r[0]), int(r[1]), int(r[2])) for r in rows if r[0] is not None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60000)
    ap.add_argument("--margin", type=int, default=1000)
    a = ap.parse_args()

    conn = _conn()
    have = {r[0] for r in conn.execute("SELECT fixture_id FROM raw").fetchall()}
    ids = neon_id_list()
    todo = [(f, l, s) for f, l, s in ids if f not in have]
    print(f"Mirror clubes | no Neon: {len(ids)} | ja no espelho: {len(have)} | a baixar: {len(todo)}",
          flush=True)

    calls, ok, fail, rem = 0, 0, 0, None
    t0 = time.time()
    for i, (fid, lid, season) in enumerate(todo):
        if calls >= a.max:
            print(f"PAROU: MAX ({a.max})", flush=True); break
        if rem is not None and rem <= a.margin:
            print(f"PAROU: LIMITE_DIARIO (rem={rem})", flush=True); break
        try:
            resp, r = _get("/fixtures", id=fid)
            calls += 1
            if r is not None:
                rem = int(r)
            if resp:
                conn.execute(
                    "INSERT OR REPLACE INTO raw(key, fixture_id, league_id, season, raw) "
                    "VALUES (?,?,?,?,?)",
                    (f"club|{lid}|{fid}", fid, lid, season,
                     json.dumps(resp[0], ensure_ascii=False)))
                ok += 1
            else:
                fail += 1
            time.sleep(0.15)
        except Exception as e:
            fail += 1
            print(f"  [AVISO] fixture {fid}: {e}", flush=True)
            time.sleep(1.0)
        if (i + 1) % 500 == 0:
            conn.commit()
            rate = (i + 1) / max(time.time() - t0, 1)
            eta_min = (len(todo) - i - 1) / max(rate, 0.01) / 60
            print(f"  progresso {i+1}/{len(todo)} | ok={ok} fail={fail} | cota ~{rem} | "
                  f"ETA {eta_min:.0f} min", flush=True)
    conn.commit()
    n = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    conn.close()
    print(f">> Mirror: {ok} baixados | {fail} falhas | {calls} chamadas | cota ~{rem} | "
          f"total no espelho: {n}", flush=True)


if __name__ == "__main__":
    main()
