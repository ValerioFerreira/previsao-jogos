#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_startup_config.py
=================================
Confere que `validate_startup_config()` derruba o boot (ConfigError) em
APP_ENV=production quando Mercado Pago/NFE.io estão declarados mas mal
configurados, e que em desenvolvimento vira só aviso — sem precisar subir o
servidor de verdade. Cobre os dois guardas novos (`_payment_problems`,
`_invoice_problems`) do mesmo jeito que os de e-mail/JWT já eram cobertos
manualmente antes.

Uso:
    cd backend
    python -m scripts.verify_startup_config     # exit 0 = tudo passou
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("EMAIL_PROVIDER", "zeptomail")
os.environ.setdefault("ZEPTOMAIL_TOKEN", "token-falso")
os.environ.setdefault("EMAIL_FROM", "no-reply@dominio-verificado.com")
os.environ.setdefault("JWT_SECRET", "verificacao-local-nao-e-segredo")

import app.core.startup as startup
from app.core.config import Settings

falhas: list[str] = []


def check(nome: str, ok: bool, extra: str = "") -> None:
    print(f"{'  OK ' if ok else '  XX '} {nome}{'' if ok else '  <-- ' + extra}")
    if not ok:
        falhas.append(nome)


def cenario(nome: str, **overrides) -> tuple[bool, list[str]]:
    """Constrói um Settings isolado (kwargs explícitos vencem env/.env) e roda a
    validação contra ele, sem afetar o singleton global `settings`."""
    base = dict(
        app_env="production", jwt_secret="segredo-de-producao-de-verdade",
        email_provider="zeptomail", zeptomail_token="token-real",
        email_from="no-reply@dominio-verificado.com",
    )
    base.update(overrides)
    fake_settings = Settings(**base)
    original = startup.settings
    startup.settings = fake_settings
    try:
        try:
            startup.validate_startup_config()
            return True, []
        except startup.ConfigError as e:
            return False, str(e).splitlines()[1:]
    finally:
        startup.settings = original


print("\n[1] payment_provider=mock em produção -> ConfigError")
ok, problemas = cenario("mock", payment_provider="mock")
check("boot falha", not ok)
check("menciona PAYMENT_PROVIDER", any("PAYMENT_PROVIDER" in p for p in problemas), str(problemas))

print("\n[2] payment_provider=mercadopago sem credenciais -> ConfigError listando cada uma")
ok, problemas = cenario("mp_sem_credencial", payment_provider="mercadopago")
check("boot falha", not ok)
check("acusa MP_ACCESS_TOKEN", any("MP_ACCESS_TOKEN" in p for p in problemas), str(problemas))
check("acusa MP_PUBLIC_KEY", any("MP_PUBLIC_KEY" in p for p in problemas), str(problemas))
check("acusa MP_WEBHOOK_SECRET", any("MP_WEBHOOK_SECRET" in p for p in problemas), str(problemas))

print("\n[3] payment_provider=mercadopago com todas as credenciais -> boot OK")
ok, problemas = cenario(
    "mp_completo", payment_provider="mercadopago",
    mp_access_token="APP_USR-real", mp_public_key="APP_USR-real", mp_webhook_secret="segredo-real",
    invoice_provider="noop",
)
check("boot passa", ok, str(problemas))

print("\n[4] invoice_provider=nfeio sem dados fiscais -> ConfigError listando cada campo")
ok, problemas = cenario(
    "nfeio_incompleto", payment_provider="mercadopago",
    mp_access_token="x", mp_public_key="x", mp_webhook_secret="x",
    invoice_provider="nfeio",
)
check("boot falha", not ok)
check("acusa NFEIO_API_TOKEN", any("NFEIO_API_TOKEN" in p for p in problemas), str(problemas))
check("acusa COMPANY_CNPJ", any("COMPANY_CNPJ" in p for p in problemas), str(problemas))

print("\n[5] invoice_provider=nfeio com todos os dados -> boot OK")
ok, problemas = cenario(
    "nfeio_completo", payment_provider="mercadopago",
    mp_access_token="x", mp_public_key="x", mp_webhook_secret="x",
    invoice_provider="nfeio", nfeio_api_token="x", nfeio_company_id="x",
    company_cnpj="12345678000199", company_razao_social="ApostAI LTDA",
    company_inscricao_municipal="12345", company_city_service_code="0107",
)
check("boot passa", ok, str(problemas))

print("\n[6] invoice_provider=noop em produção -> NÃO derruba o boot (só aviso)")
ok, problemas = cenario(
    "noop_em_producao", payment_provider="mercadopago",
    mp_access_token="x", mp_public_key="x", mp_webhook_secret="x",
    invoice_provider="noop",
)
check("boot passa mesmo sem nota fiscal real", ok, str(problemas))

print("\n[7] em desenvolvimento, nada disso é fatal (só logger.warning)")
fake = Settings(app_env="development", payment_provider="mock", invoice_provider="noop",
                jwt_secret="x", email_provider="mock")
original = startup.settings
startup.settings = fake
try:
    startup.validate_startup_config()  # não deve lançar
    check("dev não derruba o boot", True)
except startup.ConfigError as e:
    check("dev não derruba o boot", False, str(e))
finally:
    startup.settings = original

print("\n" + "=" * 56)
print("FALHAS: " + ", ".join(falhas) if falhas else "VALIDAÇÃO DE BOOT: TUDO PASSOU")
print("=" * 56)
raise SystemExit(1 if falhas else 0)
