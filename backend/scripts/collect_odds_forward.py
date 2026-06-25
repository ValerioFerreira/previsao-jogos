#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/collect_odds_forward.py
===============================
Coletor FORWARD de odds pré-jogo + snapshot da previsão do modelo, para acumular o
histórico próprio que destrava o Passo 4 (validação de value vs mercado).

Por que existe (limitação registrada da api-football /odds): odds só ficam
disponíveis 1-14 dias antes do jogo e há só 7 dias de histórico. Não dá para
backtestar value retroativamente; é preciso coletar os jogos FUTUROS e guardar.
Cada execução:
  1. enumera jogos de SELEÇÕES dos próximos N dias (via /fixtures?date=, filtrado
     pelas ligas-alvo que o modelo conhece — os diretórios de data/raw/fixtures);
  2. para cada jogo ainda não iniciado, coleta as odds de consenso (mediana entre
     casas, reaproveitando parse_fixture_odds de fetch_odds.py);
  3. snapshota a PREVISÃO do modelo no momento (probabilidades pré-jogo) — isso
     captura a "opinião do modelo" sem precisar reconstruir features históricas
     depois;
  4. anexa um snapshot com timestamp em data/odds/snapshots/<fixture>.jsonl (série
     temporal: guarda a evolução da linha; o último antes do kickoff ~ linha de
     fechamento) e atualiza data/odds/registry.json.

O snapshot da previsão omite as PMFs (`distribuicao`) para não inchar o arquivo —
as linhas O/U (prob por linha) e os mercados principais bastam para o value.

Chave: APIFOOTBALL_KEY (variável de ambiente ou .env). Nunca commitada.

Uso:
  python scripts/collect_odds_forward.py                 # próximos 10 dias
  python scripts/collect_odds_forward.py --days 14
  python scripts/collect_odds_forward.py --dry-run       # não grava, só mostra
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

from scripts.fetch_odds import BASE, BET_MAP, load_key, parse_fixture_odds  # noqa: E402

FIXTURES_DIR = ROOT / "data" / "raw" / "fixtures"
ODDS_DIR = ROOT / "data" / "odds"
SNAP_DIR = ODDS_DIR / "snapshots"
REGISTRY = ODDS_DIR / "registry.json"

# api-football league.name -> chave de tournament_weights do nosso modelo.
def map_tournament(name: str) -> str:
    n = (name or "").lower()
    if "friendl" in n:
        return "Amistoso"
    if "nations league" in n:
        return "Liga das Nacoes"
    if "world cup" in n and "qualif" in n:
        return "Eliminatorias"
    if "world cup" in n:
        return "Copa do Mundo"
    if any(k in n for k in ("euro", "copa america", "copa américa", "africa cup", "asian cup", "gold cup")):
        return "Copa America / Euro / Copa Africana"
    if "qualif" in n:
        return "Eliminatorias"
    return "Amistoso"


# Torneios finais sao disputados em pais-sede -> a maioria joga em campo neutro.
NEUTRAL_TOURNAMENTS = {"Copa do Mundo", "Copa America / Euro / Copa Africana"}


def target_league_ids() -> set[int]:
    """Ligas-alvo = as que o modelo conhece (diretorios ja coletados)."""
    if not FIXTURES_DIR.exists():
        return set()
    out = set()
    for child in FIXTURES_DIR.iterdir():
        if child.is_dir() and child.name.isdigit():
            out.add(int(child.name))
    return out


def api_get(path: str, key: str, **params):
    r = requests.get(BASE + path, headers={"x-apisports-key": key}, params=params, timeout=30)
    r.raise_for_status()
    remaining = r.headers.get("x-ratelimit-requests-remaining")
    return r.json(), remaining


def get_predictor():
    """Carrega o Predictor de producao (mesmos artefatos da API)."""
    from predictor import Predictor

    return Predictor(art_dir=str(ROOT / "api" / "model_artifacts"))


