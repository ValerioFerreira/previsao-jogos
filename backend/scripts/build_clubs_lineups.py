#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_clubs_lineups.py
================================
Extrai só o bloco `lineups` (startXI) do espelho local de clubes — necessário para
a feature de rotação de elenco (Fase 5.4). Separado do parse principal
(build_clubs_dataset.py) porque é uma passada extra sobre os 54k JSONs; roda uma
vez e cacheia em data/built/club_lineups.parquet.

Saída: fixture_id, team (Nome#id), player_ids (string "id1,id2,...", 11 titulares
ordenados), formation.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MIRROR = ROOT / "data" / "club_raw_cache.sqlite"
OUT = ROOT / "data" / "built" / "club_lineups.parquet"
FINISHED = {"FT", "AET", "PEN"}


def team_key(t):
    return f"{(t.get('name') or '').strip()}#{t.get('id')}"


def main():
    conn = sqlite3.connect(f"file:{MIRROR}?mode=ro", uri=True, timeout=60)
    n_total = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    rows = []
    cur = conn.execute("SELECT raw FROM raw")
    i = 0
    for (raw,) in cur:
        i += 1
        if i % 10000 == 0:
            print(f"  {i}/{n_total}...", flush=True)
        d = json.loads(raw)
        fx = d.get("fixture") or {}
        if ((fx.get("status") or {}).get("short")) not in FINISHED:
            continue
        fid = fx.get("id")
        for lu in d.get("lineups") or []:
            team = team_key(lu.get("team") or {})
            ids = sorted(p["player"]["id"] for p in lu.get("startXI") or []
                        if p.get("player", {}).get("id"))
            if not ids:
                continue
            rows.append({"fixture_id": fid, "team": team,
                        "player_ids": ",".join(map(str, ids)),
                        "formation": lu.get("formation")})
    conn.close()
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"salvo {OUT}: {len(df)} escalações ({df['fixture_id'].nunique()} jogos)")


if __name__ == "__main__":
    main()
