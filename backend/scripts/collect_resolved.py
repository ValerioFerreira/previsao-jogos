#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coleta DIÁRIA de jogos resolvidos: busca as partidas finalizadas da Copa do
Mundo (e reaproveita o cache de detalhe) que ainda NÃO estão na base `matches`
do Neon, e as anexa. Mantém os dados das seleções atualizados sem duplicar.

Uso: python scripts/collect_resolved.py [--league 1] [--season 2026]
"""
import argparse
import sys
sys.path.insert(0, ".")
import pandas as pd
from sqlalchemy import text

from app.db.connection import engine
from app.services.fixture_fetch import _get, fetch_full_by_id, cache_get, cache_put
from app.services.predictor_service import _norm
from build_history import parse_match

FINISHED = {"FT", "AET", "PEN"}


def existing_keys() -> set:
    df = pd.read_sql("SELECT date, team, opponent FROM matches", engine)
    return set((str(d)[:10], t, o) for d, t, o in zip(df["date"], df["team"], df["opponent"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, default=1)   # 1 = Copa do Mundo
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()

    fixtures, _ = _get("/fixtures", league=a.league, season=a.season)
    fin = [f for f in fixtures if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
    print(f"Liga {a.league}/{a.season}: {len(fixtures)} fixtures, {len(fin)} resolvidas.")

    have = existing_keys()
    new_rows = []
    fetched = no_stats = 0
    for f in fin:
        fx = f.get("fixture") or {}; tt = f.get("teams") or {}
        fid = fx.get("id"); d10 = (fx.get("date") or "")[:10]
        h = _norm((tt.get("home") or {}).get("name")); a2 = _norm((tt.get("away") or {}).get("name"))
        if not (fid and d10 and h and a2):
            continue
        key = f"{d10}|{h}|{a2}"
        d = cache_get(key)
        if d is None:
            d = fetch_full_by_id(fid)
            if d:
                cache_put(key, fid, d); fetched += 1
        if not d:
            continue
        rows = parse_match(d)
        if not rows:
            no_stats += 1; continue
        for row in rows:
            k = (str(row["date"])[:10], row["team"], row["opponent"])
            if k not in have:
                new_rows.append(row); have.add(k)

    if new_rows:
        dfn = pd.DataFrame(new_rows)
        with engine.begin() as c:
            dfn.to_sql("matches", c, if_exists="append", index=False, method="multi", chunksize=500)
    n = pd.read_sql("SELECT COUNT(*) AS n FROM matches", engine)["n"].iloc[0]
    print(f">> Novos jogos anexados a 'matches': {len(new_rows)} | API buscou {fetched} | sem stats {no_stats} "
          f"| total na base agora: {n}")


if __name__ == "__main__":
    main()
