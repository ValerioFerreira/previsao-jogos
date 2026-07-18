#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backfill_history_priority.py
=====================================
Backfill histórico de clubes com ORDEM DE PRIORIDADE explícita (pedida pelo usuário
p/ a janela de cota generosa do reset diário 2026-07-18/19):

  1. Brasileirão Série A, Série B, Copa do Brasil, Champions League, Premier League,
     La Liga -- NESSA ORDEM EXATA, cada liga esgotada (todas as temporadas do range)
     antes de passar pra próxima.
  2. TODAS as outras ligas rastreadas (prefetch_clubs.LEAGUES) -- mas o DOWNLOAD DE
     DETALHE (a parte cara, 1 request/partida) é priorizado GLOBALMENTE por
     max(Elo casa, Elo visitante), não por liga: descobre as partidas que faltam de
     TODAS as ligas restantes primeiro (barato, 1 request/liga/temporada), junta tudo
     numa lista só, ordena pelo Elo mais recente dos dois times (elo_history.csv) e
     baixa nessa ordem até a cota acabar. Times sem Elo conhecido (não desambiguados
     no roster treinado) caem pro fim via um piso conservador.

Reaproveita os primitivos de cache de prefetch_clubs.py (mesma tabela
`club_match_detail_cache` + espelho local `data/club_raw_cache.sqlite`) -- resumível
(pula o que já tem), guarda de cota (para na margem) e loga progresso em JSONL.

Uso:
  python scripts/backfill_history_priority.py --max 30000 --margin 200 \
      --log data/mega_collect_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from scripts.prefetch_clubs import LEAGUES, FINISHED, ensure_table, cached_ids, put, _get_throttled  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

PRIORITY_NAMES = [
    "Brasileirao Serie A",
    "Brasileirao Serie B",
    "Copa do Brasil",
    "Champions League",
    "Premier League",
    "La Liga",
]
_BY_NAME = {name: lid for lid, name in LEAGUES}
PRIORITY_LEAGUES = [(_BY_NAME[n], n) for n in PRIORITY_NAMES if n in _BY_NAME]
REMAINING_LEAGUES = [(lid, n) for lid, n in LEAGUES if n not in PRIORITY_NAMES]

DEFAULT_ELO_FALLBACK = 1400.0  # abaixo do p25 observado (~1392) -- time sem Elo conhecido afunda, não flutua


def _team_elo_map() -> dict[str, float]:
    """Elo mais recente por time canônico, de model_artifacts_clubes/elo_history.csv
    (já gerado por build_elo_history.py sobre o dataset de treino completo)."""
    import pandas as pd
    path = ROOT / "model_artifacts_clubes" / "elo_history.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    latest = df.sort_values("date").groupby("team").last()
    return latest["elo"].to_dict()


def _canonical_name_map() -> dict[int, str]:
    """id (api-football) -> nome canônico desambiguado (team_ids do meta.json
    treinado) -- mesmo padrão de collect_club_odds_forward.py::_canonical_name."""
    meta_path = ROOT / "model_artifacts_clubes" / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        team_ids = meta.get("team_ids", {})
    except Exception:
        team_ids = {}
    return {int(tid): name for name, tid in team_ids.items()}


