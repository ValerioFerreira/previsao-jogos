#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_signup_flow.py
=============================
Exercita o cadastro INTEIRO sem tocar em produção e sem enviar e-mail de verdade:
SQLite temporário + um servidor HTTP local que finge ser o ZeptoMail e devolve o
corpo da mensagem, de onde o script lê o código OTP.

    register -> e-mail sai -> verify-email -> set-password -> login -> /auth/me

Cobre também os dois comportamentos que não são óbvios e que se perdem numa refatoração:
  - provedor de e-mail fora do ar => HTTP 502 e NENHUM usuário órfão (rollback), porque
    o envio acontece entre o `db.add(OtpCode)` e o `db.commit()` do chamador;
  - depois do 502 o usuário consegue tentar de novo na hora (o cooldown de reenvio de
    60s não fica travado por um código que nunca chegou).

Uso:
    cd backend
    python -m scripts.verify_signup_flow          # exit 0 = tudo passou

Não precisa de DATABASE_URL, token da Zoho, nem rede. Requer as deps de
backend/requirements.txt instaladas (fastapi, sqlalchemy, argon2-cffi, PyJWT, httpx).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# --------------------------------------------------- ZeptoMail falso (captura o e-mail)
_inbox: list[dict] = []
_state: dict = {}


class _FakeZepto(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if _state.get("down"):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"indisponivel"}')
            return
        _inbox.append(body)
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"message":"OK"}')

    def log_message(self, *a):  # silencia o log do http.server
        pass


def main() -> int:
    srv = HTTPServer(("127.0.0.1", 0), _FakeZepto)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    db_path = Path(tempfile.mkdtemp(prefix="verify_signup_")) / "e2e.sqlite"
    # Precisa vir ANTES de importar app.core.config / app.db.connection.
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "APP_ENV": "development",
        "JWT_SECRET": "verificacao-local-nao-e-segredo",
        "EMAIL_PROVIDER": "zeptomail",
        "ZEPTOMAIL_TOKEN": "token-falso",
        "ZEPTOMAIL_BASE_URL": f"http://127.0.0.1:{srv.server_port}",
        "EMAIL_FROM": "no-reply@exemplo.com",
    })

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.core.rate_limit as rate_limit
    from app.db.base import Base, SessionLocal, engine
    # importa TODOS os modelos (registro central) para o create_all enxergar todas as
    # tabelas app_* e resolver as FKs entre domínios (ex.: app_coupons.affiliate_id ->
    # app_affiliates). Importar um subconjunto quebra a resolução de FK no create_all.
    import app.db.models  # noqa: F401
    from app.domains.auth.router import router as auth_router
    from app.domains.users.models import User

    Base.metadata.create_all(engine)
    api = FastAPI()
    api.include_router(auth_router)
    client = TestClient(api, raise_server_exceptions=False)

    falhas: list[str] = []

    def check(nome: str, ok: bool, extra: str = "") -> None:
        print(f"{'  OK ' if ok else '  XX '} {nome}{'' if ok else '  <-- ' + extra}")
        if not ok:
            falhas.append(nome)

    def total_usuarios() -> int:
        s = SessionLocal()
        try:
            return s.query(User).count()
        finally:
            s.close()

    CAD = dict(full_name="Maria Souza", email="maria@teste.com",
               cpf="52998224725", phone="11987654321")
    OUTRO = dict(CAD, email="joao@teste.com", cpf="15350946056", phone="11912345678")
    SENHA = "SenhaForte!234"

    print("\n[1] register -> 201 e o e-mail sai pelo adapter ZeptoMail")
    r = client.post("/auth/register", json=CAD)
    check("HTTP 201", r.status_code == 201, f"{r.status_code} {r.text[:180]}")
    check("um e-mail enviado", len(_inbox) == 1, str(len(_inbox)))
    check("destinatário correto",
          bool(_inbox) and _inbox[-1]["to"][0]["email_address"]["address"] == CAD["email"])
    check("assunto de verificação",
          bool(_inbox) and _inbox[-1]["subject"] == "Seu código de verificação")
    check("usuário persistido", total_usuarios() == 1, str(total_usuarios()))
    if not _inbox:
        print("\n  abortando: nenhum e-mail capturado")
        return 1
    codigo = re.search(r"(\d{6})", _inbox[-1]["textbody"]).group(1)

    print("\n[2] verify-email: código errado barra, código certo devolve setup_token")
    r = client.post("/auth/verify-email", json={"email": CAD["email"], "code": "000000"})
    check("código errado rejeitado", r.status_code >= 400, str(r.status_code))
    r = client.post("/auth/verify-email", json={"email": CAD["email"], "code": codigo})
    check("código certo -> 200", r.status_code == 200, f"{r.status_code} {r.text[:180]}")
    setup_token = r.json().get("setup_token") if r.status_code == 200 else None
    check("setup_token devolvido", bool(setup_token))

    print("\n[3] set-password -> conta ativa + tokens")
    r = client.post("/auth/set-password", json={"setup_token": setup_token, "password": SENHA})
    check("HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:220]}")
    if r.status_code == 200:
        j = r.json()
        check("access_token", bool(j.get("access_token")))
        check("refresh_token", bool(j.get("refresh_token")))
        check("status = active", j["user"]["status"] == "active", str(j["user"]["status"]))

    print("\n[4] login com a senha criada + /auth/me")
    r = client.post("/auth/login", json={"email": CAD["email"], "password": SENHA})
    check("login 200", r.status_code == 200, f"{r.status_code} {r.text[:180]}")
    access = r.json()["access_token"] if r.status_code == 200 else ""
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    check("/auth/me 200", r.status_code == 200, str(r.status_code))

    print("\n[5] provedor de e-mail fora do ar -> 502 e nenhum usuário órfão")
    rate_limit._hits.clear()
    _state["down"] = True
    antes = total_usuarios()
    r = client.post("/auth/register", json=OUTRO)
    check("HTTP 502 (não 500)", r.status_code == 502, f"{r.status_code} {r.text[:180]}")
    check("mensagem amigável", "Não foi possível enviar" in r.text, r.text[:110])
    check("rollback: nenhum usuário criado", total_usuarios() == antes,
          f"{antes} -> {total_usuarios()}")
    _state["down"] = False

    print("\n[6] e-mail volta -> usuário consegue tentar de novo na hora")
    r = client.post("/auth/register", json=OUTRO)
    check("retry -> 201", r.status_code == 201, f"{r.status_code} {r.text[:180]}")
    check("usuário agora criado", total_usuarios() == antes + 1, str(total_usuarios()))

    print("\n[7] rate limit do register (5 por IP / 5 min)")
    rate_limit._hits.clear()
    codes = [client.post("/auth/register", json=dict(CAD, email=f"x{i}@t.com")).status_code
             for i in range(7)]
    check("429 aparece após o limite", 429 in codes, str(codes))

    srv.shutdown()
    print("\n" + "=" * 56)
    print("FALHAS: " + ", ".join(falhas) if falhas else "CADASTRO PONTA A PONTA: TUDO PASSOU")
    print("=" * 56)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
