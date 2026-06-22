#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/collect_players_fast.py
==========================================
Versao CONCORRENTE do collect_players: I/O-bound, entao usa ThreadPool com um
rate-limiter GLOBAL (<=400/min, abaixo do teto de 450) e o mesmo cache em disco.
Reaproveita o que ja foi baixado. Ao final, parseia TODO o cache -> player_club_form.parquet.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "player_ranking" / "src"))
from collect_players import parse_club_form, all_pairs  # noqa: E402

CACHE = ROOT / "player_ranking" / "data" / "raw" / "players_profile"
INTERIM = ROOT / "player_ranking" / "data" / "interim"
BASE = "https://v3.football.api-sports.io"

WORKERS = 8
MIN_INTERVAL = 0.15           # 400/min global
MAX_LIVE = 60000

_lock = threading.Lock()
_next = [0.0]
_live = [0]
_remaining = [None]


def load_key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("APIFOOTBALL_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("APIFOOTBALL_KEY ausente.")


KEY = load_key()


def throttle():
    with _lock:
        now = time.time()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + MIN_INTERVAL
    if wait > 0:
        time.sleep(wait)


def fetch_one(pid, season):
    cpath = CACHE / str(season) / f"{pid}.json"
    if cpath.exists():
        return "cache"
    with _lock:
        if _live[0] >= MAX_LIVE:
            return "budget"
    for attempt in range(4):
        throttle()
        try:
            r = requests.get(BASE + "/players", headers={"x-apisports-key": KEY},
                             params={"id": pid, "season": season}, timeout=30)
            with _lock:
                _live[0] += 1
                _remaining[0] = r.headers.get("x-ratelimit-requests-remaining")
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            resp = r.json().get("response", [])
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
            return "live"
        except requests.RequestException:
            if attempt == 3:
                return "error"
            time.sleep(1.5 * (attempt + 1))
    return "error"


def main():
    pairs = all_pairs()
    todo = [(p, s) for p, s in pairs if not (CACHE / str(s) / f"{p}.json").exists()]
    print(f"pares totais: {len(pairs)} | ja em cache: {len(pairs)-len(todo)} | a baixar: {len(todo)}")
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, p, s): (p, s) for p, s in todo}
        for fut in as_completed(futs):
            done += 1
            if done % 500 == 0:
                el = time.time() - t0
                rate = _live[0] / el * 60 if el else 0
                print(f"  {done}/{len(todo)} | live {_live[0]} | {rate:.0f}/min | rest {_remaining[0]} | {el:.0f}s")
    print(f"coleta concluida em {time.time()-t0:.0f}s | live {_live[0]} | cota restante {_remaining[0]}")

    # parseia TODO o cache -> forma de clube
    rows = []
    for f in CACHE.glob("*/*.json"):
        try:
            resp = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rec = parse_club_form(resp, int(f.stem), int(f.parent.name))
        if rec:
            rows.append(rec)
    df = pd.DataFrame(rows)
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / "player_club_form.parquet")
    print(f"forma de clube: {len(df)} jogadores | rating notna {df.rating.notna().sum()}")
    print(f"salvo: {INTERIM / 'player_club_form.parquet'}")


if __name__ == "__main__":
    main()
