#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Precache: baixa o detalhe das ÚLTIMAS 5 partidas de cada seleção da Copa do
Mundo deste ano e grava no cache do Neon (match_detail_cache), para a página
Estatísticas já abrir instantâneo (sem cota) no Render."""
import sys
sys.path.insert(0, ".")
from app.services.fixture_fetch import _get, recent_fixture_ids, fetch_full_by_id, cache_get, cache_put
from app.services.predictor_service import _norm

WC_LEAGUE, SEASON = 1, 2026


def main():
    fixtures, _ = _get("/fixtures", league=WC_LEAGUE, season=SEASON)
    teams = {}
    for f in fixtures:
        for side in ("home", "away"):
            t = (f.get("teams") or {}).get(side) or {}
            if t.get("id"):
                teams[t["id"]] = t.get("name")
    print(f"Seleções da Copa {SEASON}: {len(teams)} | precache das últimas 5 de cada...")

    novos = jacache = falhas = 0
    for tid, name in teams.items():
        try:
            recents = recent_fixture_ids(tid, last=5)
        except Exception as e:
            print(f"  [AVISO] {name}: {e}"); falhas += 1; continue
        for f in recents:
            fx = f.get("fixture") or {}; tt = f.get("teams") or {}
            fid = fx.get("id"); d10 = (fx.get("date") or "")[:10]
            h = _norm((tt.get("home") or {}).get("name")); a = _norm((tt.get("away") or {}).get("name"))
            if not (fid and d10 and h and a):
                continue
            key = f"{d10}|{h}|{a}"
            if cache_get(key) is not None:
                jacache += 1; continue
            d = fetch_full_by_id(fid)
            if d:
                cache_put(key, fid, d); novos += 1
            else:
                falhas += 1
    print(f"Concluído: {novos} novos no cache | {jacache} já estavam | {falhas} falhas.")


if __name__ == "__main__":
    main()
