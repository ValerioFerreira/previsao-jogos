#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/collect_players.py
=====================================
PASSO 2+4 — Para cada (player_id, season) do conjunto-alvo, consulta /players?id=&season=
(via apiclient cacheado) e extrai a forma de CLUBE agregada da temporada (recem-encerrada,
logo point-in-time-limpa para as janelas pos-temporada). Salva player_club_form.parquet.

Resolucao de clube (ajuste do Passo 0): agrega por team.id somando minutos APENAS em
competicoes de CLUBE (exclui competicoes de selecao/torneio) e pega o clube de mais
minutos. Rating = media ponderada por minutos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "player_ranking" / "src"))
from apiclient import ApiClient, BudgetExhausted  # noqa: E402

INTERIM = ROOT / "player_ranking" / "data" / "interim"

# padroes de competicao de SELECAO/torneio a excluir na resolucao de clube
NAT_PATTERNS = ("world cup", "nations league", "friendl", "euro", "copa america",
                "copa américa", "africa cup", "african nations", "asian cup", "gold cup",
                "qualification", "olympic", "confederations", "club world cup",
                "uefa super cup", "conmebol")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_club_form(resp, player_id, season):
    """Do /players?id=&season=, agrega o clube de mais minutos (so comps de clube)."""
    if not resp:
        return None
    stats = resp[0].get("statistics", []) or []
    by_club = {}
    for s in stats:
        league = (s.get("league") or {})
        lname = (league.get("name") or "").lower()
        if any(p in lname for p in NAT_PATTERNS):
            continue  # ignora selecao/torneio
        team = (s.get("team") or {})
        cid = team.get("id")
        if not cid:
            continue
        g = (s.get("games") or {})
        mins = _f(g.get("minutes")) or 0.0
        rating = _f(g.get("rating"))
        sh = (s.get("shots") or {})
        go = (s.get("goals") or {})
        pa = (s.get("passes") or {})
        d = by_club.setdefault(cid, {
            "club_id": cid, "club_name": team.get("name"),
            "league_id": league.get("id"), "league_name": league.get("name"),
            "country": league.get("country"), "minutes": 0.0, "appearances": 0.0,
            "rating_w": 0.0, "rating_min": 0.0, "goals": 0.0, "assists": 0.0,
            "shots": 0.0, "shots_on": 0.0, "passes": 0.0, "key_passes": 0.0, "_topmin": -1,
        })
        d["minutes"] += mins
        d["appearances"] += _f(g.get("appearences")) or 0.0
        if rating is not None and mins > 0:
            d["rating_w"] += rating * mins
            d["rating_min"] += mins
        d["goals"] += _f(go.get("total")) or 0.0
        d["assists"] += _f(go.get("assists")) or 0.0
        d["shots"] += _f(sh.get("total")) or 0.0
        d["shots_on"] += _f(sh.get("on")) or 0.0
        d["passes"] += _f(pa.get("total")) or 0.0
        d["key_passes"] += _f(pa.get("key")) or 0.0
        if mins > d["_topmin"]:  # liga principal = a de mais minutos nesse clube
            d["_topmin"] = mins
            d["league_id"], d["league_name"], d["country"] = league.get("id"), league.get("name"), league.get("country")
    if not by_club:
        return None
    best = max(by_club.values(), key=lambda x: x["minutes"])
    rating = best["rating_w"] / best["rating_min"] if best["rating_min"] > 0 else None
    return {
        "player_id": player_id, "season": season,
        "club_id": best["club_id"], "club_name": best["club_name"],
        "league_id": best["league_id"], "league_name": best["league_name"], "country": best["country"],
        "minutes": best["minutes"], "appearances": best["appearances"], "rating": rating,
        "goals": best["goals"], "assists": best["assists"], "shots": best["shots"],
        "shots_on": best["shots_on"], "passes": best["passes"], "key_passes": best["key_passes"],
    }


def fetch_pairs(pairs, api, progress_every=500):
    rows, miss = [], 0
    for i, (pid, season) in enumerate(pairs, 1):
        try:
            resp = api.get("/players", f"players_profile/{season}/{pid}", id=pid, season=season)
        except BudgetExhausted:
            print(f"[BUDGET] parou em {i}/{len(pairs)}")
            break
        rec = parse_club_form(resp, pid, season)
        if rec:
            rows.append(rec)
        else:
            miss += 1
        if i % progress_every == 0:
            print(f"  {i}/{len(pairs)} | hits {len(rows)} miss {miss} | live {api.n_live} cache {api.n_cache} | rest {api.remaining}")
    return rows, miss


def all_pairs():
    t = pd.read_parquet(INTERIM / "target_matches.parquet")
    pairs = set()
    for _, r in t.iterrows():
        for p in list(r["home_pids"]) + list(r["away_pids"]):
            pairs.add((int(p), int(r["season_club"])))
    return sorted(pairs)


def main():
    pairs = all_pairs()
    print(f"pares (player,season) a coletar: {len(pairs)}")
    api = ApiClient(max_requests=60000, per_minute=450)
    rows, miss = fetch_pairs(pairs, api)
    df = pd.DataFrame(rows)
    df.to_parquet(INTERIM / "player_club_form.parquet")
    print(f"\nforma de clube extraida: {len(df)} jogadores | sem clube: {miss}")
    print(f"requests: {api.stats()}")
    print(f"salvo: {INTERIM / 'player_club_form.parquet'}")


if __name__ == "__main__":
    main()
