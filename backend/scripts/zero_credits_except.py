#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/zero_credits_except.py
=======================================
Zera o saldo (disponível + reservado) de TODAS as carteiras, exceto as dos e-mails
informados — via lançamento no ledger (`manual_adjustment`, auditável), nunca por UPDATE
direto na tabela. Usa a DATABASE_URL do backend/.env (Neon em produção).

Por padrão roda em modo `--dry-run` (só imprime o que faria). É preciso passar `--apply`
explicitamente para gravar de verdade — isto mexe em saldo real de contas de terceiros.

Uso:
  cd backend && .venv/Scripts/python scripts/zero_credits_except.py email1@x.com email2@y.com
  cd backend && .venv/Scripts/python scripts/zero_credits_except.py email1@x.com email2@y.com --apply
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.base import SessionLocal
from app.domains.enums import CreditTxType
from app.domains.users.models import User
from app.domains.wallet.models import Wallet
from app.domains.wallet.service import post_transaction


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_ = "--apply" in sys.argv
    if not args:
        print("uso: zero_credits_except.py email1@x.com [email2@y.com ...] [--apply]")
        sys.exit(1)
    exceptions = {e.strip().lower() for e in args}

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Wallet, User).join(User, User.id == Wallet.user_id)
        ).all()

        touched, skipped, total_available, total_reserved = 0, 0, Decimal("0"), Decimal("0")
        for wallet, user in rows:
            if user.email.lower() in exceptions:
                skipped += 1
                continue
            avail = Decimal(wallet.available_balance)
            resv = Decimal(wallet.reserved_balance)
            if avail == 0 and resv == 0:
                continue
            touched += 1
            total_available += avail
            total_reserved += resv
            print(f"{'[APLICANDO]' if apply_ else '[dry-run]'} {user.email}: "
                  f"disponível {avail} -> 0, reservado {resv} -> 0")
            if apply_:
                post_transaction(
                    db, wallet=wallet, tx_type=CreditTxType.manual_adjustment,
                    amount=-avail, reserved_delta=-resv,
                    idempotency_key=f"zero-credits:{wallet.id}",
                    reference_type="admin", description="Reset de créditos pré-lançamento",
                )

        print(f"\nResumo: {touched} conta(s) afetada(s), {skipped} conta(s) preservada(s) "
              f"(exceções), {total_available} créditos disponíveis e {total_reserved} "
              f"reservados removidos no total.")
        if apply_:
            db.commit()
            print("Gravado.")
        else:
            print("Modo dry-run — nada foi gravado. Rode de novo com --apply para aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
