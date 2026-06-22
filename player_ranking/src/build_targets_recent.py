#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/build_targets_recent.py
===========================================
Jogos-alvo para a hipótese de FORMA RECENTE POR JOGO (ortogonal ao Elo) — versão
ampla: TODAS as janelas internacionais de 2023-08 em diante (inclui meio de
temporada de clube, onde forma recente diverge do agregado-de-temporada que falhou).

Elenco-base leakage-safe = regulares dos 5 jogos internacionais ANTERIORES da seleção
(não usa a escalação do jogo atual). O clube/temporada de cada jogador é resolvido
DEPOIS, no coletor, a partir da data do jogo (não aqui).

Saída: player_ranking/data/interim/target_matches_recent.parquet
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "international_features_enriched_apifootball.csv"
INTERIM = ROOT / "player_ranking" / "data" / "interim"
DATE_FROM, DATE_TO = "2023-08-01", "2026-06-30"


def last5_pids(idx, team_id, before_date, min_apps=2):
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
    idx_key = idx.dropna(subset=["home_name", "away_name"]).copy()
    idx_key["k"] = idx_key.date.dt.strftime("%Y-%m-%d") + "|" + idx_key.home_name + "|" + idx_key.away_name
    idx_key = idx_key.drop_duplicates("k", keep="first")
    key2ids = idx_key.set_index("k")[["home_id", "away_id"]].to_dict("index")

    w = df[(df.date >= DATE_FROM) & (df.date <= DATE_TO)].copy()
    targets = []
    for _, r in w.iterrows():
        k = f"{r['date'].strftime('%Y-%m-%d')}|{r['home_team']}|{r['away_team']}"
        ids = key2ids.get(k)
        if not ids:
            continue
        hpids = last5_pids(idx, ids["home_id"], r["date"])
        apids = last5_pids(idx, ids["away_id"], r["date"])
        if len(hpids) < 8 or len(apids) < 8:
            continue
        targets.append({
            "match_id": r["match_id"], "date": r["date"],
            "home_team": r["home_team"], "away_team": r["away_team"],
            "home_id": ids["home_id"], "away_id": ids["away_id"],
            "result": r["result"], "home_pids": hpids, "away_pids": apids,
            "n_home": len(hpids), "n_away": len(apids),
        })
    t = pd.DataFrame(targets)
    INTERIM.mkdir(parents=True, exist_ok=True)
    t.to_parquet(INTERIM / "target_matches_recent.parquet")

    pairs = set()
    for _, r in t.iterrows():
        for p in r["home_pids"] + r["away_pids"]:
            pairs.add((p, r["date"].year, r["date"].month))
    uniq_players = set()
    for _, r in t.iterrows():
        uniq_players.update(r["home_pids"]); uniq_players.update(r["away_pids"])
    print(f"jogos-alvo (2023-08+): {len(t)}")
    print(t.groupby([t.date.dt.year, t.date.dt.month]).size().to_string())
    print(f"jogadores unicos: {len(uniq_players)} | pares (player,jogo) ~ {sum(len(r['home_pids'])+len(r['away_pids']) for _,r in t.iterrows())}")
    print(f"salvo: {INTERIM / 'target_matches_recent.parquet'}")


if __name__ == "__main__":
    main()
