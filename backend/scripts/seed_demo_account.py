#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/seed_demo_account.py
=====================================
Cria (ou reaproveita) a conta demo COMPARTILHADA usada por parceiros para divulgar a
plataforma — créditos ilimitados (bypass em analysis/service.py::create_analysis via
User.is_demo), login exige e-mail+senha desta conta MAIS o CPF do parceiro (allowlist em
Affiliate.demo_access_enabled, ver POST /auth/login-demo). Idempotente: rodar de novo só
garante o estado final (não duplica). Escreve direto no banco de DATABASE_URL
(backend/.env — Neon em produção).

Uso:
  cd backend && .venv/Scripts/python scripts/seed_demo_account.py \
      --email demo@apostainfo.com.br --password TrocarEssaSenha123
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core import security
from app.db.base import SessionLocal
from app.domains.enums import UserRole, UserStatus
from app.domains.users.models import User
from app.domains.wallet.service import get_or_create_wallet


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="demo@apostainfo.com.br")
    ap.add_argument("--password", required=True)
    ap.add_argument("--full-name", default="Conta Demo — Parceiros")
    ap.add_argument("--cpf", default="52998224725")      # placeholder — não é usado para login (só o e-mail/senha desta conta)
    ap.add_argument("--phone", default="11999990002")
    args = ap.parse_args()

    email = args.email.lower()
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        created = user is None
        if user is None:
            user = User(
                full_name=args.full_name, email=email, cpf=args.cpf, phone=args.phone,
                status=UserStatus.active, role=UserRole.user, signup_ip="127.0.0.1",
            )
            db.add(user)
            db.flush()

        user.is_demo = True
        user.status = UserStatus.active
        user.email_verified_at = user.email_verified_at or _now()
        user.password_hash = security.hash_password(args.password)
        user.failed_login_count = 0
        user.locked_until = None

        get_or_create_wallet(db, user.id)  # não precisa de saldo — is_demo nunca debita

        db.commit()
        print(f"OK: {'criado' if created else 'atualizado'} {email} (is_demo=True)")
        print(f"Credenciais da conta demo: {email} / {args.password}")
        print("Cada parceiro autorizado usa essas credenciais + o próprio CPF em POST /auth/login-demo.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
