"""Adapter NFE.io — emissão de NFS-e (nota de serviço), REST API.
Credenciais: NFEIO_API_TOKEN (API Key da empresa), NFEIO_COMPANY_ID.
Doc: https://nfe.io/docs/ (Service Invoices) — a emissão é ASSÍNCRONA: o POST
devolve 202 + um id com status "Created"/"Pending"; o status final ("Issued"/
"Error") só existe alguns segundos/minutos depois e precisa ser reconsultado
via check_status() — daí o polling em `scripts/invoice_poll.py` e o fallback em
`service.py::request_invoice()`, em vez de tratar isso como síncrono.

NOTA: os nomes exatos de campo (`cityServiceCode`, `federalTaxNumber`, os valores
do enum de status) foram implementados a partir da documentação pública da NFE.io
e não foram validados contra uma chamada real — confirme contra o Swagger atual
(https://api.nfe.io) ou uma chamada de teste antes de apontar para a empresa/API
key de produção. Ajustar aqui não muda o resto do desenho (Protocol/factory/
migration/config já são independentes deste detalhe).
"""
from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal

import httpx

from app.core.config import settings
from app.domains.payments.invoicing import InvoiceResult

_NFEIO_STATUS_MAP = {
    "Created": "pending",
    "Pending": "pending",
    "Issued": "issued",
    "Error": "failed",
    "Cancelled": "failed",
}


def _auth_header() -> dict:
    # NFE.io autentica via HTTP Basic com a API Key como usuário e senha em branco.
    token = base64.b64encode(f"{settings.nfeio_api_token}:".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _company_path() -> str:
    return f"{settings.nfeio_api_base}/companies/{settings.nfeio_company_id}/serviceinvoices"


class NFEioProvider:
    def issue(self, *, order_id: str, amount_brl: Decimal, credits: int,
              customer_name: str, customer_email: str, customer_cpf: str,
              competency_date: datetime, description: str) -> InvoiceResult:
        payload = {
            "borrower": {
                "name": customer_name,
                "email": customer_email,
                "federalTaxNumber": "".join(ch for ch in customer_cpf if ch.isdigit()),
            },
            "cityServiceCode": settings.company_city_service_code,
            "description": description,
            "servicesAmount": float(amount_brl),
            "environment": "Production" if settings.is_production else "Test",
            "reference": order_id,
        }
        r = httpx.post(_company_path(), headers=_auth_header(), json=payload, timeout=30)
        if r.status_code not in (200, 201, 202):
            return InvoiceResult(url=None, status="failed", error_message=r.text[:500])
        body = r.json() if r.content else {}
        provider_id = str(body.get("id") or "")
        nfeio_status = body.get("flowStatus") or body.get("status") or "Created"
        return InvoiceResult(
            url=body.get("secure", {}).get("url") if isinstance(body.get("secure"), dict) else None,
            status=_NFEIO_STATUS_MAP.get(nfeio_status, "pending"),
            provider_invoice_id=provider_id or None,
        )

    def check_status(self, *, provider_invoice_id: str) -> InvoiceResult:
        r = httpx.get(f"{_company_path()}/{provider_invoice_id}", headers=_auth_header(), timeout=30)
        r.raise_for_status()
        body = r.json()
        nfeio_status = body.get("flowStatus") or body.get("status") or "Pending"
        secure = body.get("secure") if isinstance(body.get("secure"), dict) else {}
        return InvoiceResult(
            url=secure.get("url"),
            status=_NFEIO_STATUS_MAP.get(nfeio_status, "pending"),
            provider_invoice_id=provider_invoice_id,
            invoice_number=str(body["number"]) if body.get("number") else None,
            error_message=body.get("flowMessage") if nfeio_status == "Error" else None,
        )
