"""Rate limiting leve em memória (janela deslizante) para endpoints sensíveis
(cadastro, login, reenvio de OTP). Chave = rota + identificador (IP/e-mail).

Nota de escala: em memória não compartilha estado entre múltiplos workers/instâncias.
Para produção multi-worker, trocar por backend Redis (mesma interface `hit()`).
O lockout por conta (anti-brute-force de senha) é persistido no usuário (locked_until),
independente deste limiter.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.core.config import settings

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def hit(key: str, max_events: int, window_sec: int | None = None) -> None:
    """Registra um evento; levanta 429 se exceder `max_events` na janela."""
    window = window_sec or settings.rate_limit_window_sec
    now = time.monotonic()
    with _lock:
        dq = _hits[key]
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= max_events:
            retry = int(window - (now - dq[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas tentativas. Tente novamente em instantes.",
                headers={"Retry-After": str(max(retry, 1))},
            )
        dq.append(now)


def reset(key: str) -> None:
    with _lock:
        _hits.pop(key, None)
