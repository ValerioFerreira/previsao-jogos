#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/fetch_odds.py
=====================
Coletor de odds pré-jogo da api-football (/odds) para os mercados que o nosso
modelo prevê. Mapeia os bet ids relevantes e extrai/armazena as odds por fixture.

LIMITAÇÃO DA API (documentada): odds só de 1-14 dias antes do jogo, 7 dias de
histórico. => coleta apenas FUTURO; não há backtest histórico de value. Para
acumular histórico, rodar periodicamente (recomendado: 1x a cada 3h) e guardar.

Chave: APIFOOTBALL_KEY (variável de ambiente ou .env). Nunca commitada.

Uso:
  python scripts/fetch_odds.py --fixture 123456      # odds de um jogo
  python scripts/fetch_odds.py --league 1 --season 2026   # odds de uma competição
"""
import os
import sys
import json
import argparse
import time
from pathlib import Path

import requests

BASE = "https://v3.football.api-sports.io"
OUT_DIR = Path("data/odds")

# bet id (api-football) -> nome do nosso mercado
BET_MAP = {
    1:  "resultado",            # Match Winner (Home/Draw/Away)
    5:  "gols_over_under",      # Goals Over/Under (varias linhas)
    8:  "btts",                 # Both Teams Score
    45: "escanteios_total",     # Corners Over Under
    57: "escanteios_mandante",  # Home Corners Over/Under
    58: "escanteios_visitante", # Away Corners Over/Under
    80: "cartoes_total",        # Cards Over/Under
    82: "cartoes_mandante",     # Home Team Total Cards
    83: "cartoes_visitante",    # Away Team Total Cards
}


def load_key():
    key = os.environ.get("APIFOOTBALL_KEY")
    if not key and Path(".env").exists():
        for line in Path(".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("APIFOOTBALL_KEY"):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("APIFOOTBALL_KEY ausente (env ou .env).")
    return key


def api_get(path, key, **params):
    r = requests.get(BASE + path, headers={"x-apisports-key": key}, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_fixture_odds(item):
    """Extrai, dos bookmakers, as odds dos mercados em BET_MAP. Faz a mediana entre
    casas por (mercado, aposta) para um valor de consenso robusto."""
    from statistics import median
    agg = {}  # market -> outcome/linha -> [odds]
    for bm in item.get("bookmakers", []):
        for bet in bm.get("bets", []):
            mkt = BET_MAP.get(bet.get("id"))
            if not mkt:
                continue
            for v in bet.get("values", []):
                outcome = str(v.get("value"))
                try:
                    odd = float(v.get("odd"))
                except (TypeError, ValueError):
                    continue
                agg.setdefault(mkt, {}).setdefault(outcome, []).append(odd)
    # consenso = mediana entre casas
    return {mkt: {out: round(median(odds), 2) for out, odds in outs.items()}
            for mkt, outs in agg.items()}


def fetch_fixture(fixture_id, key, store=True):
    j = api_get("/odds", key, fixture=fixture_id)
    resp = j.get("response", [])
    if not resp:
        return None
    parsed = parse_fixture_odds(resp[0])
    parsed["_fixture"] = fixture_id
    if store and parsed:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{fixture_id}.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    return parsed


def fetch_competition(league, season, key):
    """Paginacao: coleta odds de todos os jogos de uma competicao que tenham odds."""
    page, total, saved = 1, 1, 0
    while page <= total:
        j = api_get("/odds", key, league=league, season=season, page=page)
        total = j.get("paging", {}).get("total", 1)
        for item in j.get("response", []):
            fx = item.get("fixture", {}).get("id")
            parsed = parse_fixture_odds(item)
            if parsed and fx:
                parsed["_fixture"] = fx
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUT_DIR / f"{fx}.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                saved += 1
        page += 1
        time.sleep(0.3)  # freio gentil
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=int)
    ap.add_argument("--league", type=int)
    ap.add_argument("--season", type=int)
    a = ap.parse_args()
    key = load_key()
    if a.fixture:
        p = fetch_fixture(a.fixture, key)
        print(json.dumps(p, ensure_ascii=False, indent=2) if p else "Sem odds para esse fixture.")
    elif a.league and a.season:
        n = fetch_competition(a.league, a.season, key)
        print(f"Odds salvas para {n} jogos em data/odds/")
    else:
        ap.error("informe --fixture ou (--league e --season)")


if __name__ == "__main__":
    main()
