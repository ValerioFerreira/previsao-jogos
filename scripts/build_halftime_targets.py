#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_halftime_targets.py
=================================
Extrai dos fixtures brutos da api-football os ALVOS POR TEMPO (1º/2º), por jogo:
  - gols 1º/2º tempo (mandante/visitante) via score.halftime e goals (fulltime);
  - cartões 1º/2º tempo (mandante/visitante) contando eventos type=Card por minuto
    (time.elapsed <= 45 -> 1º tempo; senão 2º tempo).

Chaveado por (date, home_team, away_team) — a mesma chave usada pelo build_history
para casar com a base enriquecida. Salva data/built/halftime_targets.parquet.
NÃO toca produção.
"""
from __future__ import annotations
import gzip, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "raw" / "fixtures"
OUT = ROOT / "data" / "built" / "halftime_targets.parquet"


def main():
    rows = []
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        fx = d.get("fixture") or {}
        teams = d.get("teams") or {}
        score = d.get("score") or {}
        ht = score.get("halftime") or {}
        ft = d.get("goals") or {}
        hn = (teams.get("home") or {}).get("name")
        an = (teams.get("away") or {}).get("name")
        hid = (teams.get("home") or {}).get("id")
        date = (fx.get("date") or "")[:10]
        if not (hn and an and date):
            continue
        hg_ht, ag_ht = ht.get("home"), ht.get("away")
        hg_ft, ag_ft = ft.get("home"), ft.get("away")
        if hg_ht is None or hg_ft is None:
            continue  # sem placar de 1º tempo confiável -> pula

        # cartões por tempo (mandante/visitante) a partir dos eventos
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
            "date": date, "home_team": hn, "away_team": an,
            "home_goals_1t": hg_ht, "away_goals_1t": ag_ht,
            "home_goals_2t": hg_ft - hg_ht, "away_goals_2t": ag_ft - ag_ht,
            "home_cards_1t": hc1, "away_cards_1t": ac1,
            "home_cards_2t": hc2, "away_cards_2t": ac2,
            "has_card_events": int(has_cards),
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "home_team", "away_team"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT)
    print(f"Alvos por tempo: {len(df)} jogos -> {OUT}")
    print(f"  com eventos de cartão: {df['has_card_events'].sum()}")

    # cobertura contra a base enriquecida (linhas com box-score)
    csv = pd.read_csv(ROOT / "international_features_enriched_apifootball.csv", low_memory=False)
    csv["date"] = csv["date"].astype(str).str[:10]
    adv = csv[csv["has_advanced_stats"] == 1]
    merged = adv.merge(df, on=["date", "home_team", "away_team"], how="inner")
    print(f"  join com linhas has_advanced_stats={len(adv)}: {len(merged)} casadas")


if __name__ == "__main__":
    main()
