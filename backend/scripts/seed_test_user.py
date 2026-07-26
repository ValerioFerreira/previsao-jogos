#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/seed_test_user.py
=================================
Cria (ou reaproveita) uma conta de TESTE já ativa, com e-mail verificado, senha
definida e carteira com um saldo-alvo de créditos. Escreve direto no banco
configurado em `DATABASE_URL` (backend/.env — Neon em produção). Idempotente:
rodar de novo apenas garante o estado final (não duplica usuário nem créditos).

Uso:
  cd backend && .venv/Scripts/python scripts/seed_test_user.py \
      --email teste@gmail.com --password Teste123 --credits 100
Defaults já correspondem ao pedido (teste@gmail.com / Teste123 / 100 créditos).
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core import security
from app.db.base import SessionLocal
from app.domains.enums import CreditTxType, UserRole, UserStatus
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet, post_transaction


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="teste@gmail.com")
    ap.add_argument("--password", default="Teste123")
    ap.add_argument("--credits", type=int, default=100)
    ap.add_argument("--full-name", default="Conta Teste")
    ap.add_argument("--cpf", default="52998224725")      # CPF de teste válido (DV correto)
    ap.add_argument("--phone", default="11999990001")    # DDD 11 + celular (11 dígitos)
    ap.add_argument("--admin", action="store_true", help="também promove a admin")
    args = ap.parse_args()

    email = args.email.lower()
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(
                full_name=args.full_name, email=email, cpf=args.cpf, phone=args.phone,
                status=UserStatus.active, role=UserRole.owner if args.admin else UserRole.user,
                signup_ip="127.0.0.1",
            )
            db.add(user)
            db.flush()
            created = True
        else:
            created = False
            if args.admin:
                user.role = UserRole.owner

        # garante conta plenamente utilizável (login direto, sem OTP)
        user.status = UserStatus.active
        user.email_verified_at = user.email_verified_at or _now()
        user.password_hash = security.hash_password(args.password)
        user.failed_login_count = 0
        user.locked_until = None

        wallet = get_or_create_wallet(db, user.id)

        # ajusta o saldo DISPONÍVEL para exatamente `args.credits` (lançamento no ledger)
        target = Decimal(args.credits)
        delta = target - Decimal(wallet.available_balance)
        if delta != 0:
            post_transaction(
                db,
                wallet=wallet,
                tx_type=CreditTxType.manual_adjustment,
                amount=delta,
                idempotency_key=f"seed:{email}:set-{target}",
                reference_type="admin",
                description=f"Seed de conta de teste: saldo ajustado para {target} créditos.",
            )

        db.commit()
        db.refresh(wallet)
        print(
            f"OK: {'criado' if created else 'atualizado'} {email} "
            f"(status={user.status.value}, role={user.role.value}) | "
            f"saldo={wallet.available_balance} créditos, reservado={wallet.reserved_balance}"
        )
        print(f"Login: {email} / {args.password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
