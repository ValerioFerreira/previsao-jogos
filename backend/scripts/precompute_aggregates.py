#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/precompute_aggregates.py
================================
Roda no job diário (máquina local). Lê o detalhe bruto UMA vez (via raw_cache — do SQLite
local se existir, senão do Neon) e grava as tabelas PEQUENAS de agregados no Neon
(referee_stats_agg, goal_timing_agg, competition_bench_agg, agg_kv). Assim o site serve
Fator Árbitro / Minutagem / Quadrantes lendo bytes, sem escanear os ~44 MB do bruto.

Uso: python scripts/precompute_aggregates.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    from app.db.connection import engine
    from app.services import raw_cache, aggregates
    from app.services.predictor_service import _COMP_BUCKETS

    local = raw_cache.local_available()
    print(f"Fonte do bruto: {'SQLite local' if local else 'Neon (fallback)'} | "
          f"local rows: {raw_cache.local_count()}", flush=True)
    res = aggregates.precompute_from_raw(engine, raw_cache.iter_all_raw())
    nb = aggregates.precompute_benchmarks(engine, _COMP_BUCKETS)
    print(f">> Agregados gravados: {res['referees']} árbitros, {res['teams']} times, {nb} competições.", flush=True)


if __name__ == "__main__":
    main()
