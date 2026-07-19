#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp12_gk_extract.py
==================================
Hipotese H12 (passo 1/2): extrai por partida/time o goleiro que efetivamente
jogou (games.position == "G", minutes != None, maior nro de minutos entre os
goleiros do time naquele jogo) + suas estatisticas de jogo
(players[].statistics.goals.{saves,conceded}) a partir do espelho local bruto
(club_raw_cache.sqlite, JSON da api-football).

ZERO chamada a API -- 100% leitura local. O espelho local desta worktree de
pesquisa esta vazio (0 bytes, coleta em producao roda em paralelo escrevendo
no espelho do repo principal); lemos o espelho do repo principal em modo
read-only (nao concorre com o escritor, nao grava nada).

Paralelizado via multiprocessing (parse de JSON é CPU-bound; 200k+ blobs).

Saida: data/built/club_gk_stats.parquet
  fixture_id, team (Nome#id), gk_id, gk_name, minutes, saves, conceded

Uso: python scripts/clubs_hyp12_gk_extract.py [--workers N] [--batch-size N]
"""
import argparse
import json
import sqlite3
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Espelho do repo PRINCIPAL (não desta worktree de pesquisa) — só leitura,
# nunca escreve (coleta de produção pode estar escrevendo lá agora).
RAW_DB = Path(r"C:\Users\operadorsge\Desktop\Projetos\previsao-jogos\backend\data\club_raw_cache.sqlite")
OUT = ROOT / "data" / "built" / "club_gk_stats.parquet"


def team_key(t):
    return f"{(t.get('name') or '').strip()}#{t.get('id')}"


def parse_batch(raws):
    rows = []
    for fixture_id, raw in raws:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        for team_block in d.get("players") or []:
            team = team_block.get("team") or {}
            tkey = team_key(team)
            best = None  # (minutes, gk_id, gk_name, saves, conceded)
            for p in team_block.get("players") or []:
                stats_list = p.get("statistics") or []
                if not stats_list:
                    continue
                st = stats_list[0]
                games = st.get("games") or {}
                if games.get("position") != "G":
                    continue
                minutes = games.get("minutes")
                if minutes is None:
                    continue
                if best is None or minutes > best[0]:
                    goals = st.get("goals") or {}
                    pl = p.get("player") or {}
                    best = (minutes, pl.get("id"), pl.get("name"),
                            goals.get("saves"), goals.get("conceded"))
            if best is not None:
                minutes, gk_id, gk_name, saves, conceded = best
                rows.append({"fixture_id": fixture_id, "team": tkey, "gk_id": gk_id,
                            "gk_name": gk_name, "minutes": minutes,
                            "saves": saves, "conceded": conceded})
    return rows


def batch_reader(cursor, batch_size):
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            return
        yield rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=1500)
    ap.add_argument("--limit", type=int, default=None, help="debug: só as N primeiras linhas")
    a = ap.parse_args()

    t0 = time.time()
    conn = sqlite3.connect(f"file:{RAW_DB}?mode=ro", uri=True, timeout=60, check_same_thread=False)
    n_total = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    print(f"espelho: {RAW_DB} ({n_total} fixtures)", flush=True)
    sql = "SELECT fixture_id, raw FROM raw"
    if a.limit:
        sql += f" LIMIT {a.limit}"
    cur = conn.execute(sql)

    all_rows = []
    n_batches_est = (a.limit or n_total) // a.batch_size + 1
    with Pool(processes=a.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(parse_batch, batch_reader(cur, a.batch_size), chunksize=1)):
            all_rows.extend(res)
            if i % 20 == 0:
                print(f"  batch {i}/{n_batches_est} ({len(all_rows)} gk-game rows até agora, "
                      f"{time.time()-t0:.0f}s)", flush=True)
    conn.close()

    df = pd.DataFrame(all_rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    n_with_saves = df["saves"].notna().sum() if len(df) else 0
    print(f"\nsalvo {OUT}: {len(df)} linhas goleiro-jogo "
          f"({df['fixture_id'].nunique() if len(df) else 0} fixtures, "
          f"{df['gk_id'].nunique() if len(df) else 0} goleiros únicos)")
    print(f"cobertura saves não-nulo: {n_with_saves}/{len(df)} "
          f"({100*n_with_saves/max(len(df),1):.1f}%)")
    print(f"tempo total: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