class Logger:
    def __init__(self, path: Path | None):
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **event):
        import datetime
        event["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        line = json.dumps(event, ensure_ascii=False)
        print(line, flush=True)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


class Budget:
    def __init__(self, max_calls: int, margin: int):
        self.max_calls = max_calls
        self.margin = margin
        self.calls = 0
        self.remaining = None
        self.stopped = None

    def note(self, remaining):
        self.calls += 1
        if remaining is not None:
            self.remaining = int(remaining)

    def ok(self) -> bool:
        if self.calls >= self.max_calls:
            self.stopped = "MAX_CALLS"
            return False
        if self.remaining is not None and self.remaining <= self.margin:
            self.stopped = "LIMITE_DIARIO"
            return False
        return True


def backfill_league(league_id: int, nome: str, have: set, budget: Budget, log: Logger,
                     season_from: int, season_to: int) -> dict:
    """Esgota uma liga (todas as temporadas no range, mais recente primeiro).
    Retorna {"completa": bool, "novos": int, "faltam": int}."""
    novos = 0
    faltam_total = 0
    completa = True
    for season in range(season_from, season_to - 1, -1):
        if not budget.ok():
            completa = False
            break
        try:
            fxs, rem = _get_throttled("/fixtures", league=league_id, season=season)
            budget.note(rem)
        except Exception as e:
            log.log(evento="erro_descoberta", liga=nome, temporada=season, erro=str(e))
            completa = False
            continue
        finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
        todo = [f for f in finished if (f.get("fixture") or {}).get("id") not in have]
        if todo:
            log.log(evento="descoberta", liga=nome, temporada=season, encontrados=len(finished), faltam=len(todo))
        for f in todo:
            if not budget.ok():
                completa = False
                faltam_total += len(todo)
                break
            fid = (f.get("fixture") or {}).get("id")
            if not fid:
                continue
            try:
                resp, rem = _get_throttled("/fixtures", id=fid)
                budget.note(rem)
                if resp:
                    put(fid, league_id, season, resp[0])
                    have.add(fid)
                    novos += 1
            except Exception as e:
                log.log(evento="erro_detalhe", liga=nome, fixture=fid, erro=str(e))
    return {"completa": completa, "novos": novos}


def backfill_priority_tier(have: set, budget: Budget, log: Logger, season_from: int, season_to: int) -> list[dict]:
    resultados = []
    for league_id, nome in PRIORITY_LEAGUES:
        if not budget.ok():
            log.log(evento="tier1_parou_antes", liga=nome, motivo=budget.stopped)
            break
        log.log(evento="tier1_inicio", liga=nome)
        r = backfill_league(league_id, nome, have, budget, log, season_from, season_to)
        resultados.append({"liga": nome, **r})
        log.log(evento="tier1_fim", liga=nome, **r)
    return resultados


def backfill_remaining_tier(have: set, budget: Budget, log: Logger, season_from: int, season_to: int) -> list[dict]:
    """Descoberta (barata) de TODAS as ligas restantes primeiro, depois download de
    detalhe (caro) numa fila única ordenada por max(Elo casa, Elo visitante)."""
    elo = _team_elo_map()
    canon = _canonical_name_map()

    def team_elo(name: str | None, tid: int | None) -> float:
        cname = canon.get(tid) if tid is not None else None
        return elo.get(cname or name or "", DEFAULT_ELO_FALLBACK)

    log.log(evento="tier2_descoberta_inicio", ligas=len(REMAINING_LEAGUES), temporadas=f"{season_to}-{season_from}")
    todo_global: list[tuple[float, int, int, int]] = []  # (elo_prio, fixture_id, league_id, season)
    league_todo_count: dict[int, int] = {}

    for league_id, nome in REMAINING_LEAGUES:
        if not budget.ok():
            log.log(evento="tier2_descoberta_parou", motivo=budget.stopped, liga_seguinte=nome)
            break
        for season in range(season_from, season_to - 1, -1):
            if not budget.ok():
                break
            try:
                fxs, rem = _get_throttled("/fixtures", league=league_id, season=season)
                budget.note(rem)
            except Exception as e:
                log.log(evento="erro_descoberta", liga=nome, temporada=season, erro=str(e))
                continue
            finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            for f in finished:
                fid = (f.get("fixture") or {}).get("id")
                if not fid or fid in have:
                    continue
                teams = f.get("teams") or {}
                h, a = teams.get("home") or {}, teams.get("away") or {}
                prio = max(team_elo(h.get("name"), h.get("id")), team_elo(a.get("name"), a.get("id")))
                todo_global.append((prio, fid, league_id, season))
                league_todo_count[league_id] = league_todo_count.get(league_id, 0) + 1

    log.log(evento="tier2_descoberta_fim", partidas_faltando=len(todo_global), cota_restante=budget.remaining)

    todo_global.sort(key=lambda t: -t[0])
    league_baixados: dict[int, int] = {}
    for prio, fid, league_id, season in todo_global:
        if not budget.ok():
            log.log(evento="tier2_detalhe_parou", motivo=budget.stopped, partidas_restantes=len(todo_global))
            break
        try:
            resp, rem = _get_throttled("/fixtures", id=fid)
            budget.note(rem)
            if resp:
                put(fid, league_id, season, resp[0])
                have.add(fid)
                league_baixados[league_id] = league_baixados.get(league_id, 0) + 1
        except Exception as e:
            log.log(evento="erro_detalhe", fixture=fid, erro=str(e))

    resultados = []
    for league_id, nome in REMAINING_LEAGUES:
        total = league_todo_count.get(league_id, 0)
        baixados = league_baixados.get(league_id, 0)
        resultados.append({"liga": nome, "completa": baixados >= total, "novos": baixados, "faltavam": total})
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=100000)
    ap.add_argument("--margin", type=int, default=150)
    ap.add_argument("--priority-season-from", type=int, default=2026)
    ap.add_argument("--priority-season-to", type=int, default=2015)
    ap.add_argument("--remaining-season-from", type=int, default=2026)
    ap.add_argument("--remaining-season-to", type=int, default=2018)
    ap.add_argument("--log", type=str, default="data/mega_collect_log.jsonl")
    a = ap.parse_args()

    ensure_table()
    have = cached_ids()
    log = Logger(ROOT / a.log if a.log else None)
    budget = Budget(a.max, a.margin)

    log.log(evento="inicio", ja_em_cache=len(have),
            tier1=[n for _, n in PRIORITY_LEAGUES], tier2_ligas=len(REMAINING_LEAGUES))

    tier1 = backfill_priority_tier(have, budget, log, a.priority_season_from, a.priority_season_to)
    tier2 = []
    if budget.ok():
        tier2 = backfill_remaining_tier(have, budget, log, a.remaining_season_from, a.remaining_season_to)
    else:
        log.log(evento="tier2_pulado", motivo=budget.stopped)

    completas = [r["liga"] for r in (tier1 + tier2) if r.get("completa")]
    log.log(evento="fim", chamadas=budget.calls, cota_restante=budget.remaining, parou_por=budget.stopped,
            ligas_completas=len(completas), lista_ligas_completas=completas,
            tier1=tier1, tier2=tier2)
    print(f"\n>> Backfill: {budget.calls} chamadas | cota restante ~{budget.remaining} | "
          f"parou por: {budget.stopped or 'FIM (tudo coberto)'}")
    print(f">> Ligas completas: {len(completas)}/{len(PRIORITY_LEAGUES) + len(REMAINING_LEAGUES)}")
    for n in completas:
        print(f"   - {n}")


if __name__ == "__main__":
    main()
