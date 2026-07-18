#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/collect_club_odds_forward.py
======================================
Coletor FORWARD de odds pré-jogo para CLUBES — mesma lógica de
collect_odds_forward.py (só olha jogos ainda não iniciados; odds só existem
1-14 dias antes do jogo, sem histórico retroativo), mas alvo = as 26 ligas de
clubes rastreadas (scripts/prefetch_clubs.py::LEAGUES), não as ligas de seleção.

Preenche a lacuna documentada na Fase 8 da pesquisa de clubes
(docs/PESQUISA_CLUBES.md): `odds_registry` tinha ZERO cobertura de clubes.
Sem snapshot de modelo (não há Predictor de clubes em produção ainda) — só
odds + metadados, para futuro backtest de valor quando a Linha A/B tiver um
artefato de clubes promovido.

Escreve em data/odds/club_snapshots/<fixture>.jsonl e
data/odds/club_registry.json (mesmo padrão do coletor de seleções).

Uso:
  python scripts/collect_club_odds_forward.py [--days 10] [--dry-run]
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
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from scripts.fetch_odds import BASE, load_key, parse_fixture_odds  # noqa: E402
from scripts.prefetch_clubs import LEAGUES  # noqa: E402

ODDS_DIR = ROOT / "data" / "odds"
SNAP_DIR = ODDS_DIR / "club_snapshots"
REGISTRY = ODDS_DIR / "club_registry.json"


def _trained_target_leagues() -> dict[int, str]:
    """Restringe a coleta às ligas que o artefato de clube TREINADO conhece
    (`tournament_weights` do meta.json) -- mesmo padrão de
    collect_odds_forward.py::target_league_ids() pro lado seleção (só ligas
    que o modelo sabe prever). Evita listar partida de time fora do roster."""
    meta_path = ROOT / "model_artifacts_clubes" / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        trained = set(meta.get("tournament_weights", {}).keys())
    except Exception:
        trained = set()
    if not trained:
        return {lid: name for lid, name in LEAGUES}
    return {lid: name for lid, name in LEAGUES if name in trained}


def _trained_team_names_by_id() -> dict[int, str]:
    """Mapa id (api-football) -> nome CANÔNICO já desambiguado do artefato treinado
    (`team_ids` do meta.json, name->id -- ver disambiguate_collisions em
    build_clubs_production_artifacts.py). A API de odds devolve o nome cru (ex.:
    "Athletic Club"), que não bate com o nome desambiguado do roster quando há
    colisão entre ligas (ex.: "Athletic Club (Brasileirao Serie B)" vs "(La Liga)")
    -- sem essa correção, brasão/H2H/histórico do time colidente ficam vazios."""
    meta_path = ROOT / "model_artifacts_clubes" / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        team_ids = meta.get("team_ids", {})
    except Exception:
        team_ids = {}
    return {int(tid): name for name, tid in team_ids.items()}


TARGET_LEAGUES = _trained_target_leagues()
TEAM_NAMES_BY_ID = _trained_team_names_by_id()


def _canonical_name(raw_name: str | None, team_id: int | None) -> str | None:
    if team_id is not None and team_id in TEAM_NAMES_BY_ID:
        return TEAM_NAMES_BY_ID[team_id]
    return raw_name

# Prioridade pedida pelo usuário p/ a coleta de odds de clube (cota apertada, assinatura
# expirando 2026-07-19) -- essas ligas são processadas primeiro; o restante entra na
# ordem original de LEAGUES só se sobrar cota.
PRIORITY_LEAGUES = [
    "Brasileirao Serie A",
    "Brasileirao Serie B",
    "Copa do Brasil",
    "Champions League",
    "Premier League",
    "La Liga",
]


def _priority_rank(league_name: str) -> int:
    try:
        return PRIORITY_LEAGUES.index(league_name)
    except ValueError:
        return len(PRIORITY_LEAGUES)


def api_get(path: str, key: str, **params):
    r = requests.get(BASE + path, headers={"x-apisports-key": key}, params=params, timeout=30)
    r.raise_for_status()
    return r.json(), r.headers.get("x-ratelimit-requests-remaining")


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def sync_registry_to_db(registry: dict) -> None:
    """Mesmo padrão do coletor de seleções: espelha no Neon p/ sobreviver ao disco
    efêmero do Render (tabela separada `club_odds_registry`, nunca mistura com a
    de seleções)."""
    if not registry:
        return
    try:
        import pandas as pd
        from app.db.connection import engine, upsert_df
        from sqlalchemy import text

        with engine.begin() as c:
            c.execute(text(
                "CREATE TABLE IF NOT EXISTS club_odds_registry ("
                "fixture_id TEXT PRIMARY KEY, home TEXT, away TEXT, league_id INT, "
                "league_name TEXT, fixture_date TEXT, last_collected TEXT, n_snapshots INT)"
            ))
        rows = [{
            "fixture_id": str(fid), "home": info.get("home"), "away": info.get("away"),
            "league_id": info.get("league_id"), "league_name": info.get("league_name"),
            "fixture_date": info.get("fixture_date"), "last_collected": info.get("last_collected"),
            "n_snapshots": info.get("n_snapshots", 0),
        } for fid, info in registry.items()]
        upsert_df(pd.DataFrame(rows), "club_odds_registry", engine, unique_keys=["fixture_id"])
        print(f">> club_odds_registry sincronizada no Neon: {len(rows)} jogos")
    except Exception as exc:
        print(f"[AVISO] Falha ao sincronizar club_odds_registry no Neon: {exc}")


