#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audita a cobertura de xG (expected_goals) nos fixtures brutos da api-football,
por temporada. xG so existe 2023+ — esta varredura quantifica o quanto da pra usar."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "raw" / "fixtures"


def main():
    seasons = defaultdict(lambda: [0, 0])  # season -> [com_stats, com_xg]
    xg_types = set()
    files = list(FIX.glob("*/*/*.json.gz"))
    print("total arquivos:", len(files))
    for f in files:
        season = f.parent.name
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        st = d.get("statistics") or []
        has_stats = any(t.get("statistics") for t in st)
        has_xg = False
        for t in st:
            for s in (t.get("statistics") or []):
                ty = str(s.get("type", ""))
                if "xpected" in ty:
                    xg_types.add(ty)
                    if s.get("value") not in (None, ""):
                        has_xg = True
        if has_stats:
            seasons[season][0] += 1
        if has_xg:
            seasons[season][1] += 1

    print("tipos xG:", xg_types)
    print(f"{'season':>8} {'com_stats':>10} {'com_xG':>8}")
    for s in sorted(seasons):
        a, b = seasons[s]
        print(f"{s:>8} {a:>10} {b:>8}")
    print("TOTAL com xG:", sum(v[1] for v in seasons.values()))
    print("TOTAL com stats:", sum(v[0] for v in seasons.values()))


if __name__ == "__main__":
    main()
