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
OUT_PAST = ROOT / "data" / "built" / "past_fixtures.json"


def main():
    index: dict[str, str] = {}
    past: list[dict] = []
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        fx = d.get("fixture") or {}
        teams = d.get("teams") or {}
        lg = d.get("league") or {}
        th, ta = teams.get("home") or {}, teams.get("away") or {}
        date_full = fx.get("date") or ""
        date = date_full[:10]
        hn, an = th.get("name"), ta.get("name")
        # só jogos já disputados (com placar) entram na lista de passadas
        played = (d.get("goals") or {}).get("home") is not None
        if date and hn and an:
            index[f"{date}|{hn}|{an}"] = str(f.relative_to(ROOT)).replace("\\", "/")
            if played:
                past.append({
                    "fixture_id": f"{date}|{hn}|{an}",
                    "home": hn, "away": an, "date": date_full,
                    "league_name": lg.get("name"),
                })
    past.sort(key=lambda x: x["date"], reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    OUT_PAST.write_text(json.dumps(past, ensure_ascii=False), encoding="utf-8")
    print(f"Índice de fixtures (Local Fallback): {len(index)} jogos -> {OUT}")
    print(f"Partidas passadas (Local Fallback): {len(past)} -> {OUT_PAST}")

    # Salvar no Banco de Dados
    try:
        import pandas as pd
        from app.db.connection import engine, truncate_and_append
        
        if index:
            df_index = pd.DataFrame(list(index.items()), columns=["key", "path"])
            truncate_and_append(df_index, "fixture_index", engine)
            print("   Tabela 'fixture_index' salva no banco com sucesso.")
            
        if past:
            df_past = pd.DataFrame(past)
            truncate_and_append(df_past, "past_fixtures", engine)
            print("   Tabela 'past_fixtures' salva no banco com sucesso.")
            
    except Exception as e:
        print(f"[ERRO] Falha ao salvar no banco de dados: {e}")

if __name__ == "__main__":
    main()
