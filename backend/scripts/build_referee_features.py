#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/build_referee_features.py
=========================================
Deriva features de ÁRBITRO por jogo (offline, dos fixtures brutos) para o mercado de
cartões — o dado que faltava. Para cada jogo extrai o árbitro e o total de cartões
(amarelos+vermelhos das estatísticas). Calcula, leakage-safe, a SEVERIDADE do árbitro
= média de cartões totais nos jogos ANTERIORES daquele árbitro (expanding, shift(1)).
Saída: backend/data/built/referee_features.csv (date, home_team, away_team,
ref_strictness, ref_nmatches).
"""
import gzip, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "data" / "raw" / "fixtures"
OUT = ROOT / "data" / "built" / "referee_features.csv"


def total_cards(d):
    tot = 0; got = False
    for team in (d.get("statistics") or []):
        for s in (team.get("statistics") or []):
            t = str(s.get("type", ""))
            if t in ("Yellow Cards", "Red Cards") and s.get("value") not in (None, ""):
                try:
                    tot += int(s["value"]); got = True
                except (TypeError, ValueError):
                    pass
    return tot if got else None


def main():
    rows = []
    for f in FIX.glob("*/*/*.json.gz"):
        try:
            d = json.load(gzip.open(f))
        except Exception:
            continue
        fx = d.get("fixture") or {}
        teams = d.get("teams") or {}
        ref = fx.get("referee")
        date = (fx.get("date") or "")[:10]
        hn = (teams.get("home") or {}).get("name")
        an = (teams.get("away") or {}).get("name")
        if not (ref and date and hn and an):
            continue
        rows.append({"date": date, "home_team": hn, "away_team": an,
                     "referee": ref.split(",")[0].strip(), "tot_cards": total_cards(d)})
    df = pd.DataFrame(rows).dropna(subset=["referee"]).sort_values("date").reset_index(drop=True)
    # severidade leakage-safe: média expanding dos cartões totais do árbitro ANTES do jogo
    df["ref_strictness"] = (df.groupby("referee")["tot_cards"]
                            .apply(lambda s: s.shift(1).expanding().mean()).reset_index(level=0, drop=True))
    df["ref_nmatches"] = df.groupby("referee").cumcount()
    out = df[["date", "home_team", "away_team", "ref_strictness", "ref_nmatches"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"referee_features: {len(out)} jogos | com severidade: {out['ref_strictness'].notna().sum()} -> {OUT}")
    print(f"  árbitros distintos: {df['referee'].nunique()} | severidade média global: {df['tot_cards'].mean():.2f}")


if __name__ == "__main__":
    main()