def model_snapshot(predictor, home: str, away: str, tournament: str, neutral: bool):
    """Previsao compacta (sem PMFs) ou None se algo impedir (time fora do modelo)."""
    try:
        if home not in predictor.teams() or away not in predictor.teams():
            return None
        if tournament not in predictor.meta["tournament_weights"]:
            tournament = "Amistoso"
        raw = predictor.predict(home, away, neutral=neutral, tournament=tournament)
    except Exception as exc:  # pragma: no cover - robustez de coleta
        return {"_erro": f"{type(exc).__name__}: {exc}"}
    # remove as PMFs pesadas, preserva estimativa/intervalo/linhas
    for market in ("chutes", "escanteios", "cartoes"):
        block = raw.get(market)
        if isinstance(block, dict) and "distribuicao" in block:
            block.pop("distribuicao", None)
        elif isinstance(block, dict):
            for sub in block.values():
                if isinstance(sub, dict):
                    sub.pop("distribuicao", None)
    raw.pop("odds", None)  # o bloco de odds-justas e derivavel; nao precisa guardar
    return raw


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def collect(days: int, dry_run: bool) -> dict:
    key = load_key()
    targets = target_league_ids()
    if not targets:
        raise SystemExit("Nenhuma liga-alvo encontrada em data/raw/fixtures/.")
    predictor = None if dry_run else get_predictor()
    if dry_run:
        try:
            predictor = get_predictor()
        except Exception:
            predictor = None

    registry = load_registry()
    today = datetime.now(timezone.utc).date()
    seen_fixtures = []
    odds_collected = 0
    remaining = None

    for offset in range(days):
        day = (today + timedelta(days=offset)).isoformat()
        data, remaining = api_get("/fixtures", key, date=day)
        for item in data.get("response", []):
            league = item.get("league", {})
            if league.get("id") not in targets:
                continue
            fx = item.get("fixture", {})
            status = fx.get("status", {}).get("short")
            if status not in ("NS", "TBD"):  # só jogos ainda não iniciados
                continue
            fixture_id = fx.get("id")
            teams = item.get("teams", {})
            home = teams.get("home", {}).get("name")
            away = teams.get("away", {}).get("name")
            tournament = map_tournament(league.get("name"))
            neutral = tournament in NEUTRAL_TOURNAMENTS
            seen_fixtures.append((fixture_id, home, away, league.get("name"), fx.get("date")))

            odds_json, remaining = api_get("/odds", key, fixture=fixture_id)
            resp = odds_json.get("response", [])
            odds = parse_fixture_odds(resp[0]) if resp else {}
            if not odds:
                time.sleep(0.25)
                continue

            pred = model_snapshot(predictor, home, away, tournament, neutral) if predictor else None
            snapshot = {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "fixture_date": fx.get("date"),
                "status": status,
                "home": home,
                "away": away,
                "league_id": league.get("id"),
                "league_name": league.get("name"),
                "tournament": tournament,
                "neutral": neutral,
                "odds": odds,
                "model": pred,
            }
            odds_collected += 1
            if not dry_run:
                SNAP_DIR.mkdir(parents=True, exist_ok=True)
                with (SNAP_DIR / f"{fixture_id}.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
                registry[str(fixture_id)] = {
                    "home": home,
                    "away": away,
                    "league_id": league.get("id"),
                    "league_name": league.get("name"),
                    "tournament": tournament,
                    "neutral": neutral,
                    "fixture_date": fx.get("date"),
                    "last_collected": snapshot["collected_at"],
                    "n_snapshots": registry.get(str(fixture_id), {}).get("n_snapshots", 0) + 1,
                }
            time.sleep(0.25)  # freio gentil

    if not dry_run and seen_fixtures:
        ODDS_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "dias": days,
        "jogos_vistos": len(seen_fixtures),
        "odds_coletadas": odds_collected,
        "fixtures": seen_fixtures,
        "cota_restante": remaining,
        "dry_run": dry_run,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10, help="janela de dias a frente (padrao 10)")
    ap.add_argument("--dry-run", action="store_true", help="nao grava; so lista e conta")
    a = ap.parse_args()
    summary = collect(a.days, a.dry_run)
    print(f"\nJanela: {summary['dias']} dias | jogos de selecoes vistos: {summary['jogos_vistos']} "
          f"| com odds: {summary['odds_coletadas']} | cota restante: {summary['cota_restante']}")
    for fid, home, away, lg, date in summary["fixtures"][:40]:
        print(f"  {date}  {home} x {away}  [{lg}]  (fixture {fid})")
    if summary["dry_run"]:
        print("\n(dry-run: nada gravado)")
    else:
        print(f"\nSnapshots em {SNAP_DIR}/  | registry em {REGISTRY}")


if __name__ == "__main__":
    main()
