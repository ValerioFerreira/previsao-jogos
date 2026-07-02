#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/settle_bets.py
==============================
Liquidação das apostas com partida encerrada (uso agendado, ex.: Task Scheduler a cada
30 min). Consome o crédito das vencedoras e estorna o das não vencedoras, respeitando o
delay de segurança. Idempotente. Alternativa ao endpoint POST /api/cron/settle-bets.

Uso: cd backend && .venv/Scripts/python scripts/settle_bets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import SessionLocal
from app.domains.bets.results import get_result_provider
from app.domains.bets.settlement import run_due_settlements


def main() -> None:
    db = SessionLocal()
    try:
        res = run_due_settlements(db, get_result_provider())
        print("liquidacao:", res, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
