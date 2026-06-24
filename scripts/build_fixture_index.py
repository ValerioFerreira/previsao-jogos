#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_fixture_index.py
==============================
Índice dos fixtures brutos para lookup rápido na página de detalhe de partida
(sem cota: lê o cache local data/raw/fixtures). Mapeia:
  "YYYY-MM-DD|Home|Away" -> caminho relativo do .json.gz
Salva data/built/fixture_index.json.
"""
from __future__ import annotations
import gzip, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "raw" / "fixtures"
OUT = ROOT / "data" / "built" / "fixture_index.json"


def main():
    index: dict[str, str] = {}
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        fx = d.get("fixture") or {}
        teams = d.get("teams") or {}
        date = (fx.get("date") or "")[:10]
        hn = (teams.get("home") or {}).get("name")
        an = (teams.get("away") or {}).get("name")
        if date and hn and an:
            index[f"{date}|{hn}|{an}"] = str(f.relative_to(ROOT)).replace("\\", "/")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"Índice de fixtures: {len(index)} jogos -> {OUT}")


if __name__ == "__main__":
    main()
