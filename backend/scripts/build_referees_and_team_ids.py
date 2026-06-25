#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_referees_and_team_ids.py
=======================================
Extrai, dos fixtures brutos da api-football (offline, sem cota):
  - lista de árbitros distintos (para autocomplete na UI);
  - mapa nome_da_seleção -> team_id (para montar a URL do logo:
    https://media.api-sports.io/football/teams/{id}.png).
Salva data/built/referees.json e data/built/team_ids.json.
"""
from __future__ import annotations
import gzip, json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "raw" / "fixtures"
OUT_REF = ROOT / "data" / "built" / "referees.json"
OUT_IDS = ROOT / "data" / "built" / "team_ids.json"


def main():
    referees = Counter()
    team_ids: dict[str, int] = {}
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        ref = (d.get("fixture") or {}).get("referee")
        if ref and isinstance(ref, str):
            # normaliza "Nome, Country" -> "Nome"
            referees[ref.split(",")[0].strip()] += 1
        for side in ("home", "away"):
            t = (d.get("teams") or {}).get(side) or {}
            if t.get("name") and t.get("id"):
                team_ids[t["name"]] = t["id"]

    ref_list = sorted([r for r, n in referees.items() if r])
    OUT_REF.parent.mkdir(parents=True, exist_ok=True)
    OUT_REF.write_text(json.dumps(ref_list, ensure_ascii=False), encoding="utf-8")
    OUT_IDS.write_text(json.dumps(team_ids, ensure_ascii=False), encoding="utf-8")
    print(f"Árbitros distintos: {len(ref_list)} -> {OUT_REF}")
    print(f"Times com id: {len(team_ids)} -> {OUT_IDS}")


if __name__ == "__main__":
    main()
