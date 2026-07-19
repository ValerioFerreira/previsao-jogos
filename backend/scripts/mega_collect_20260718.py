#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/mega_collect_20260718.py
=================================
Orquestrador da coleta noturna de 2026-07-18/19 -- pedida pelo usuário pra usar a
cota diária inteira (75k) assim que ela resetar (21h BRT / 00h UTC), antes da
assinatura da api-football precisar ser renovada.

Fluxo:
  0. Espera o reset diário (poll de /status, não gasta cota) -- não confia só no
     relógio, confirma pelo `requests.current` caindo.
  1. FASE A (prioridade máxima) -- jogos futuros dos DOIS escopos, TODAS as
     competições treinadas, janela de enumeração longa (270 dias -- o quanto der);
     odds só tentadas dentro de ~16 dias (fora disso a api-football sempre volta
     vazia). Todo jogo descoberto é gravado no registry (visível no seletor
     "Partida Agendada"), com ou sem odds.
  2. FASE B -- o RESTANTE da cota vai pro backfill histórico priorizado
     (backfill_history_priority.py): Brasileirão A/B, Copa do Brasil, Champions,
     Premier, La Liga esgotadas em ordem; depois todas as outras ligas rastreadas,
     com o download de detalhe (a parte cara) ordenado globalmente por Elo dos times.

Roda como processo de background próprio (não depende da sessão do agente que o
lançou) -- log incremental em data/mega_collect_log.jsonl, resumível.

Uso:
  python scripts/mega_collect_20260718.py                  # espera o reset, roda tudo
  python scripts/mega_collect_20260718.py --skip-wait       # roda já (teste/retomada)
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests  # noqa: E402
from scripts.fetch_odds import BASE, load_key  # noqa: E402
from scripts import quota_tracker  # noqa: E402

LOG_PATH = ROOT / "data" / "mega_collect_log.jsonl"


def log(**event):
    event["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = json.dumps(event, ensure_ascii=False)
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def check_status() -> tuple[int, int, str]:
    key = load_key()
    r = requests.get(BASE + "/status", headers={"x-apisports-key": key}, timeout=20)
    r.raise_for_status()
    d = r.json()["response"]
    return int(d["requests"]["current"]), int(d["requests"]["limit_day"]), d["subscription"]["end"]


def wait_for_reset(poll_seconds: int, reset_threshold: int) -> str:
    """Poll de /status (não gasta cota) até `current` (usado hoje) cair abaixo de
    `reset_threshold` -- mais seguro que confiar só no relógio."""
    last_used = None
    while True:
        try:
            used, limit, sub_end = check_status()
            if used != last_used:
                log(evento="poll_status", usado=used, limite=limit, assinatura_fim=sub_end)
                last_used = used
            if used < reset_threshold:
                log(evento="cota_resetada", usado=used)
                return sub_end
        except Exception as e:
            log(evento="erro_poll_status", erro=str(e))
        time.sleep(poll_seconds)


def run_phase_a(days: int, odds_window_days: int, quota_buffer: int):
    from scripts import collect_odds_forward, collect_club_odds_forward
    log(evento="fase_a_inicio", dias=days, janela_odds=odds_window_days)
    try:
        r1 = collect_odds_forward.collect(days, False, odds_window_days, quota_buffer)
        log(evento="fase_a_selecao_fim", jogos_vistos=r1["jogos_vistos"], odds_coletadas=r1["odds_coletadas"],
            cota_restante=r1["cota_restante"], parou_por_cota=r1["parou_por_cota"])
    except Exception as e:
        log(evento="fase_a_selecao_erro", erro=str(e), trace=traceback.format_exc())
    try:
        r2 = collect_club_odds_forward.collect(days, False, quota_buffer, odds_window_days)
        log(evento="fase_a_clube_fim", jogos_vistos=r2["jogos_vistos"], odds_coletadas=r2["odds_coletadas"],
            cota_restante=r2["cota_restante"], parou_por_cota=r2["parou_por_cota"])
    except Exception as e:
        log(evento="fase_a_clube_erro", erro=str(e), trace=traceback.format_exc())
    log(evento="fase_a_fim")


def run_phase_b(margin: int):
    from scripts import backfill_history_priority as bhp
    log(evento="fase_b_inicio")
    bhp.ensure_table()
    have = bhp.cached_ids()
    logger = bhp.Logger(LOG_PATH)
    budget = bhp.Budget(max_calls=200000, margin=margin)  # teto de chamadas essencialmente irrestrito -- quem governa é a cota real (headers ao vivo)
    tier1 = bhp.backfill_priority_tier(have, budget, logger, 2026, 2015)
    tier2 = []
    if budget.ok():
        tier2 = bhp.backfill_remaining_tier(have, budget, logger, 2026, 2018)
    else:
        log(evento="fase_b_tier2_pulado", motivo=budget.stopped)
    completas = [r["liga"] for r in (tier1 + tier2) if r.get("completa")]
    log(evento="fase_b_fim", chamadas=budget.calls, cota_restante=budget.remaining,
        parou_por=budget.stopped, ligas_completas=len(completas), lista=completas)
    return completas, tier1, tier2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wait", action="store_true", help="não espera reset -- roda já (teste/retomada)")
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--reset-threshold", type=int, default=2000, help="considera resetado quando `current` (usado) cair abaixo disso")
    ap.add_argument("--days", type=int, default=270)
    ap.add_argument("--odds-window-days", type=int, default=16)
    ap.add_argument("--quota-buffer", type=int, default=150)
    a = ap.parse_args()

    log(evento="orquestrador_inicio", args=vars(a))

    if a.skip_wait:
        used, limit, sub_end = check_status()
        log(evento="skip_wait", usado=used, assinatura_fim=sub_end)
    else:
        sub_end = wait_for_reset(a.poll_seconds, a.reset_threshold)
        used, limit, _ = check_status()

    quota_tracker.init(used_at_start=used, daily_limit=limit)
    log(evento="quota_tracker_init", usado_at_start=used, limite_diario=limit)

    completas: list[str] = []
    try:
        run_phase_a(a.days, a.odds_window_days, a.quota_buffer)
    except Exception as e:
        log(evento="fase_a_erro_fatal", erro=str(e), trace=traceback.format_exc())

    try:
        completas, tier1, tier2 = run_phase_b(a.quota_buffer)
    except Exception as e:
        log(evento="fase_b_erro_fatal", erro=str(e), trace=traceback.format_exc())

    try:
        used_final, limit_final, _ = check_status()
    except Exception:
        used_final = limit_final = None

    log(evento="orquestrador_fim", ligas_completas=len(completas), lista_final=completas,
        cota_usada_final=used_final, cota_limite=limit_final)
    print("\n=== COLETA NOTURNA CONCLUÍDA ===")
    print(f"Ligas históricas completas nesta rodada: {len(completas)}")
    for n in completas:
        print(f"  - {n}")
    if used_final is not None:
        print(f"Cota usada: {used_final}/{limit_final}")


if __name__ == "__main__":
    main()
