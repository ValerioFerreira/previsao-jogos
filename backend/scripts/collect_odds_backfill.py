#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
scripts/collect_odds_backfill.py
==================================
PLANO 4 / Fase D — coleta TODAS as odds que a API-Football guarda na janela de
retenção (odds só existem ~1-14 dias antes do jogo e ~7 dias de histórico depois)
e persiste os VALORES de forma durável em `data/odds_history.sqlite` (hoje os
coletores forward só guardam em JSONL efêmero + metadados no Neon).

Objetivo: acumular um dataset rotulável (odds + resultado real) dos mercados que
ainda não validamos — BTTS, escanteios O/U, cartões O/U — para recalibrar seus
modelos (ver skill `validar-mercado-com-odds`). 1ª execução varre a janela
inteira; execuções diárias pegam só o novo (idempotente por fixture+market+
outcome+dia de coleta).

Cobre TODOS os mercados do BET_MAP (`scripts/fetch_odds.py`): resultado, gols O/U,
btts, escanteios (total/mand/vis), cartões (total/mand/vis).

## Correções de 2026-07-30 (§28 do doc-mestre)

1. **As ligas de CLUBE não entravam.** As ligas-alvo vinham só de
   `collect_odds_forward.py::target_league_ids()`, que lista os subdiretórios de
   `data/raw/fixtures/` -- 41 diretórios, todos de SELEÇÃO. As 83 competições de clube
   eram silenciosamente ignoradas, e por isso `odds_history.sqlite` tinha **12 fixtures**
   depois de dias rodando. Agora o alvo é a união dos dois escopos (`--scope`).
2. **Sem pré-filtro de dia.** A tarefa `\PrevisaoJogos\CollectOdds` roda a cada 3h (8x/dia)
   e o script re-baixava as mesmas fixtures em toda execução, porque a idempotência era só
   no `INSERT OR REPLACE`. Agora as fixtures já gravadas no dia corrente são puladas antes
   do `GET /odds`, o que torna as 7 execuções seguintes quase gratuitas.

Por que isto importa: a API-Football **não serve odd retroativa** (verificado --
`/odds?fixture=<jogo de temporada passada>` e `/odds?league=&season=` voltam vazios). Só dá
para acumular para a frente, então cada dia não coletado é perda permanente. É este dataset
que destrava a validação de BTTS/escanteios/cartões (docs/ODD_JUSTA_E_CALIBRACAO.md §4) e a
medição de CLV (DOCUMENTACAO_CENTRAL.md §25.5).

Uso:
  python scripts/collect_odds_backfill.py                 # janela padrão -7..+14, ambos escopos
  python scripts/collect_odds_backfill.py --past 7 --future 14 --buffer 2000
  python scripts/collect_odds_backfill.py --scope clube   # só clubes
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_odds import BASE, load_key, parse_fixture_odds  # noqa: E402
from scripts.collect_odds_forward import target_league_ids  # noqa: E402
from scripts.prefetch_clubs import LEAGUES as CLUB_LEAGUES  # noqa: E402
try:
    from scripts import quota_tracker
    _HAS_QUOTA = True
except Exception:  # pragma: no cover
    _HAS_QUOTA = False

import requests  # noqa: E402

DB_PATH = ROOT / "data" / "odds_history.sqlite"


