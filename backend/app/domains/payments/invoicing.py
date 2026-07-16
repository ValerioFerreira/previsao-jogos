"""Hook de nota fiscal — best-effort, nunca bloqueia a liberação do crédito (que já
aconteceu antes desta chamada). Sem emissor real configurado: `NoopInvoiceProvider`
(mesmo padrão do MockGateway). Emissor real: NFE.io (`INVOICE_PROVIDER=nfeio`,
ver `invoicing_nfeio.py`) — emissão de NFS-e é assíncrona lá, por isso o Protocol
também expõe `check_status()` para reconsulta idempotente (usada por
`request_invoice()` e pelo polling periódico, ver `scripts/invoice_poll.py`)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.core.config import settings


class InvoiceResult:
    def __init__(self, url: str | None, status: str,
                 provider_invoice_id: str | None = None,
                 invoice_number: str | None = None,
                 error_message: str | None = None):
        self.url = url
        self.status = status                            # pending | issued | failed
        self.provider_invoice_id = provider_invoice_id   # id do documento no provedor (polling/idempotência)
        self.invoice_number = invoice_number              # número dado pelo município (só após "issued")
        self.error_message = error_message


class InvoiceProvider(Protocol):
    def issue(self, *, order_id: str, amount_brl: Decimal, credits: int,
              customer_name: str, customer_email: str, customer_cpf: str,
              competency_date: datetime, description: str) -> InvoiceResult: ...

    def check_status(self, *, provider_invoice_id: str) -> InvoiceResult:
        """Reconsulta o status de um documento já criado — usada quando
        `invoice_provider_id` já existe, para nunca reemitir uma nota duplicada."""
        ...


class NoopInvoiceProvider:
    """Não emite nada de verdade — marca como 'pending' (fica para emissão manual/futura
    integração) sem quebrar o fluxo de pagamento."""

    def issue(self, *, order_id: str, amount_brl: Decimal, credits: int,
              customer_name: str, customer_email: str, customer_cpf: str,
              competency_date: datetime, description: str) -> InvoiceResult:
        return InvoiceResult(url=None, status="pending")

    def check_status(self, *, provider_invoice_id: str) -> InvoiceResult:
        return InvoiceResult(url=None, status="pending", provider_invoice_id=provider_invoice_id)


def get_invoice_provider() -> InvoiceProvider:
    provider = (settings.invoice_provider or "noop").lower()
    if provider == "nfeio":
        from app.domains.payments.invoicing_nfeio import NFEioProvider
        return NFEioProvider()
    return NoopInvoiceProvider()


def issue_invoice(db, order) -> None:
    """Chamado após o pagamento ser confirmado — nunca lança (best-effort)."""
    try:
        provider = get_invoice_provider()
        from app.domains.users.models import User
        user = db.get(User, order.user_id)
        result = provider.issue(
            order_id=str(order.id), amount_brl=order.amount_brl, credits=order.credits,
            customer_name=user.full_name if user else "", customer_cpf=user.cpf if user else "",
            customer_email=user.email if user else "",
            competency_date=order.paid_at or datetime.now(),
            description=f"{order.credits} créditos ApostAI",
        )
        order.invoice_url = result.url
        order.invoice_status = result.status
        order.invoice_provider_id = result.provider_invoice_id
        order.invoice_number = result.invoice_number
    except Exception as e:
        print(f"[AVISO] issue_invoice({order.id}): {e}")
