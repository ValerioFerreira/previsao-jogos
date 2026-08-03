#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_clubs_exhaustive.py
=====================================
Coleta EXAUSTIVA de "todos os jogos de todos os clubes conhecidos" (pedido do dono,
2026-08-01): alguns confrontos mostram dado "desatualizado ou limitado" porque nem
todo clube já foi baixado por inteiro, mesmo com `prefetch_clubs.py`/
`prefetch_clubs_parallel.py` rodando há dias.

Não é um coletor novo -- é o `prefetch_clubs_parallel.py` (throttle/put/flush/retry,
tudo reaproveitado via `run_parallel_prefetch`, ver `scripts/prefetch_clubs_parallel.py`)
apontado para `LEAGUES_ALL_ORDERED` (`scripts/prefetch_clubs.py`): a fusão de `LEAGUES` +
`LEAGUES_EXPANSION_20260730` (150 competições, sem duplicar id) reordenada em
prioridade ESTRITA:

    Brasil -> Europa -> Sul-Americano -> Resto

em vez da ordem "fama/tier editorial misturado com região" que as duas listas tinham
originalmente. Dentro de cada região a ordem relativa original é preservada.

Cache-first (pula fixture já presente em `data/club_raw_cache.sqlite` / Neon via
`cached_ids()`) e resumível -- pode parar e retomar a qualquer momento, o backfill
completo se dá ao longo de vários dias/execuções, igual ao `prefetch_clubs_parallel.py`.

Protege o `CollectOdds` (tarefa agendada que roda todo dia e depende de cota sobrando)
com `--margin` alto por padrão, mesmo padrão que `CollectExpansion` já usa em
`collect_expansion.cmd` (`--margin 15000`). Default `--local-only` é True: os blobs
brutos vão só para o espelho local -- `data/MANIFEST.yaml` já lista
`club_match_detail_cache` em `neon_to_migrate`, não faz sentido crescer o Neon com
fixtures que nenhum runtime lê.

Uso:
    python scripts/prefetch_clubs_exhaustive.py [--max 60000] [--margin 15000]
        [--from 2026] [--to 2010] [--workers 10] [--rps 6.5] [--local-only / --no-local-only]

Smoke test pequeno (não gasta cota de propósito):
    python scripts/prefetch_clubs_exhaustive.py --max 30 --margin 30000
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prefetch_clubs import LEAGUES_ALL_ORDERED
from scripts.prefetch_clubs_parallel import run_parallel_prefetch


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=60000,
                     help="teto de chamadas de API nesta execucao (default 60000)")
    ap.add_argument("--margin", type=int, default=15000,
                     help="para quando a cota diaria restante cai abaixo disso -- "
                          "default alto (15000, igual ao CollectExpansion) para nao "
                          "disputar cota com o CollectOdds do mesmo dia")
    ap.add_argument("--from", dest="ffrom", type=int, default=2026)
    ap.add_argument("--to", dest="fto", type=int, default=2010)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--rps", type=float, default=6.5)  # 390/min, com folga do teto de 450/min
    ap.add_argument("--local-only", dest="local_only", action="store_true", default=True,
                     help="grava so no espelho SQLite, sem escrever no Neon (default: True, "
                          "ver MANIFEST: club_match_detail_cache esta em neon_to_migrate)")
    ap.add_argument("--no-local-only", dest="local_only", action="store_false",
                     help="tambem escreve no Neon (raramente necessario)")
    a = ap.parse_args()

    print(f"Coleta EXAUSTIVA de clubes | ordem Brasil->Europa->SulAmericano->Resto | "
          f"{len(LEAGUES_ALL_ORDERED)} competicoes alvo", flush=True)
    run_parallel_prefetch(LEAGUES_ALL_ORDERED, a, label="Clubs EXAUSTIVO (Brasil->Europa->SulAm->Resto)")


if __name__ == "__main__":
    main()
