#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/quota_tracker.py
=========================
Cota DIÁRIA compartilhada entre os coletores (collect_odds_forward,
collect_club_odds_forward, prefetch_clubs/backfill_history_priority).

Bug que isso corrige: cada coletor usava o header `x-ratelimit-requests-remaining`
da api-football como se fosse a cota DIÁRIA restante -- mas esse header é o limite
POR MINUTO (450/min), que sobe e desce dentro de qualquer minuto de uso sustentado.
Comparar esse valor contra um `quota_buffer`/`margin` de 50-150 fazia o coletor
parar por engano após poucos milhares de chamadas, achando que a cota diária
(75000) tinha acabado quando só o burst do minuto corrente tinha esvaziado
(recupera sozinho no minuto seguinte).

Fix: um contador de processo, inicializado 1x via GET /status (não custa cota) com
o `current` (usado hoje) e `limit_day` reais, incrementado a cada chamada real feita
por QUALQUER um dos coletores neste processo -- a cota diária restante é sempre
`limit_day - used_at_start - calls_neste_processo`.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_daily_limit: int | None = None
_used_at_start: int | None = None
_calls = 0

_rl_lock = threading.Lock()
_rl_window_start: float | None = None
_rl_window_count = 0
_rl_next_slot: float | None = None
PER_MINUTE_CAP = 380  # abaixo do limite real da api-football (450/min) -- margem maior
                       # p/ absorver jitter de 16 workers (440 ainda gerava 429 esporadicos)
MIN_GAP = 60.0 / PER_MINUTE_CAP  # espaçamento minimo entre chamadas -- evita rajada


def throttle() -> None:
    """Rate-limit GLOBAL (across threads, mesmo processo) -- janela fixa de 60s
    (nunca ultrapassa PER_MINUTE_CAP/janela) + espaçamento mínimo entre chamadas
    (MIN_GAP), pra não liberar rajada instantânea até o teto -- com 16 workers em
    paralelo, uma janela "solta" deixava várias dezenas de chamadas saírem quase
    juntas (limite por-SEGUNDO da api-football estourava -> 429), mesmo respeitando
    o total por minuto. Múltiplas chamadas seguem em voo (workers != 1), só a
    LIBERAÇÃO de cada uma é espaçada."""
    wait = 0.0
    with _rl_lock:
        global _rl_window_start, _rl_window_count, _rl_next_slot
        now = time.monotonic()
        if _rl_window_start is None or now - _rl_window_start >= 60:
            _rl_window_start = now
            _rl_window_count = 0
        _rl_window_count += 1
        if _rl_window_count > PER_MINUTE_CAP:
            wait = max(60 - (now - _rl_window_start), 0.0)
        else:
            slot = max(now, _rl_next_slot or now)
            wait = max(slot - now, 0.0)
            _rl_next_slot = slot + MIN_GAP
    if wait:
        time.sleep(wait)
    with _rl_lock:
        if _rl_window_count > PER_MINUTE_CAP:
            _rl_window_start = time.monotonic()
            _rl_window_count = 1
            _rl_next_slot = time.monotonic() + MIN_GAP


def _bootstrap() -> None:
    global _daily_limit, _used_at_start
    from scripts.fetch_odds import BASE, load_key
    import requests
    r = requests.get(BASE + "/status", headers={"x-apisports-key": load_key()}, timeout=20)
    r.raise_for_status()
    d = r.json()["response"]
    _used_at_start = int(d["requests"]["current"])
    _daily_limit = int(d["requests"]["limit_day"])


def init(used_at_start: int, daily_limit: int) -> None:
    """Chamar 1x no início do orquestrador (após confirmar reset), com valores
    frescos de /status. Reseta o contador de chamadas do processo."""
    global _daily_limit, _used_at_start, _calls
    with _lock:
        _used_at_start = used_at_start
        _daily_limit = daily_limit
        _calls = 0


def note_call() -> None:
    """Chamar após CADA chamada real à api-football (qualquer endpoint que gasta
    cota diária -- /status não conta, os coletores não a chamam)."""
    global _calls
    with _lock:
        if _used_at_start is None:
            _bootstrap()
        _calls += 1


def remaining() -> int:
    with _lock:
        if _used_at_start is None:
            _bootstrap()
        return _daily_limit - _used_at_start - _calls


def calls_made() -> int:
    with _lock:
        return _calls
