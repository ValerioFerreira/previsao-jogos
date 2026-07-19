#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_clubs_halftime_targets.py
========================================
Equivalente a build_halftime_targets.py, mas pra CLUBES: extrai alvos por tempo
(1º/2º -- gols e cartões) do espelho local `data/club_raw_cache.sqlite` (raw JSON
por fixture_id, tabela `raw` -- ver prefetch_clubs.py), keyed por fixture_id (não
por nome+data -- club_features_enriched.parquet já tem fixture_id direto, evita
ambiguidade de nome#id). 100% local, sem chamada de API/Neon.

Uso: python scripts/build_clubs_halftime_targets.py
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "club_raw_cache.sqlite"
OUT = ROOT / "data" / "built" / "club_halftime_targets.parquet"


def main():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT fixture_id, raw FROM raw")
    rows = []
    n = 0
    for r in cur:
        n += 1
        if n % 50000 == 0:
            print(f"  {n}...", flush=True)
        try:
            d = json.loads(r["raw"])
        except Exception:
            continue
        fx = d.get("fixture") or {}
        teams = d.get("teams") or {}
        score = d.get("score") or {}
        ht = score.get("halftime") or {}
        ft = d.get("goals") or {}
        hid = (teams.get("home") or {}).get("id")
        hg_ht, ag_ht = ht.get("home"), ht.get("away")
        hg_ft, ag_ft = ft.get("home"), ft.get("away")
        if hg_ht is None or hg_ft is None or hid is None:
            continue

        hc1 = hc2 = ac1 = ac2 = 0
        has_cards = False
        for e in (d.get("events") or []):
            if e.get("type") != "Card":
                continue
            has_cards = True
            el = ((e.get("time") or {}).get("elapsed") or 0)
            is_home = ((e.get("team") or {}).get("id") == hid)
            first = el <= 45
            if is_home:
                hc1 += first; hc2 += (not first)
            else:
                ac1 += first; ac2 += (not first)

        rows.append({
            "fixture_id": r["fixture_id"],
            "home_goals_1t": hg_ht, "away_goals_1t": ag_ht,
            "home_goals_2t": hg_ft - hg_ht, "away_goals_2t": ag_ft - ag_ht,
            "home_cards_1t": hc1, "away_cards_1t": ac1,
            "home_cards_2t": hc2, "away_cards_2t": ac2,
            "has_card_events": int(has_cards),
        })
    conn.close()

    df = pd.DataFrame(rows).drop_duplicates(subset=["fixture_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"Alvos por tempo (clubes): {len(df)} jogos -> {OUT}")
    print(f"  com eventos de cartao: {df['has_card_events'].sum()}")


if __name__ == "__main__":
    main()
