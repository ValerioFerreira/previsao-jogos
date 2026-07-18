#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/mirror_club_cache.py
============================
Cria o espelho LOCAL (SQLite) do bruto de CLUBES sem egress do Neon: lê apenas a
lista de fixture_ids do `club_match_detail_cache` (~2 MB) e re-baixa o detalhe
completo direto da API-Football para `data/club_raw_cache.sqlite`, usando a cota
ociosa do dia (as coletas já saturaram). Resumível e com guarda de cota.

Por que não puxar o raw do Neon: são ~2,4 GB de blobs — o projeto acabou de reduzir
o egress mensal para <0,5 GB (ARCHITECTURE.md §3.1). A API custa 1 chamada/jogo da
cota diária de 75k, que hoje está ociosa.

Paralelo: N workers (default 6) com rate-limit global de ~360 req/min (limite da API é
450/min) e um único escritor SQLite (fila) — ~2,5h para 54k jogos.

Uso: python scripts/mirror_club_cache.py [--max 60000] [--margin 1000] [--workers 6]
"""
import argparse
import json
import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get

LOCAL_PATH = Path(__file__).resolve().parents[1] / "data" / "club_raw_cache.sqlite"


def _conn() -> sqlite3.Connection:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOCAL_PATH))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS raw (key TEXT PRIMARY KEY, fixture_id INTEGER, "
        "league_id INTEGER, season INTEGER, raw TEXT)"
    )
    return conn


def neon_id_list():
    """Só ids/league/season do Neon — colunas pequenas, sem blobs."""
    from app.db.connection import engine
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT fixture_id, league_id, season FROM club_match_detail_cache"
        )).fetchall()
    return [(int(r[0]), int(r[1]), int(r[2])) for r in rows if r[0] is not None]


class RateLimiter:
    """Rate-limit global compartilhado entre workers (req/s)."""
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
    ap.add_argument("--max", type=int, default=60000)
    ap.add_argument("--margin", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rps", type=float, default=6.0)  # 360/min < 450/min do plano
    a = ap.parse_args()

    conn = _conn()
    have = {r[0] for r in conn.execute("SELECT fixture_id FROM raw").fetchall()}
    ids = neon_id_list()
    todo = [(f, l, s) for f, l, s in ids if f not in have]
    print(f"Mirror clubes | no Neon: {len(ids)} | ja no espelho: {len(have)} | a baixar: {len(todo)}",
          flush=True)

    state = {"calls": 0, "ok": 0, "fail": 0, "rem": None, "stop": None}
    slock = threading.Lock()
    work_q: "queue.Queue" = queue.Queue()
    write_q: "queue.Queue" = queue.Queue()
    for item in todo:
        work_q.put(item)
    limiter = RateLimiter(a.rps)
    t0 = time.time()

    def worker():
        while True:
            with slock:
                if state["stop"]:
                    return
                if state["calls"] >= a.max:
                    state["stop"] = "MAX"; return
                if state["rem"] is not None and state["rem"] <= a.margin:
                    state["stop"] = "LIMITE_DIARIO"; return
                state["calls"] += 1
            try:
                fid, lid, season = work_q.get_nowait()
            except queue.Empty:
                return
            limiter.acquire()
            try:
                resp, r = _get("/fixtures", id=fid)
                with slock:
                    if r is not None:
                        state["rem"] = int(r)
                if resp:
                    write_q.put((f"club|{lid}|{fid}", fid, lid, season,
                                 json.dumps(resp[0], ensure_ascii=False)))
                    with slock:
                        state["ok"] += 1
                else:
                    with slock:
                        state["fail"] += 1
            except Exception as e:
                with slock:
                    state["fail"] += 1
                print(f"  [AVISO] fixture {fid}: {e}", flush=True)
                time.sleep(1.0)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(a.workers)]
    for t in threads:
        t.start()

    # escritor único (SQLite não gosta de escrita concorrente)
    done_since_commit = 0
    while any(t.is_alive() for t in threads) or not write_q.empty():
        try:
            row = write_q.get(timeout=2.0)
        except queue.Empty:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO raw(key, fixture_id, league_id, season, raw) "
            "VALUES (?,?,?,?,?)", row)
        done_since_commit += 1
        if done_since_commit >= 500:
            conn.commit()
            done_since_commit = 0
            with slock:
                rem = state["rem"]
                n_ok, n_fail = state["ok"], state["fail"]
            rate = n_ok / max(time.time() - t0, 1)
            eta_min = (len(todo) - n_ok) / max(rate, 0.01) / 60
            print(f"  progresso {n_ok}/{len(todo)} | fail={n_fail} | cota ~{rem} | "
                  f"{rate:.1f} req/s | ETA {eta_min:.0f} min", flush=True)
    conn.commit()
    if state["stop"]:
        print(f"PAROU: {state['stop']}", flush=True)
    n = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    conn.close()
    print(f">> Mirror: {state['ok']} baixados | {state['fail']} falhas | {state['calls']} chamadas | "
          f"cota ~{state['rem']} | total no espelho: {n}", flush=True)


if __name__ == "__main__":
    main()
