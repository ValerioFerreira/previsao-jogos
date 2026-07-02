#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/make_admin.py
=============================
Promove um usuário (por e-mail) a admin (ou superadmin). Usa a DATABASE_URL do
backend/.env (Neon em produção). Requer que o usuário já exista (cadastrado/ativo).

Uso:
  cd backend && .venv/Scripts/python scripts/make_admin.py email@dominio.com [--super]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.base import SessionLocal
from app.domains.enums import UserRole
from app.domains.users.models import User


def main() -> None:
    if len(sys.argv) < 2:
        print("uso: make_admin.py email@dominio.com [--super]"); sys.exit(1)
    email = sys.argv[1].lower()
    role = UserRole.superadmin if "--super" in sys.argv else UserRole.admin
    db = SessionLocal()
    try:
        u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if u is None:
            print(f"[erro] usuário não encontrado: {email}"); sys.exit(2)
        u.role = role
        db.commit()
        print(f"OK: {email} agora é {role.value}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
