#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_first_scorer_targets.py
======================================
Mercado novo: TIME A MARCAR PRIMEIRO. Extrai, dos eventos brutos (type=Goal,
ordenados por minuto), qual time fez o 1º gol da partida (ou "nenhum" se 0x0).
Mesmo padrão de build_clubs_halftime_targets.py, generalizado pros dois espelhos
locais (raw_cache.sqlite = seleção, club_raw_cache.sqlite = clube).

Uso: python scripts/build_first_scorer_targets.py --scope selecao
     python scripts/build_first_scorer_targets.py --scope clube
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

CONFIG = {
    "selecao": {"db": ROOT / "data" / "raw_cache.sqlite",
               "out": ROOT / "data" / "built" / "first_scorer_targets.parquet"},
    "clube": {"db": ROOT / "data" / "club_raw_cache.sqlite",
             "out": ROOT / "data" / "built" / "club_first_scorer_targets.parquet"},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    conn = sqlite3.connect(str(cfg["db"]))
    cur = conn.execute("SELECT fixture_id, raw FROM raw")
    rows = []
    n = 0
    for fid, raw in cur:
        n += 1
        if n % 50000 == 0:
            print(f"  {n}...", flush=True)
        try:
            d = json.loads(raw)
        except Exception:
            continue
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id")
        hn = (teams.get("home") or {}).get("name")
        an = (teams.get("away") or {}).get("name")
        date = ((d.get("fixture") or {}).get("date") or "")[:10]
        goals = d.get("goals") or {}
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None or hid is None:
            continue
        base = {"fixture_id": fid, "date": date, "home_team": hn, "away_team": an}
        if hg == 0 and ag == 0:
            rows.append({**base, "first_scorer": "none"})
            continue
        gevents = [e for e in (d.get("events") or [])
                  if e.get("type") == "Goal" and (e.get("detail") or "") != "Missed Penalty"]
        if not gevents:
            continue
        gevents.sort(key=lambda e: (((e.get("time") or {}).get("elapsed") or 0),
                                    ((e.get("time") or {}).get("extra") or 0)))
        first = gevents[0]
        is_home = (first.get("team") or {}).get("id") == hid
        rows.append({**base, "first_scorer": "home" if is_home else "away"})
    conn.close()

    df = pd.DataFrame(rows).drop_duplicates(subset=["fixture_id"])
    cfg["out"].parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cfg["out"], index=False)
    print(f"[{a.scope}] alvos: {len(df)} jogos -> {cfg['out']}", flush=True)
    print(df["first_scorer"].value_counts(), flush=True)


if __name__ == "__main__":
    main()
