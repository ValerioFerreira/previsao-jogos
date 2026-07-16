"""Gateway MERCADO PAGO (Checkout Pro) — Pix + cartão via preferência de pagamento.
Credenciais: MP_ACCESS_TOKEN (server-side), MP_WEBHOOK_SECRET (assinatura do webhook).
Doc: https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/webhooks
"""
from __future__ import annotations

import hashlib
import hmac
import re
from decimal import Decimal

import httpx

from app.core.config import settings
from app.domains.payments.gateways.base import CheckoutResult, WebhookEvent

_API_BASE = "https://api.mercadopago.com"

_MP_STATUS_MAP = {
    "approved": "paid",
    "pending": "pending",
    "in_process": "pending",
    "rejected": "failed",
    "cancelled": "canceled",
    "refunded": "canceled",
    "charged_back": "canceled",
}


class MercadoPagoGateway:
    name = "mercadopago"

    def create_checkout(self, *, order_id: str, amount_brl: Decimal, description: str,
                        customer_email: str) -> CheckoutResult:
        if not settings.mp_access_token:
            raise RuntimeError("MP_ACCESS_TOKEN ausente — configure antes de usar o gateway real.")
        payload = {
            "items": [{
                "id": order_id,
                "title": description[:250],
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(amount_brl),
            }],
            "payer": {"email": customer_email},
            "external_reference": order_id,
            "notification_url": settings.mp_webhook_url or None,
            "back_urls": {
                "success": f"{settings.frontend_base_url}/carteira?status=success",
                "pending": f"{settings.frontend_base_url}/carteira?status=pending",
                "failure": f"{settings.frontend_base_url}/carteira?status=failure",
            },
            "auto_return": "approved",
        }
        r = httpx.post(
            f"{_API_BASE}/checkout/preferences",
            headers={"Authorization": f"Bearer {settings.mp_access_token}"},
            json=payload, timeout=30,
        )
        r.raise_for_status()
        pref = r.json()
        # Guardamos o nosso próprio order_id como provider_order_id: é o valor que
        # mandamos em `external_reference` e que volta em todo webhook/pagamento do MP,
        # então é a chave estável para casar PaymentOrder <-> notificação (a preferência
        # em si não aparece no payload de pagamento). O id da preferência fica só no
        # `checkout` dict, para referência/debug.
        return CheckoutResult(
            provider_order_id=order_id,
            status="pending",
            checkout={
                "modo": "mercadopago",
                "preference_id": pref.get("id"),
                "init_point": pref.get("init_point"),
                "sandbox_init_point": pref.get("sandbox_init_point"),
            },
        )

    def verify_signature(self, headers: dict, body: bytes, query_params: dict) -> bool:
        """Valida `x-signature` (ts + hash) contra MP_WEBHOOK_SECRET.
        Formato: 'ts=<epoch>,v1=<hmac_sha256_hex>'. Manifest assinado:
        'id:<data.id>;request-id:<x-request-id>;ts:<ts>;'

        `data.id` vem do **query string da URL da notificação** (`?data.id=...&type=payment`),
        NÃO do corpo do POST — é um erro comum assumir que vem do JSON (o corpo pode até
        conter um `data.id`, mas a MP assina com o valor da URL; usar o do corpo gera 100%
        de falso-negativo em produção). Normalizado para minúsculas conforme a doc da MP.
        """
        secret = settings.mp_webhook_secret.strip()
        if not secret:
            return False
        sig_header = headers.get("x-signature") or headers.get("X-Signature")
        request_id = (headers.get("x-request-id") or headers.get("X-Request-Id") or "").strip()
        if not sig_header:
            print("[AVISO] webhook MP: sem header x-signature")
            return False
        # .strip() em chave E valor — a MP pode mandar "ts=...,  v1=..." com espaço após a
        # vírgula; sem o strip, a chave vira " v1" (com espaço) e o v1 nunca é encontrado.
        parts = {}
        for p in sig_header.split(","):
            if "=" in p:
                k, v = p.split("=", 1)
                parts[k.strip()] = v.strip()
        ts, v1 = parts.get("ts"), parts.get("v1")
        if not ts or not v1:
            print(f"[AVISO] webhook MP: x-signature sem ts/v1 (header bruto={sig_header!r})")
            return False
        data_id = (query_params.get("data.id") or query_params.get("data_id")
                   or query_params.get("id") or "").strip().lower()
        if not data_id:
            # fallback defensivo — algumas integrações também ecoam data.id no corpo
            try:
                import json
                data_id = str(json.loads(body or b"{}").get("data", {}).get("id", "")).strip().lower()
            except Exception:
                data_id = ""
        manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
        expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, v1)
        if not ok:
            # Fingerprint do segredo (sha256 truncado) — nunca expõe o valor, mas permite
            # comparar com um fingerprint calculado à parte a partir do os.environ real,
            # pra descartar de vez qualquer divergência de carregamento de config
            # (.env desatualizado no deploy, nome de env var errado, cache, etc.).
            secret_fp = hashlib.sha256(secret.encode()).hexdigest()[:12]
            print(f"[AVISO] webhook MP: assinatura não bateu — manifest={manifest!r} "
                  f"esperado={expected} recebido={v1} "
                  f"secret_len={len(secret)} secret_fp_sha256_12={secret_fp} "
                  f"sig_header_bruto={sig_header!r} data_id_fonte="
                  f"{'query.data.id' if query_params.get('data.id') else 'query.data_id' if query_params.get('data_id') else 'query.id' if query_params.get('id') else 'body/vazio'}")
        return ok

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        """Payload de notificação IPN/webhook do MP traz só o `data.id` do pagamento —
        buscamos o pagamento pra saber status + external_reference (nosso order_id)."""
        payment_id = str((payload.get("data") or {}).get("id", ""))
        if not payment_id:
            return WebhookEvent(external_id="", event="unknown", status="pending", raw=payload)
        r = httpx.get(
            f"{_API_BASE}/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {settings.mp_access_token}"}, timeout=30,
        )
        r.raise_for_status()
        pay = r.json()
        mp_status = pay.get("status", "pending")
        return WebhookEvent(
            external_id=str(pay.get("external_reference") or ""),
            event=f"payment.{mp_status}",
            status=_MP_STATUS_MAP.get(mp_status, "pending"),
            raw=pay,
        )
