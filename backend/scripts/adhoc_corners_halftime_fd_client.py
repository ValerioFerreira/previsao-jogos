#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_fd_client.py
=============================================
Cliente minimo para a footballdata.io, usado so pela pesquisa de escanteios
1T/2T (ver plano em ~/.claude/plans/... "Modelo de escanteios 1o/2o tempo").

Contador de chamadas persistido em disco (data/external/fd_call_budget.json)
para nunca estourar o limite de 1000 chamadas da chave temporaria.

Uso:
    python scripts/adhoc_corners_halftime_fd_client.py --check-schema
    python scripts/adhoc_corners_halftime_fd_client.py --list-leagues
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_KEY = os.environ.get("FOOTBALLDATA_IO_KEY")
if not API_KEY:
    raise SystemExit("FOOTBALLDATA_IO_KEY nao configurada em backend/.env")

BASE_URL = "https://footballdata.io/api/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

BUDGET_FILE = ROOT / "data" / "external" / "fd_call_budget.json"
BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
CALL_LIMIT = 1000


def _load_budget() -> dict:
    if BUDGET_FILE.exists():
        return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
    return {"calls_used": 0, "log": []}


def _save_budget(state: dict) -> None:
    BUDGET_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def fd_get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET autenticado na footballdata.io com contador de budget persistido.

    Levanta RuntimeError se o call_limit for estourado -- protege a chave
    temporaria de 1000 chamadas.
    """
    state = _load_budget()
    if state["calls_used"] >= CALL_LIMIT:
        raise RuntimeError(
            f"Budget de {CALL_LIMIT} chamadas footballdata.io esgotado "
            f"({state['calls_used']} usadas). Abortando."
        )

    url = f"{BASE_URL}{path}"
    last_exc = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            state["calls_used"] += 1
            state["log"].append({"path": path, "params": params, "status": resp.status_code, "ts": time.time()})
            _save_budget(state)

            if resp.status_code == 429:
                raise RuntimeError(f"rate_limit_exceeded na footballdata.io: {resp.text[:300]}")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success", True) and "error" in data:
                raise RuntimeError(f"footballdata.io error: {data['error']}")
            return data
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Falha apos {retries} tentativas em {path}: {last_exc}")


def calls_used() -> int:
    return _load_budget()["calls_used"]


def calls_remaining() -> int:
    return CALL_LIMIT - calls_used()


def check_schema(sample_match_id: int | None = None) -> None:
    """Go/no-go: confirma se /matches/{id}/stats tras escanteio por tempo."""
    if sample_match_id is None:
        # pega qualquer partida recente do Brasileirao pra testar o schema
        leagues = fd_get("/leagues")
        br = [l for l in leagues.get("data", []) if "brasileir" in json.dumps(l).lower() or "brazil" in json.dumps(l).lower()]
        print(f"Ligas candidatas (Brasil): {json.dumps(br, ensure_ascii=False, indent=2)[:2000]}")
        if not br:
            print("Nenhuma liga brasileira encontrada em /leagues.")
            return
        league_id = br[0]["id"]
        matches = fd_get(f"/leagues/{league_id}/matches", params={"limit": 5, "page": 1})
        print(f"Amostra de partidas: {json.dumps(matches, ensure_ascii=False, indent=2)[:2000]}")
        data = matches.get("data", [])
        if not data:
            print("Sem partidas retornadas.")
            return
        sample_match_id = data[0]["id"]

    stats = fd_get(f"/matches/{sample_match_id}/stats")
    print(f"\n=== /matches/{sample_match_id}/stats ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    events = fd_get(f"/matches/{sample_match_id}/events")
    print(f"\n=== /matches/{sample_match_id}/events ===")
    print(json.dumps(events, ensure_ascii=False, indent=2)[:3000])


def list_leagues() -> None:
    leagues = fd_get("/leagues")
    print(json.dumps(leagues, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-schema", action="store_true")
    parser.add_argument("--list-leagues", action="store_true")
    parser.add_argument("--match-id", type=int, default=None)
    parser.add_argument("--usage", action="store_true")
    args = parser.parse_args()

    if args.usage:
        print(f"Chamadas usadas: {calls_used()} / {CALL_LIMIT} (restam {calls_remaining()})")
        sys.exit(0)
    if args.list_leagues:
        list_leagues()
    if args.check_schema:
        check_schema(args.match_id)
    print(f"\n[budget] chamadas usadas ate agora: {calls_used()} / {CALL_LIMIT}")
