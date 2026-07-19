#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_clubs_parallel.py
===================================
Versão PARALELA do prefetch_clubs.py — mesma lista LEAGUES (importada, não duplicada),
mesmas tabelas de destino (`club_match_detail_cache` no Neon + espelho local
`data/club_raw_cache.sqlite`), mas usa N workers concorrentes para o download de
detalhe de cada fixture (o passo caro), igual ao padrão já validado em
`mirror_club_cache.py` (~360 req/min sustentado com 6 workers).

Por que existe: o `prefetch_clubs.py` sequencial mede ~15-20 chamadas/min na prática
(2026-07-18) porque `httpx.get()` sem keep-alive paga handshake TCP/TLS completo a
cada chamada -- a "cota" nunca foi o gargalo, o tempo de parede é. Paralelizar recupera
a banda real da API (~450/min no plano Ultra).

Listagem de temporadas continua sequencial (barata, poucas centenas de chamadas no
total) -- só o download de detalhe por fixture (a maioria das chamadas) é paralelo.

Uso: python scripts/prefetch_clubs_parallel.py [--max 70000] [--margin 500] [--workers 10] [--rps 7]
"""
import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get
from scripts.prefetch_clubs import LEAGUES, FINISHED, TABLE, ensure_table, cached_ids, _local_put_batch

MAX_RETRIES = 4


def neon_put(fixture_id, league_id, season, raw):
    """Só o Neon -- seguro em paralelo (pool de conexões do SQLAlchemy + ON CONFLICT
    idempotente). O espelho local (SQLite) fica só no escritor único (não gosta de
    escrita concorrente) -- ver prefetch_clubs._local_put_batch."""
    from app.db.connection import engine
    key = f"club|{league_id}|{fixture_id}"
    with engine.begin() as c:
        c.execute(text(
            f"INSERT INTO {TABLE} (key, fixture_id, league_id, season, raw, cached_at) "
            "VALUES (:k,:f,:l,:s,:r, now()) ON CONFLICT (key) DO UPDATE SET raw=EXCLUDED.raw, cached_at=now()"
        ), {"k": key, "f": fixture_id, "l": league_id, "s": season, "r": json.dumps(raw, ensure_ascii=False)})


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_t = time.monotonic()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            if now < self.next_t:
                wait = self.next_t - now
                self.next_t += self.interval
            else:
                wait = 0.0
                self.next_t = now + self.interval
        if wait > 0:
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=70000)
    ap.add_argument("--margin", type=int, default=500)
    ap.add_argument("--from", dest="ffrom", type=int, default=2026)
    ap.add_argument("--to", dest="fto", type=int, default=2010)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--rps", type=float, default=6.5)  # 390/min, com folga do teto de 450/min
    a = ap.parse_args()

    ensure_table()
    have = cached_ids()
    state = {"calls": 0, "novos": 0, "falhas": 0, "rem": None, "stop": None}
    slock = threading.Lock()

    def budget_ok_locked():
        if state["calls"] >= a.max:
            state["stop"] = "MAX"; return False
        if state["rem"] is not None and state["rem"] <= a.margin:
            state["stop"] = "LIMITE_DIARIO"; return False
        return True

    print(f"Clubs prefetch PARALELO | ja em cache: {len(have)} fixtures | "
          f"{len(LEAGUES)} ligas | workers={a.workers} rps={a.rps}", flush=True)

    # 1) Listagem sequencial (barata) -- monta a fila de fixtures novas por liga/temporada.
    todo = []  # (fixture_id, league_id, season)
    for league_id, nome in LEAGUES:
        with slock:
            if not budget_ok_locked():
                break
        print(f"== Liga {nome} ({league_id}) ==", flush=True)
        for season in range(a.ffrom, a.fto - 1, -1):
            with slock:
                if not budget_ok_locked():
                    break
                state["calls"] += 1
            try:
                fxs, rem = _get("/fixtures", league=league_id, season=season)
                time.sleep(0.15)
                if rem is not None:
                    with slock:
                        state["rem"] = int(rem)
            except Exception as e:
                print(f"  [AVISO] {nome}/{season}: {e}", flush=True)
                continue
            finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            new_ids = [(f.get("fixture") or {}).get("id") for f in finished]
            new_ids = [fid for fid in new_ids if fid and fid not in have]
            for fid in new_ids:
                todo.append((fid, league_id, season))
                have.add(fid)
            print(f"  {season}: {len(finished)} encerrados, {len(new_ids)} a baixar | fila={len(todo)}", flush=True)

    print(f">> Listagem concluida | fila de download: {len(todo)} fixtures | "
          f"chamadas ate aqui: {state['calls']} | cota ~{state['rem']}", flush=True)

    # 2) Download de detalhe em paralelo (o grosso das chamadas).
    work_q: "queue.Queue" = queue.Queue()
    write_q: "queue.Queue" = queue.Queue()
    retries: dict = {}
    for item in todo:
        work_q.put(item)
    limiter = RateLimiter(a.rps)
    t0 = time.time()

    def worker():
        while True:
            with slock:
                if state["stop"] or not budget_ok_locked():
                    return
                state["calls"] += 1
            try:
                fid, lid, season = work_q.get_nowait()
            except queue.Empty:
                return
            limiter.acquire()
            try:
                resp, rem = _get("/fixtures", id=fid)
                if rem is not None:
                    with slock:
                        state["rem"] = int(rem)
                if resp:
                    neon_put(fid, lid, season, resp[0])  # paralelo, direto no worker
                    write_q.put((fid, lid, season, resp[0]))  # só a fila do espelho local
                    with slock:
                        state["novos"] += 1
                else:
                    with slock:
                        state["falhas"] += 1
            except httpx.HTTPStatusError as e:
                is_429 = e.response is not None and e.response.status_code == 429
                n = retries.get(fid, 0)
                if is_429 and n < MAX_RETRIES:
                    retries[fid] = n + 1
                    time.sleep(2.0 * (n + 1))  # backoff crescente, da folga ao rate-limit
                    work_q.put((fid, lid, season))
                else:
                    with slock:
                        state["falhas"] += 1
                    print(f"    [AVISO] fixture {fid}: {e}", flush=True)
            except Exception as e:
                n = retries.get(fid, 0)
                if n < MAX_RETRIES:
                    retries[fid] = n + 1
                    time.sleep(1.0 * (n + 1))
                    work_q.put((fid, lid, season))
                else:
                    with slock:
                        state["falhas"] += 1
                    print(f"    [AVISO] fixture {fid}: {e}", flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(a.workers)]
    for t in threads:
        t.start()

    done_since_log = 0
    while any(t.is_alive() for t in threads) or not write_q.empty():
        try:
            fid, lid, season, raw = write_q.get(timeout=2.0)
        except queue.Empty:
            continue
        key = f"club|{lid}|{fid}"
        _local_put_batch([(key, fid, lid, season, raw)])  # só o espelho local; Neon já foi gravado no worker
        done_since_log += 1
        if done_since_log >= 200:
            done_since_log = 0
            with slock:
                rem, n_ok, n_fail, calls = state["rem"], state["novos"], state["falhas"], state["calls"]
            rate = n_ok / max(time.time() - t0, 1) * 60
            eta_min = (len(todo) - n_ok) / max(rate, 1) if len(todo) else 0
            print(f"  progresso {n_ok}/{len(todo)} | fail={n_fail} | chamadas={calls} | "
                  f"cota ~{rem} | {rate:.0f} req/min | ETA {eta_min:.0f} min", flush=True)

    print(f">> Clubs (paralelo): {state['novos']} novos | {state['falhas']} falhas | "
          f"{state['calls']} chamadas | cota ~{state['rem']} | parou por: {state['stop'] or 'FIM (tudo coberto)'}",
          flush=True)


if __name__ == "__main__":
    main()
