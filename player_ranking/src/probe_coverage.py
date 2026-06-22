#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/probe_coverage.py
====================================
PASSO 0 — Sonda de cobertura (~150-220 requests). Decide se a frente de
Player-Level Power Ranking e viavel ANTES de gastar a cota grande.

Para uma amostra de selecoes do espectro inteiro (top -> minnow), mede se o
endpoint /fixtures/players tem dados utilizaveis (minutos/rating) nos CLUBES onde
os atletas dessas selecoes atuam. Se a cobertura morre nos minnows, a base
enriquecida nasce enviesada para os times fortes — e o teste fica confundido.

Isolado: le APIFOOTBALL_KEY do .env da raiz, escreve so em player_ranking/data/probe/.
Nao toca producao. Rodar com a venv existente (tem requests):
  api/.venv/Scripts/python.exe player_ranking/src/probe_coverage.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]            # raiz do repo
OUT = ROOT / "player_ranking" / "data" / "probe"
BASE = "https://v3.football.api-sports.io"
SEASONS_TRY = [2025, 2024]                            # temporada de clube atual / anterior
MAX_REQUESTS = 240                                    # trava dura de seguranca
PLAYERS_PER_TEAM = 6                                  # amostra de jogadores-base por selecao
CLUB_GAMES_CHECK = 2                                  # quantos jogos de clube checar por jogador

# amostra do espectro: (nome, tier)
SAMPLE = [
    ("France", "top (UEFA)"),
    ("Japan", "media (AFC, mix Europa/J-League)"),
    ("Egypt", "media (CAF)"),
    ("Curacao", "minnow (CONCACAF)"),
    ("Cape Verde Islands", "minnow (CAF)"),
]


class Api:
    def __init__(self, key):
        self.key = key
        self.n = 0
        self.remaining = None

    def get(self, path, **params):
        if self.n >= MAX_REQUESTS:
            raise SystemExit(f"Trava de seguranca: {MAX_REQUESTS} requests atingidos.")
        r = requests.get(BASE + path, headers={"x-apisports-key": self.key}, params=params, timeout=30)
        self.n += 1
        self.remaining = r.headers.get("x-ratelimit-requests-remaining")
        r.raise_for_status()
        time.sleep(0.3)
        return r.json().get("response", [])


def load_key():
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("APIFOOTBALL_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("APIFOOTBALL_KEY ausente no .env da raiz.")


def resolve_national_team(api, name):
    for item in api.get("/teams", search=name):
        t = item.get("team", {})
        if t.get("national") and name.lower() in (t.get("name", "").lower()):
            return t.get("id"), t.get("name")
    # fallback: primeiro nacional
    for item in api.get("/teams", search=name):
        if item.get("team", {}).get("national"):
            return item["team"]["id"], item["team"]["name"]
    return None, None


def base_squad(api, team_id):
    """IDs dos jogadores dos ultimos 5 jogos da selecao (titulares + subs).
    FILTRA pelo bloco da PROPRIA selecao (team.id == team_id) — /fixtures/players
    devolve os DOIS times, e queremos so o nosso lado."""
    fixtures = api.get("/fixtures", team=team_id, last=5)
    pids = {}
    for fx in fixtures:
        fid = fx.get("fixture", {}).get("id")
        if not fid:
            continue
        for block in api.get("/fixtures/players", fixture=fid):
            if (block.get("team", {}) or {}).get("id") != team_id:
                continue  # ignora o adversario
            for p in block.get("players", []):
                pl = p.get("player", {})
                if pl.get("id"):
                    pids[pl["id"]] = pl.get("name")
    return pids


def current_club(api, player_id):
    """Clube de maior minutagem na temporada (current club) + league."""
    for season in SEASONS_TRY:
        resp = api.get("/players", id=player_id, season=season)
        if not resp:
            continue
        stats = resp[0].get("statistics", [])
        best = None
        for s in stats:
            mins = (s.get("games", {}) or {}).get("minutes") or 0
            league = s.get("league", {}) or {}
            # ignora competicoes de selecao; queremos clube
            if league.get("name", "").lower() in ("world cup", "uefa nations league", "friendlies"):
                continue
            if best is None or mins > best[0]:
                best = (mins, s.get("team", {}).get("id"), s.get("team", {}).get("name"),
                        league.get("id"), league.get("name"), season)
        if best:
            return best[1], best[2], best[3], best[4], best[5]
    return None, None, None, None, None


def club_has_player_stats(api, club_id):
    """Checa se os jogos recentes do clube tem /fixtures/players com minutos/rating."""
    fixtures = api.get("/fixtures", team=club_id, last=CLUB_GAMES_CHECK)
    for fx in fixtures:
        fid = fx.get("fixture", {}).get("id")
        if not fid:
            continue
        blocks = api.get("/fixtures/players", fixture=fid)
        for block in blocks:
            for p in block.get("players", []):
                st = (p.get("statistics") or [{}])[0]
                mins = (st.get("games", {}) or {}).get("minutes")
                rating = (st.get("games", {}) or {}).get("rating")
                if mins is not None or rating is not None:
                    return True
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    api = Api(load_key())
    report = []
    print(f"{'SELECAO':<22} {'tier':<32} {'jogadores':>9} {'clubes c/ stats':>16}")
    print("-" * 84)
    for name, tier in SAMPLE:
        tid, tname = resolve_national_team(api, name)
        if not tid:
            print(f"{name:<22} {tier:<32} {'NAO ACHOU':>9}")
            report.append({"selecao": name, "tier": tier, "erro": "team_id nao resolvido"})
            continue
        squad = base_squad(api, tid)
        sample = list(squad.items())[:PLAYERS_PER_TEAM]
        rows = []
        ok = 0
        for pid, pname in sample:
            club_id, club_name, lg_id, lg_name, season = current_club(api, pid)
            has = club_has_player_stats(api, club_id) if club_id else False
            ok += int(has)
            rows.append({"player": pname, "club": club_name, "league": lg_name,
                         "league_id": lg_id, "season": season, "fixture_players_ok": has})
        frac = f"{ok}/{len(sample)}" if sample else "0/0"
        print(f"{tname:<22} {tier:<32} {len(squad):>9} {frac:>16}")
        report.append({"selecao": tname, "team_id": tid, "tier": tier,
                       "n_squad": len(squad), "amostra": rows, "clubes_ok": frac})

    (OUT / "coverage_report.json").write_text(
        json.dumps({"requests_usados": api.n, "cota_restante": api.remaining, "selecoes": report},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print("-" * 84)
    print(f"requests usados: {api.n} | cota restante: {api.remaining}")
    print(f"relatorio: {OUT / 'coverage_report.json'}")
    print("\nLeitura: se os minnows tem 'clubes c/ stats' baixo, a base enriquecida nasce "
          "enviesada para times fortes -> a frente precisa de fallback p/ Elo nesses casos.")


if __name__ == "__main__":
    main()
