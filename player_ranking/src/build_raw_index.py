#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/build_raw_index.py
=====================================
Indexa TODOS os fixtures crus locais (data/raw/fixtures) extraindo, de cada jogo,
os ids dos jogadores que atuaram (startXI + substitutes do bloco lineups). Base
para montar o "elenco-base" de cada selecao a partir dos jogos ANTERIORES — local,
gratis, sem leakage de escalacao. Salva Parquet em player_ranking/data/interim/.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "raw" / "fixtures"
OUT = ROOT / "player_ranking" / "data" / "interim"


def player_ids_from_lineup(block):
    ids = []
    for grp in ("startXI", "substitutes"):
        for e in block.get(grp, []) or []:
            pid = (e.get("player") or {}).get("id")
            if pid:
                ids.append(pid)
    return ids


def main():
    rows = []
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        fx = d.get("fixture", {})
        teams = d.get("teams", {})
        date = (fx.get("date") or "")[:10]
        hid = (teams.get("home") or {}).get("id")
        aid = (teams.get("away") or {}).get("id")
        if not (date and hid and aid):
            continue
        lineups = {(b.get("team") or {}).get("id"): player_ids_from_lineup(b) for b in (d.get("lineups") or [])}
        rows.append({
            "fixture_id": fx.get("id"),
            "date": date,
            "home_id": hid, "home_name": (teams.get("home") or {}).get("name"),
            "away_id": aid, "away_name": (teams.get("away") or {}).get("name"),
            "home_pids": lineups.get(hid, []),
            "away_pids": lineups.get(aid, []),
            "league_id": (d.get("league") or {}).get("id"),
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "raw_fixture_index.parquet")
    have_lu = df[df["home_pids"].str.len() > 0]
    print(f"fixtures indexados: {len(df)} | com escalacao: {len(have_lu)} "
          f"| datas: {df.date.min().date()} -> {df.date.max().date()}")
    print(f"salvo: {OUT / 'raw_fixture_index.parquet'}")


if __name__ == "__main__":
    main()
