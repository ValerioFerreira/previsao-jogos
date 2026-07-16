#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/invoice_poll.py
================================
Reconsulta no provedor de nota fiscal (ex.: NFE.io) os documentos ainda "pending"
(emissão assíncrona) e persiste a transição de status. Uso agendado (ex.: Task
Scheduler a cada 15-30 min). Idempotente. Alternativa ao endpoint
POST /api/cron/poll-invoices.

Uso: cd backend && .venv/Scripts/python scripts/invoice_poll.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import SessionLocal
from app.domains.payments.service import poll_pending_invoices


def main() -> None:
    db = SessionLocal()
    try:
        res = poll_pending_invoices(db)
        print("poll_invoices:", res, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
