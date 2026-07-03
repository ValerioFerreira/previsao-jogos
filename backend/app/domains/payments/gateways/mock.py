"""Gateway MOCK — para desenvolvimento/revisão. Não move dinheiro real. O pagamento é
'confirmado' via endpoint de simulação (POST /payments/mock/confirm/{order_id}), que
dispara o mesmo caminho de webhook usado pelos gateways reais."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.domains.payments.gateways.base import CheckoutResult, WebhookEvent


class MockGateway:
    name = "mock"

    def create_checkout(self, *, order_id: str, amount_brl: Decimal, description: str,
                        customer_email: str) -> CheckoutResult:
        provider_order_id = f"mock_{uuid.uuid4().hex[:16]}"
        return CheckoutResult(
            provider_order_id=provider_order_id,
            status="pending",
            checkout={
                "modo": "mock",
                "instrucao": "Simule o pagamento chamando POST /payments/mock/confirm/{order_id}.",
                "amount_brl": str(amount_brl),
            },
        )

    def verify_signature(self, headers: dict, body: bytes) -> bool:
        return True  # mock: sempre válido

    def parse_webhook(self, payload: dict) -> WebhookEvent:
        return WebhookEvent(
            external_id=str(payload.get("external_id", "")),
            event=str(payload.get("event", "payment.confirmed")),
            status=str(payload.get("status", "paid")),
            raw=payload,
        )
