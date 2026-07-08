#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/send_test_email.py
==========================
Envia um e-mail de teste usando exatamente o mesmo adapter que o cadastro usa
(`app.core.email`), lendo a mesma configuração (`backend/.env` ou o ambiente).

Existe para que a configuração da Zoho seja validada ANTES de um usuário real
tentar se cadastrar. Sem isso, o primeiro sinal de que o token está errado, o
domínio não está verificado ou o SPF/DKIM não propagou é um 502 na cara do usuário
(ou, com EMAIL_PROVIDER=mock, um cadastro que "dá certo" e nunca entrega o código).

Uso:
    cd backend
    python -m scripts.send_test_email voce@seudominio.com

Saída: imprime o provider usado, o remetente e o resultado. Código de saída != 0
em qualquer falha, para poder ser usado em CI ou num check de deploy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# permite rodar tanto como `python -m scripts.send_test_email` quanto direto
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings          # noqa: E402
from app.core.email import EmailSendError, get_email_sender  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Envia um e-mail de teste pelo adapter do cadastro.")
    ap.add_argument("destinatario", help="endereço que vai receber o teste")
    args = ap.parse_args()

    provider = (settings.email_provider or "mock").lower()
    print(f"  APP_ENV        = {settings.app_env}")
    print(f"  EMAIL_PROVIDER = {provider}")
    print(f"  EMAIL_FROM     = {settings.email_from_name} <{settings.email_from}>")
    if provider == "zeptomail":
        tok = settings.zeptomail_token
        print(f"  ZEPTOMAIL_BASE_URL = {settings.zeptomail_base_url}")
        print(f"  ZEPTOMAIL_TOKEN    = {'(vazio!)' if not tok else tok[:6] + '…' + f' ({len(tok)} chars)'}")
    elif provider == "smtp":
        print(f"  SMTP = {settings.smtp_user}@{settings.smtp_host}:{settings.smtp_port} "
              f"(starttls={settings.smtp_starttls})")

    if provider == "mock":
        print("\n  AVISO: EMAIL_PROVIDER=mock — nada será entregue de verdade.")
        print("         Defina EMAIL_PROVIDER=zeptomail (ou smtp) para testar a Zoho.\n")

    print(f"\n>> enviando para {args.destinatario} ...")
    try:
        get_email_sender().send(
            args.destinatario,
            "Teste de configuração — ApostAI",
            "Se você recebeu este e-mail, o envio transacional está funcionando.\n"
            "Os códigos de verificação de cadastro chegarão por este mesmo caminho.",
        )
    except EmailSendError as e:
        print(f"\n  FALHOU: {e}")
        print("\n  Checklist: domínio verificado na Zoho? SPF e DKIM publicados no DNS?")
        print("  EMAIL_FROM pertence ao domínio verificado? Token é o 'Send Mail Token'?")
        print("  Conta na UE? Então ZEPTOMAIL_BASE_URL=https://api.zeptomail.eu")
        return 1

    print("\n  OK — entregue ao provedor. Confira a caixa de entrada (e o spam).")
    if provider != "mock":
        print("  Se não chegar, veja os logs de entrega no painel do ZeptoMail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
