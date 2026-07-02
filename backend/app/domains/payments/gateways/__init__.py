"""Fábrica de gateway de pagamento (trocável por settings.payment_provider)."""
from __future__ import annotations

from app.core.config import settings
from app.domains.payments.gateways.base import PaymentGateway
from app.domains.payments.gateways.mock import MockGateway


def get_gateway() -> PaymentGateway:
    provider = (settings.payment_provider or "mock").lower()
    # Adapters reais (asaas/mercadopago/pagarme/stripe) entram aqui pela mesma interface.
    return MockGateway()
