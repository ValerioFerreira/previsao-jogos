#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_invoice_flow.py
===============================
Exercita o fluxo de nota fiscal INTEIRO sem tocar na NFE.io de verdade e sem
gastar nenhuma nota real: SQLite temporário + um servidor HTTP local que finge
ser a API da NFE.io (POST .../serviceinvoices -> 202 pending; GET .../{id} ->
Pending na primeira consulta, Issued na segunda, simulando a emissão assíncrona).

    checkout (mock) -> confirm_mock (paga) -> issue_invoice automático (pending)
    -> invoice_poll (1a consulta: ainda pending) -> invoice_poll (2a: issued)

Também cobre o caminho de erro (provedor devolve Error) e o `request_invoice()`
não reemitindo (reconsulta em vez de duplicar) quando já existe
`invoice_provider_id`.

Uso:
    cd backend
    python -m scripts.verify_invoice_flow          # exit 0 = tudo passou

Não precisa de DATABASE_URL nem rede real. Requer as deps de
backend/requirements.txt instaladas (fastapi, sqlalchemy, httpx).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# --------------------------------------------------- NFE.io falsa
_invoices: dict[str, dict] = {}
_poll_count: dict[str, int] = {}
_state: dict = {"next_status": "Issued"}  # trocável para "Error" num teste de falha


class _FakeNFEio(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        new_id = uuid.uuid4().hex
        _invoices[new_id] = {"id": new_id, "flowStatus": "Created"}
        _poll_count[new_id] = 0
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"id": new_id, "flowStatus": "Created"}).encode())

    def do_GET(self):  # noqa: N802
        inv_id = self.path.rsplit("/", 1)[-1]
        _poll_count[inv_id] = _poll_count.get(inv_id, 0) + 1
        # 1a consulta: ainda "Pending". Da 2a em diante: resolve para next_status.
        if _poll_count[inv_id] == 1:
            body = {"id": inv_id, "flowStatus": "Pending"}
        elif _state["next_status"] == "Issued":
            body = {"id": inv_id, "flowStatus": "Issued", "number": "2026NFE00042",
                     "secure": {"url": "https://fake.nfe.io/invoice.pdf"}}
        else:
            body = {"id": inv_id, "flowStatus": "Error", "flowMessage": "cityServiceCode inválido"}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *a):  # silencia o log do http.server
        pass


def main() -> int:
    srv = HTTPServer(("127.0.0.1", 0), _FakeNFEio)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    db_path = Path(tempfile.mkdtemp(prefix="verify_invoice_")) / "e2e.sqlite"
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "APP_ENV": "development",
        "JWT_SECRET": "verificacao-local-nao-e-segredo",
        "PAYMENT_PROVIDER": "mock",
        "INVOICE_PROVIDER": "nfeio",
        "NFEIO_API_BASE": f"http://127.0.0.1:{srv.server_port}",
        "NFEIO_API_TOKEN": "token-falso",
        "NFEIO_COMPANY_ID": "empresa-falsa",
        "COMPANY_CNPJ": "12345678000199",
        "COMPANY_RAZAO_SOCIAL": "ApostAI Teste LTDA",
        "COMPANY_INSCRICAO_MUNICIPAL": "12345",
        "COMPANY_CITY_SERVICE_CODE": "0107",
    })

    from app.db.base import Base, SessionLocal, engine
    # importa todos os modelos para o create_all enxergar as tabelas app_*
    import app.domains.users.models, app.domains.wallet.models, app.domains.legal.models      # noqa: F401,E401
    import app.domains.payments.models, app.domains.analysis.models, app.domains.bets.models  # noqa: F401,E401
    import app.domains.promotions.models, app.domains.admin.models                            # noqa: F401,E401
    import app.domains.affiliates.models, app.domains.campaigns.models                        # noqa: F401,E401
    import app.domains.analytics.models, app.domains.notifications.models                     # noqa: F401,E401

    from app.domains.payments import schemas
    from app.domains.payments.service import create_order, confirm_mock, poll_pending_invoices, request_invoice
    from app.domains.payments.models import PaymentOrder
    from app.domains.users.models import User
    from app.domains.enums import UserStatus

    Base.metadata.create_all(engine)

    falhas: list[str] = []

    def check(nome: str, ok: bool, extra: str = "") -> None:
        print(f"{'  OK ' if ok else '  XX '} {nome}{'' if ok else '  <-- ' + extra}")
        if not ok:
            falhas.append(nome)

    db = SessionLocal()
    user = User(full_name="Maria Souza", email="maria@teste.com", cpf="52998224725",
                phone="11987654321", status=UserStatus.active)
    db.add(user)
    db.commit()
    db.refresh(user)

    print("\n[1] checkout (mock) + confirm_mock -> paga e dispara issue_invoice automático")
    order_resp = create_order(db, user, schemas.CheckoutRequest(credits=100))
    confirm_mock(db, user, order_resp.order_id)
    order = db.get(PaymentOrder, uuid.UUID(order_resp.order_id))
    db.refresh(order)
    check("status pago", order.status.value == "paid", order.status.value)
    check("invoice_status = pending (assíncrono)", order.invoice_status == "pending", str(order.invoice_status))
    check("invoice_provider_id setado", bool(order.invoice_provider_id))
    check("invoice_url ainda vazio", order.invoice_url is None)

    print("\n[2] 1a reconsulta (poll) -> provedor ainda responde Pending")
    res1 = poll_pending_invoices(db)
    db.refresh(order)
    check("1 pedido verificado", res1["checked"] == 1, str(res1))
    check("continua pending", order.invoice_status == "pending", str(order.invoice_status))

    print("\n[3] 2a reconsulta (poll) -> provedor resolve para Issued")
    res2 = poll_pending_invoices(db)
    db.refresh(order)
    check("1 emitida", res2["issued"] == 1, str(res2))
    check("invoice_status = issued", order.invoice_status == "issued", str(order.invoice_status))
    check("invoice_number populado", order.invoice_number == "2026NFE00042", str(order.invoice_number))
    check("invoice_url populado", order.invoice_url == "https://fake.nfe.io/invoice.pdf", str(order.invoice_url))

    print("\n[4] request_invoice() não reemite (reconsulta, não duplica) quando já issued")
    provider_id_antes = order.invoice_provider_id
    request_invoice(db, user, str(order.id))
    db.refresh(order)
    check("mesmo provider_invoice_id (não duplicou)", order.invoice_provider_id == provider_id_antes)

    print("\n[5] pedido novo + provedor devolve Error -> invoice_status = failed, pagamento intocado")
    _state["next_status"] = "Error"
    order_resp2 = create_order(db, user, schemas.CheckoutRequest(credits=50))
    confirm_mock(db, user, order_resp2.order_id)
    order2 = db.get(PaymentOrder, uuid.UUID(order_resp2.order_id))
    poll_pending_invoices(db)  # 1a consulta: pending
    res3 = poll_pending_invoices(db)  # 2a: Error
    db.refresh(order2)
    check("pedido2 continua pago mesmo com nota falha", order2.status.value == "paid", order2.status.value)
    check("invoice_status = failed", order2.invoice_status == "failed", str(order2.invoice_status))
    check("poll reporta 1 failed", res3["failed"] == 1, str(res3))

    db.close()
    srv.shutdown()
    print("\n" + "=" * 56)
    print("FALHAS: " + ", ".join(falhas) if falhas else "FLUXO DE NOTA FISCAL PONTA A PONTA: TUDO PASSOU")
    print("=" * 56)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
