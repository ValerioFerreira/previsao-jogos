#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/apiclient.py
===============================
Cliente HTTP da API-Football v3 com: cache idempotente por chave (em disco),
rate-limit (450/min), retomada (pula o que ja existe no cache), backoff, e teto
duro de requests para nao estourar a cota. Toda coleta da arquitetura paralela
passa por aqui. Le APIFOOTBALL_KEY do .env da raiz. Nao toca producao.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "player_ranking" / "data" / "raw"
BASE = "https://v3.football.api-sports.io"


def load_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("APIFOOTBALL_KEY"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("APIFOOTBALL_KEY ausente no .env da raiz.")


class ApiClient:
    def __init__(self, max_requests=60000, per_minute=450):
        self.key = load_key()
        self.max_requests = max_requests
        self.min_interval = 60.0 / per_minute     # ~0.133s
        self.n_live = 0                            # chamadas reais (nao-cache)
        self.n_cache = 0
        self.remaining = None
        self._last = 0.0

    def _throttle(self):
        dt = time.time() - self._last
        if dt < self.min_interval:
            time.sleep(self.min_interval - dt)
        self._last = time.time()

    def get(self, path: str, cache_key: str, **params):
        """path ex: '/players'. cache_key ex: 'players_profile/2025/12345'.
        Retorna a lista 'response' (cacheada em disco como JSON)."""
        cpath = CACHE / f"{cache_key}.json"
        if cpath.exists():
            self.n_cache += 1
            try:
                return json.loads(cpath.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass  # cache corrompido -> rebaixa
        if self.n_live >= self.max_requests:
            raise BudgetExhausted(f"Teto de {self.max_requests} requests atingido.")
        self._throttle()
        for attempt in range(4):
            try:
                r = requests.get(BASE + path, headers={"x-apisports-key": self.key},
                                 params=params, timeout=30)
                self.n_live += 1
                self.remaining = r.headers.get("x-ratelimit-requests-remaining")
                if r.status_code == 429:  # rate limit -> espera e tenta de novo
                    time.sleep(2 * (attempt + 1))
                    continue
                r.raise_for_status()
                resp = r.json().get("response", [])
                cpath.parent.mkdir(parents=True, exist_ok=True)
                cpath.write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
                return resp
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        return []

    def stats(self):
        return {"live": self.n_live, "cache": self.n_cache, "remaining": self.remaining}


class BudgetExhausted(Exception):
    pass