def _api_get(path: str, key: str, **params):
    if _HAS_QUOTA:
        quota_tracker.throttle()
    r = requests.get(BASE + path, headers={"x-apisports-key": key}, params=params, timeout=30)
    if _HAS_QUOTA:
        quota_tracker.note_call()
    r.raise_for_status()
    return r.json()


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS odds_history (
            fixture_id  INTEGER,
            league_id   INTEGER,
            fixture_date TEXT,
            status      TEXT,
            market      TEXT,
            outcome     TEXT,
            value       REAL,
            collected_day TEXT,
            PRIMARY KEY (fixture_id, market, outcome, collected_day)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_oh_market ON odds_history(market)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_oh_date ON odds_history(fixture_date)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_oh_day ON odds_history(collected_day, fixture_id)")
    con.commit()
    return con


def _already_collected_today(con: sqlite3.Connection, day: str) -> set[int]:
    """Fixtures que já têm odds gravadas no dia corrente.

    A tarefa agendada roda a cada 3h; sem este filtro cada execução re-baixava a janela
    inteira (~10-15k requisições) só para reescrever as mesmas linhas.
    """
    try:
        return {int(f) for (f,) in con.execute(
            "SELECT DISTINCT fixture_id FROM odds_history WHERE collected_day = ?", (day,))}
    except Exception:
        return set()


def _resolve_leagues(scope: str) -> set[int]:
    """Ligas-alvo por escopo. Conjunto vazio = sem filtro (todas as ligas da API)."""
    selecao = target_league_ids()
    clube = {lid for lid, _ in CLUB_LEAGUES}
    if scope == "selecao":
        return selecao
    if scope == "clube":
        return clube
    return selecao | clube


def _fixtures_on(date_str: str, key: str, leagues: set[int]) -> list[dict]:
    j = _api_get("/fixtures", key, date=date_str)
    out = []
    for it in j.get("response", []):
        lg = (it.get("league") or {}).get("id")
        if leagues and lg not in leagues:
            continue
        fx = (it.get("fixture") or {}).get("id")
        status = ((it.get("fixture") or {}).get("status") or {}).get("short")
        if fx:
            out.append({"fixture_id": fx, "league_id": lg, "date": date_str, "status": status})
    return out


def _store(con: sqlite3.Connection, meta: dict, parsed: dict, day: str) -> int:
    rows = []
    for market, outs in parsed.items():
        if market.startswith("_"):
            continue
        for outcome, value in outs.items():
            rows.append((meta["fixture_id"], meta["league_id"], meta["date"], meta["status"],
                         market, str(outcome), float(value), day))
    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO odds_history VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--past", type=int, default=7, help="dias passados (retenção ~7)")
    ap.add_argument("--future", type=int, default=14, help="dias futuros (odds ~1-14 antes)")
    ap.add_argument("--buffer", type=int, default=2000, help="para quando a cota chegar aqui")
    ap.add_argument("--all-leagues", action="store_true", help="ignora o filtro de ligas do modelo")
    ap.add_argument("--scope", choices=("selecao", "clube", "ambos"), default="ambos",
                    help="quais ligas entram no alvo (default: ambos)")
    args = ap.parse_args()

    key = load_key()
    leagues = set() if args.all_leagues else _resolve_leagues(args.scope)
    con = _init_db()

    today = dt.date.today()
    day = today.isoformat()
    days = [today + dt.timedelta(days=d) for d in range(-args.past, args.future + 1)]

    ja_hoje = _already_collected_today(con, day)
    print(f"Escopo: {args.scope} | ligas-alvo: {len(leagues) or 'TODAS'} | "
          f"janela: -{args.past}..+{args.future} dias | "
          f"{len(ja_hoje)} fixtures já coletadas hoje serão puladas")

    n_fix = n_rows = n_pulados = 0
    for d in days:
        if _HAS_QUOTA and quota_tracker.remaining() <= args.buffer:
            print(f"[AVISO] cota perto do limite ({quota_tracker.remaining()}) — parando.")
            break
        try:
            fixtures = _fixtures_on(d.isoformat(), key, leagues)
        except requests.RequestException as e:
            print(f"  {d}: erro ao listar fixtures ({e}) — pulando")
            continue
        for meta in fixtures:
            if meta["fixture_id"] in ja_hoje:
                n_pulados += 1
                continue
            if _HAS_QUOTA and quota_tracker.remaining() <= args.buffer:
                print(f"[AVISO] cota perto do limite — parando no meio de {d}.")
                con.close()
                _summary(con_path=DB_PATH, n_fix=n_fix, n_rows=n_rows, n_pulados=n_pulados)
                return
            try:
                j = _api_get("/odds", key, fixture=meta["fixture_id"])
            except requests.RequestException:
                continue
            resp = j.get("response", [])
            if not resp:
                continue
            parsed = parse_fixture_odds(resp[0])
            if parsed:
                n_rows += _store(con, meta, parsed, day)
                n_fix += 1
                ja_hoje.add(meta["fixture_id"])
        print(f"  {d.isoformat()}: {len(fixtures)} fixtures da(s) liga(s)-alvo processados "
              f"(acumulado: {n_fix} com odds, {n_rows} linhas, {n_pulados} pulados)")
        time.sleep(0.2)

    con.close()
    _summary(con_path=DB_PATH, n_fix=n_fix, n_rows=n_rows, n_pulados=n_pulados)


def _summary(con_path: Path, n_fix: int, n_rows: int, n_pulados: int = 0) -> None:
    con = sqlite3.connect(con_path)
    print(f"\n=== Backfill concluído: {n_fix} fixtures com odds, {n_rows} linhas "
          f"novas/atualizadas, {n_pulados} pulados (já coletados hoje) ===")
    for market, cnt in con.execute(
            "SELECT market, COUNT(DISTINCT fixture_id) FROM odds_history GROUP BY market ORDER BY 2 DESC"):
        print(f"  {market:22s} {cnt} fixtures")
    if _HAS_QUOTA:
        print(f"cota restante: {quota_tracker.remaining()}")
    con.close()


if __name__ == "__main__":
    main()
