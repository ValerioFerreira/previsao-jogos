"""Interface do gateway de pagamento — permite trocar de provedor com impacto mínimo.
Cada adapter (Asaas/MercadoPago/Pagar.me/Stripe) implementa estes métodos."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


@dataclass
class CheckoutResult:
    provider_order_id: str
    status: str                       # created | pending
    checkout: dict = field(default_factory=dict)   # url/pix/qr — específico do provedor


@dataclass
class WebhookEvent:
    external_id: str                  # id da ordem no provedor
    event: str                        # ex.: payment.confirmed
    status: str                       # paid | failed | canceled | pending
    raw: dict = field(default_factory=dict)


class PaymentGateway(Protocol):
    name: str

    def create_checkout(self, *, order_id: str, amount_brl: Decimal, description: str,
                        customer_email: str) -> CheckoutResult: ...

    def verify_signature(self, headers: dict, body: bytes) -> bool: ...

    def parse_webhook(self, payload: dict) -> WebhookEvent: ...
