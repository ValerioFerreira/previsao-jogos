#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/build_base_squads.py
=======================================
Monta os JOGOS-ALVO (janelas pos-temporada, onde o agregado de clube da temporada
recem-encerrada e point-in-time-limpo) e o ELENCO-BASE de cada lado: jogadores dos
5 jogos ANTERIORES da selecao (sem leakage de escalacao). Tudo local/gratis a partir
do indice de fixtures crus + o CSV de producao (que tem Elo/forma/resultado).

Janelas: jun-jul de 2024, 2025, 2026. season_clube = ano-1 (temporada recem-encerrada).
Saida: player_ranking/data/interim/target_matches.parquet
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "international_features_enriched_apifootball.csv"
INTERIM = ROOT / "player_ranking" / "data" / "interim"

WINDOWS = [  # (inicio, fim, season_clube_recem_encerrada)
    ("2024-06-01", "2024-07-31", 2023),
    ("2025-06-01", "2025-07-31", 2024),
    ("2026-06-01", "2026-07-31", 2025),
]


def last5_pids(idx, team_id, before_date, min_apps=2):
    """Jogadores REGULARES: presentes em >= min_apps dos 5 ultimos jogos da selecao
    antes de before_date (remove convocados pontuais; representa a forca real)."""
    from collections import Counter
    sub = idx[((idx.home_id == team_id) | (idx.away_id == team_id)) & (idx.date < before_date)]
    sub = sub.sort_values("date").tail(5)
    cnt = Counter()
    for _, r in sub.iterrows():
        cnt.update(r["home_pids"] if r["home_id"] == team_id else r["away_pids"])
    return sorted(p for p, c in cnt.items() if c >= min_apps)


def main():
    df = pd.read_csv(CSV, parse_dates=["date"])
    idx = pd.read_parquet(INTERIM / "raw_fixture_index.parquet")
    idx["date"] = pd.to_datetime(idx["date"])

    # chave de join (date, home_name, away_name) -> team ids do raw
    idx_key = idx.dropna(subset=["home_name", "away_name"]).copy()
    idx_key["k"] = idx_key.date.dt.strftime("%Y-%m-%d") + "|" + idx_key.home_name + "|" + idx_key.away_name
    idx_key = idx_key.drop_duplicates("k", keep="first")
    key2ids = idx_key.set_index("k")[["home_id", "away_id"]].to_dict("index")

    targets = []
    for ini, fim, season in WINDOWS:
        w = df[(df.date >= ini) & (df.date <= fim)].copy()
        for _, r in w.iterrows():
            k = f"{r['date'].strftime('%Y-%m-%d')}|{r['home_team']}|{r['away_team']}"
            ids = key2ids.get(k)
            if not ids:
                continue
            hpids = last5_pids(idx, ids["home_id"], r["date"])
            apids = last5_pids(idx, ids["away_id"], r["date"])
            if len(hpids) < 8 or len(apids) < 8:   # precisa de elenco minimo nos 2 lados
                continue
            targets.append({
                "match_id": r["match_id"], "date": r["date"],
                "home_team": r["home_team"], "away_team": r["away_team"],
                "home_id": ids["home_id"], "away_id": ids["away_id"],
                "result": r["result"], "season_club": season,
                "home_pids": hpids, "away_pids": apids,
                "n_home": len(hpids), "n_away": len(apids),
            })
    t = pd.DataFrame(targets)
    INTERIM.mkdir(parents=True, exist_ok=True)
    t.to_parquet(INTERIM / "target_matches.parquet")

    all_pids = set()
    for _, r in t.iterrows():
        all_pids.update(r["home_pids"]); all_pids.update(r["away_pids"])
    # jogadores unicos por (season) — o que vamos consultar na API
    pairs = set()
    for _, r in t.iterrows():
        for p in r["home_pids"] + r["away_pids"]:
            pairs.add((p, r["season_club"]))
    print(f"jogos-alvo (com elenco-base nos 2 lados): {len(t)}")
    print(t.groupby(t.date.dt.year).size().to_string())
    print(f"elenco-base medio: home {t.n_home.mean():.0f} / away {t.n_away.mean():.0f}")
    print(f"jogadores unicos: {len(all_pids)} | pares (player,season) p/ API: {len(pairs)}")
    print(f"salvo: {INTERIM / 'target_matches.parquet'}")


if __name__ == "__main__":
    main()
