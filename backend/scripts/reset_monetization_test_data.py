#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/reset_monetization_test_data.py
================================================
Reset pré-lançamento: apaga todo o histórico de vendas/crédito promocional gerado em
modo de teste, preservando as contas de admin e de parceiros. Usa a DATABASE_URL do
backend/.env (Neon em produção).

Exceções de saldo (carteira NUNCA zerada) calculadas automaticamente:
  - todo User com role admin/superadmin;
  - todo User linkado a um Affiliate (conta de parceiro), via Affiliate.user_id.
E-mails extras podem ser passados por argv e são somados a essas exceções.

O que é feito (nesta ordem, tudo numa única transação — só grava com --apply):
  1. Saldo de créditos: zera disponível+reservado de toda carteira fora das exceções,
     via lançamento no ledger (post_transaction, NUNCA UPDATE direto) — mesma lógica de
     zero_credits_except.py.
  2. Comissões/pagamentos de afiliado (AffiliateCommission, AffiliatePayment): excluídos
     por completo (inteiramente derivados de compras de teste).
  3. Pedidos e webhooks de pagamento (PaymentOrder, PaymentWebhook): excluídos por
     completo (nenhuma venda real aconteceu ainda).
  4. Cupons: contador de resgates (Coupon.redemptions) volta a 0.
  5. Eventos de analytics (app_events): excluídos por completo.

Por padrão roda em modo `--dry-run` (só imprime o que faria). É preciso passar `--apply`
explicitamente para gravar de verdade.

Uso:
  cd backend && .venv/Scripts/python scripts/reset_monetization_test_data.py
  cd backend && .venv/Scripts/python scripts/reset_monetization_test_data.py --apply
  cd backend && .venv/Scripts/python scripts/reset_monetization_test_data.py extra@x.com --apply
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select, update

from app.db.base import SessionLocal
from app.domains.affiliates.models import Affiliate, AffiliateCommission, AffiliatePayment
from app.domains.analytics.models import Event
from app.domains.enums import CreditTxType, UserRole
from app.domains.payments.models import PaymentOrder, PaymentWebhook
from app.domains.promotions.models import Coupon
from app.domains.users.models import User
from app.domains.wallet.models import Wallet
from app.domains.wallet.service import post_transaction


def main() -> None:
    extra_emails = {a.strip().lower() for a in sys.argv[1:] if not a.startswith("--")}
    apply_ = "--apply" in sys.argv

    db = SessionLocal()
    try:
        admin_emails = {
            u.email.lower() for u in db.execute(
                select(User).where(User.role.in_([UserRole.admin, UserRole.superadmin]))
            ).scalars()
        }
        partner_user_ids = [r[0] for r in db.execute(
            select(Affiliate.user_id).where(Affiliate.user_id.is_not(None))
        )]
        partner_emails = {
            u.email.lower() for u in db.execute(
                select(User).where(User.id.in_(partner_user_ids))
            ).scalars()
        } if partner_user_ids else set()
        exceptions = admin_emails | partner_emails | extra_emails

        print(f"Contas preservadas ({len(exceptions)}): {', '.join(sorted(exceptions)) or '—'}\n")

        # 1. Zerar saldo de créditos (ledger, nunca UPDATE direto)
        rows = db.execute(select(Wallet, User).join(User, User.id == Wallet.user_id)).all()
        touched, skipped, total_available, total_reserved = 0, 0, Decimal("0"), Decimal("0")
        for wallet, user in rows:
            if user.email.lower() in exceptions:
                skipped += 1
                continue
            avail = Decimal(wallet.available_balance)
            resv = Decimal(wallet.reserved_balance)
            if avail == 0 and resv == 0:
                continue
            touched += 1
            total_available += avail
            total_reserved += resv
            print(f"{'[APLICANDO]' if apply_ else '[dry-run]'} carteira {user.email}: "
                  f"disponível {avail} -> 0, reservado {resv} -> 0")
            if apply_:
                post_transaction(
                    db, wallet=wallet, tx_type=CreditTxType.manual_adjustment,
                    amount=-avail, reserved_delta=-resv,
                    idempotency_key=f"pre-launch-reset:{wallet.id}",
                    reference_type="admin", description="Reset de créditos pré-lançamento",
                )
        print(f"\n[saldos] {touched} carteira(s) zerada(s), {skipped} preservada(s), "
              f"{total_available} disponíveis + {total_reserved} reservados removidos.\n")

        # 2. Comissões/pagamentos de afiliado
        n_payments = db.execute(select(func.count(AffiliatePayment.id))).scalar_one()
        n_commissions = db.execute(select(func.count(AffiliateCommission.id))).scalar_one()
        print(f"[afiliados] {n_commissions} comissão(ões) e {n_payments} pagamento(s) de teste "
              f"{'excluídos' if apply_ else 'seriam excluídos'}.")
        if apply_:
            db.execute(delete(AffiliatePayment))
            db.execute(delete(AffiliateCommission))

        # 3. Pedidos e webhooks de pagamento
        n_orders = db.execute(select(func.count(PaymentOrder.id))).scalar_one()
        n_webhooks = db.execute(select(func.count(PaymentWebhook.id))).scalar_one()
        print(f"[pedidos] {n_orders} pedido(s) e {n_webhooks} webhook(s) de teste "
              f"{'excluídos' if apply_ else 'seriam excluídos'}.")
        if apply_:
            db.execute(delete(PaymentOrder))
            db.execute(delete(PaymentWebhook))

        # 4. Cupons resgatados
        n_coupons = db.execute(select(func.count(Coupon.id)).where(Coupon.redemptions > 0)).scalar_one()
        print(f"[cupons] {n_coupons} cupom(ns) com resgate {'zerado' if apply_ else 'seria(m) zerado(s)'}.")
        if apply_:
            db.execute(update(Coupon).values(redemptions=0))

        # 5. Eventos de analytics
        n_events = db.execute(select(func.count(Event.id))).scalar_one()
        print(f"[analytics] {n_events} evento(s) de teste {'excluídos' if apply_ else 'seriam excluídos'}.")
        if apply_:
            db.execute(delete(Event))

        if apply_:
            db.commit()
            print("\nGravado.")
        else:
            print("\nModo dry-run — nada foi gravado. Rode de novo com --apply para aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
