#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/fetch_historical_odds.py — baixa temporadas históricas de odds reais.
==============================================================================

Fonte: football-data.co.uk — CSVs públicos, gratuitos, uma URL por liga/temporada:
    https://www.football-data.co.uk/mmz4281/<TEMPORADA>/<DIV>.csv
onde TEMPORADA = "2425" (2024/25), "2526" (2025/26)… e DIV = E0, SP1, I1, D1, BRA…

## Por que isto é a prioridade nº 1 de dados (ver DOCUMENTACAO_CENTRAL.md §25.3)

O dataset de jogos vai de 2010 a 2026, mas as odds cobrem **uma única temporada** — por isso o
backtest honesto do §24 ficou com N=722. Poder estatístico exigido para detectar um edge de 2%:
~20.100 apostas. Baixar ~16 temporadas das ligas que já cobrimos deve levar o N casado para a
casa dos 10-15 mil, sem custo de API e sem depender de credencial nenhuma.

Ressalvas honestas:
- Temporadas antigas têm MENOS colunas de casas individuais (o alfa de cotação da Hipótese A
  fica com cobertura menor quanto mais se volta no tempo). O `Max`/`Avg` aparece a partir de
  meados dos anos 2000 na maioria das ligas principais.
- O Brasileirão NÃO está nos CSVs por temporada (football-data.co.uk cobre só ligas europeias);
  ele vem do `new_leagues_data.xlsx`, que já temos e traz 2012-2026 mas só 1X2 de fechamento.

Uso:
  python -m scripts.fetch_historical_odds --from 2010 --to 2026            # ligas padrão
  python -m scripts.fetch_historical_odds --from 2010 --to 2026 --divs E0,SP1
  python -m scripts.fetch_historical_odds --list                            # só lista o plano

Saída: data-test/historical/<TEMPORADA>/<DIV>.csv  (ingerido depois por backtest_odds_ingest.py)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
OUT_ROOT = REPO_ROOT / "data-test" / "historical"
BASE_URL = "https://www.football-data.co.uk/mmz4281"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ligas que o projeto cobre ou pretende cobrir. As 4 locais de hoje são Brasileirão A/B,
# Premier League e Champions League — dessas, só a Premier League tem fonte aqui (E0).
# As demais entram valendo assim que o backfill de competições (§24.5) concluir.
DEFAULT_DIVS = [
    "E0",   # Premier League          <- única das nossas 4 ligas locais com fonte aqui
    "E1", "E2", "E3", "EC",           # divisões inferiores inglesas
    "SP1", "SP2",                     # Espanha
    "I1", "I2",                       # Itália
    "D1", "D2",                       # Alemanha
    "F1", "F2",                       # França
    "N1", "P1", "T1", "B1", "G1",     # Holanda, Portugal, Turquia, Bélgica, Grécia
    "SC0", "SC1", "SC2", "SC3",       # Escócia
]


def season_codes(year_from: int, year_to: int) -> list[str]:
    """2010..2026 -> ['1011', '1112', ..., '2526']. A temporada europeia cruza o ano civil."""
    out = []
    for y in range(year_from, year_to):
        out.append(f"{y % 100:02d}{(y + 1) % 100:02d}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Baixa odds históricas do football-data.co.uk")
    ap.add_argument("--from", dest="year_from", type=int, default=2010)
    ap.add_argument("--to", dest="year_to", type=int, default=2026)
    ap.add_argument("--divs", default=",".join(DEFAULT_DIVS),
                    help="ligas separadas por vírgula (default: 22 ligas europeias)")
    ap.add_argument("--list", action="store_true", help="só mostra o plano, não baixa")
    ap.add_argument("--sleep", type=float, default=0.5,
                    help="pausa entre requisições (educação com o servidor)")
    ap.add_argument("--force", action="store_true", help="rebaixa mesmo se o arquivo já existir")
    args = ap.parse_args()

    divs = [d.strip() for d in args.divs.split(",") if d.strip()]
    seasons = season_codes(args.year_from, args.year_to)
    total = len(divs) * len(seasons)

    print("=" * 84)
    print(" DOWNLOAD DE ODDS HISTORICAS -- football-data.co.uk")
    print("=" * 84)
    print(f"Temporadas: {len(seasons)} ({seasons[0]} .. {seasons[-1]})")
    print(f"Ligas:      {len(divs)} ({', '.join(divs[:8])}{'...' if len(divs) > 8 else ''})")
    print(f"Arquivos:   {total}")
    print(f"Destino:    {OUT_ROOT}")
    if args.list:
        print("\n[--list] plano apenas, nada baixado.")
        return

    import httpx

    ok = skipped = failed = 0
    bytes_total = 0
    for season in seasons:
        for div in divs:
            dest = OUT_ROOT / season / f"{div}.csv"
            if dest.exists() and not args.force:
                skipped += 1
                continue
            url = f"{BASE_URL}/{season}/{div}.csv"
            try:
                r = httpx.get(url, timeout=60, follow_redirects=True)
                # 404 é esperado e normal: nem toda liga existe em toda temporada.
                if r.status_code == 404:
                    failed += 1
                    continue
                r.raise_for_status()
                content = r.content
                # Página de erro HTML às vezes volta com 200 — checa se parece CSV de verdade.
                if not content[:200].lstrip().lower().startswith(b"div,"):
                    failed += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                ok += 1
                bytes_total += len(content)
                print(f"  OK  {season}/{div}.csv  ({len(content)/1024:.0f} KB)")
            except Exception as e:
                failed += 1
                print(f"  ERRO {season}/{div}: {type(e).__name__}")
            time.sleep(args.sleep)

    print("\n" + "=" * 84)
    print(f"Baixados: {ok} ({bytes_total/1024/1024:.1f} MB) | já existiam: {skipped} | "
          f"indisponíveis (404/liga inexistente na temporada): {failed}")
    print("\nPróximo passo: registrar no MANIFEST + push pro WorkDrive, depois")
    print("  python -m scripts.backtest_odds_ingest   (precisa aceitar data-test/historical/)")


if __name__ == "__main__":
    main()