def collect(days: int, dry_run: bool, quota_buffer: int = 50, odds_window_days: int = 16) -> dict:
    """`days` = até onde ENUMERAMOS jogos (o quanto der -- descoberta é barata, 1
    request/dia cobre TODAS as ligas de uma vez). `odds_window_days` = até onde
    TENTAMOS odds (a api-football só publica 1-14 dias antes; tentar além disso é
    cota jogada fora). Todo jogo descoberto entra no registry (visível no seletor
    "Partida Agendada") independente de ter odds ou não -- odds não é mais gate de
    visibilidade, só enriquecimento oportunista pro backtest de valor."""
    key = load_key()
    registry = load_registry()
    today = datetime.now(timezone.utc).date()
    remaining = None
    stopped_early = False

    # Fase 1 (descoberta): 1 request/dia, barato -- cobre a janela inteira antes de
    # gastar cota com /odds (que é 1 request por partida, o custo de verdade).
    candidates = []  # (fixture_id, home, away, league_name, league_id, date, status)
    for offset in range(days):
        day = (today + timedelta(days=offset)).isoformat()
        data, remaining = api_get("/fixtures", key, date=day)
        for item in data.get("response", []):
            league = item.get("league", {})
            lid = league.get("id")
            if lid not in TARGET_LEAGUES:
                continue
            fx = item.get("fixture", {})
            status = fx.get("status", {}).get("short")
            if status not in ("NS", "TBD"):
                continue
            teams = item.get("teams", {})
            home_name = _canonical_name(teams.get("home", {}).get("name"), teams.get("home", {}).get("id"))
            away_name = _canonical_name(teams.get("away", {}).get("name"), teams.get("away", {}).get("id"))
            candidates.append((
                fx.get("id"), home_name, away_name,
                TARGET_LEAGUES[lid], lid, fx.get("date"), status, offset,
            ))
        if remaining is not None and int(remaining) <= quota_buffer:
            print(f"[AVISO] cota perto do limite ({remaining} restantes) -- parando a descoberta em {day}")
            stopped_early = True
            break

    # Registra TODOS os candidatos já aqui (visíveis no seletor mesmo sem odds).
    seen_fixtures = [(c[0], c[1], c[2], c[3], c[5]) for c in candidates]
    if not dry_run:
        for fixture_id, home, away, league_name, lid, date, status, offset in candidates:
            prev = registry.get(str(fixture_id), {})
            registry[str(fixture_id)] = {
                **prev,
                "home": home, "away": away, "league_id": lid,
                "league_name": league_name, "fixture_date": date,
                "n_snapshots": prev.get("n_snapshots", 0),
            }

    # Fase 2 (odds): 1 request/partida, só dentro de `odds_window_days` (fora disso a
    # api-football sempre volta vazio), em ordem de prioridade -- Brasileirão A/B, Copa
    # do Brasil, Champions, Premier, La Liga primeiro; resto por ordem de LEAGUES se
    # sobrar cota (ver PRIORITY_LEAGUES).
    odds_candidates = [c for c in candidates if c[7] <= odds_window_days]
    odds_candidates.sort(key=lambda c: _priority_rank(c[3]))
    odds_collected = 0

    for fixture_id, home, away, league_name, lid, date, status, offset in odds_candidates:
        if remaining is not None and int(remaining) <= quota_buffer:
            print(f"[AVISO] cota perto do limite ({remaining} restantes) -- parando antes de {league_name}")
            stopped_early = True
            break

        odds_json, remaining = api_get("/odds", key, fixture=fixture_id)
        resp = odds_json.get("response", [])
        odds = parse_fixture_odds(resp[0]) if resp else {}
        if not odds:
            time.sleep(0.2)
            continue

        snapshot = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "fixture_date": date, "status": status,
            "home": home, "away": away, "league_id": lid,
            "league_name": league_name, "odds": odds,
        }
        odds_collected += 1
        if not dry_run:
            SNAP_DIR.mkdir(parents=True, exist_ok=True)
            with (SNAP_DIR / f"{fixture_id}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
            registry[str(fixture_id)]["last_collected"] = snapshot["collected_at"]
            registry[str(fixture_id)]["n_snapshots"] = registry[str(fixture_id)].get("n_snapshots", 0) + 1
        time.sleep(0.2)

    if not dry_run and seen_fixtures:
        ODDS_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        sync_registry_to_db(registry)

    return {"dias": days, "jogos_vistos": len(seen_fixtures), "odds_coletadas": odds_collected,
           "fixtures": seen_fixtures, "cota_restante": remaining, "dry_run": dry_run,
           "parou_por_cota": stopped_early}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=270, help="janela de dias a frente p/ ENUMERAR jogos (descoberta é barata)")
    ap.add_argument("--odds-window-days", type=int, default=16, help="janela de dias a frente p/ TENTAR odds (api-football só publica 1-14 dias antes)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quota-buffer", type=int, default=50,
                     help="Para a coleta quando a cota restante do dia chegar nesse valor (proteção contra 429).")
    a = ap.parse_args()
    summary = collect(a.days, a.dry_run, a.quota_buffer, a.odds_window_days)
    print(f"\nJanela: {summary['dias']} dias | jogos de CLUBES vistos: {summary['jogos_vistos']} "
          f"| com odds: {summary['odds_coletadas']} | cota restante: {summary['cota_restante']}"
          f"{' | PAROU CEDO POR COTA' if summary['parou_por_cota'] else ''}")
    for fid, home, away, lg, date in summary["fixtures"][:40]:
        print(f"  {date}  {home} x {away}  [{lg}]  (fixture {fid})")
    if summary["dry_run"]:
        print("\n(dry-run: nada gravado)")
    else:
        print(f"\nSnapshots em {SNAP_DIR}/  | registry em {REGISTRY}")


if __name__ == "__main__":
    main()
