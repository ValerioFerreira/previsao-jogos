"""Hook de nota fiscal — best-effort, nunca bloqueia a liberação do crédito (que já
aconteceu antes desta chamada). Sem emissor real configurado: `NoopInvoiceProvider`
(mesmo padrão do MockGateway) até o usuário escolher o emissor (NFE.io/Focus NFe/etc)."""
from __future__ import annotations

from typing import Protocol


class InvoiceResult:
    def __init__(self, url: str | None, status: str):
        self.url = url
        self.status = status


class InvoiceProvider(Protocol):
    def issue(self, *, order_id: str, amount_brl, customer_email: str) -> InvoiceResult: ...


class NoopInvoiceProvider:
    """Não emite nada de verdade — marca como 'pending' (fica para emissão manual/futura
    integração) sem quebrar o fluxo de pagamento."""

    def issue(self, *, order_id: str, amount_brl, customer_email: str) -> InvoiceResult:
        return InvoiceResult(url=None, status="pending")


def get_invoice_provider() -> InvoiceProvider:
    return NoopInvoiceProvider()


def issue_invoice(db, order) -> None:
    """Chamado após o pagamento ser confirmado — nunca lança (best-effort)."""
    try:
        provider = get_invoice_provider()
        from app.domains.users.models import User
        user = db.get(User, order.user_id)
        result = provider.issue(order_id=str(order.id), amount_brl=order.amount_brl,
                                customer_email=user.email if user else "")
        order.invoice_url = result.url
        order.invoice_status = result.status
    except Exception as e:
        print(f"[AVISO] issue_invoice({order.id}): {e}")
