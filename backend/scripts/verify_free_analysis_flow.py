#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/verify_free_analysis_flow.py
=====================================
Exercita a regra "Copa do Mundo grátis ilimitada + 1 análise grátis por dia" sem
depender do pipeline de previsão real (mocka `_generate_snapshot`, que já é testado
à parte pelo endpoint /predict) e sem rede/banco real (SQLite temporário).

Cobre:
  - análise de "Copa do Mundo" nunca desconta crédito, mesmo repetida várias vezes;
  - a 1a análise do dia de outro torneio é grátis (credits_consumed=0, is_free=True);
  - a 2a análise do MESMO dia e usuário já desconta crédito normalmente;
  - no dia seguinte, a cota grátis volta a valer (idempotência por (user_id, dia)).

Uso:
    cd backend
    python -m scripts.verify_free_analysis_flow    # exit 0 = tudo passou
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    db_path = Path(tempfile.mkdtemp(prefix="verify_free_analysis_")) / "e2e.sqlite"
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "APP_ENV": "development",
        "JWT_SECRET": "verificacao-local-nao-e-segredo",
    })

    from app.db.base import Base, SessionLocal, engine
    import app.domains.users.models, app.domains.wallet.models, app.domains.legal.models      # noqa: F401,E401
    import app.domains.payments.models, app.domains.analysis.models, app.domains.bets.models  # noqa: F401,E401
    import app.domains.promotions.models, app.domains.admin.models                            # noqa: F401,E401
    import app.domains.affiliates.models, app.domains.campaigns.models                        # noqa: F401,E401
    import app.domains.analytics.models, app.domains.notifications.models                     # noqa: F401,E401

    from app.domains.analysis import schemas, service as analysis_service
    from app.domains.users.models import User
    from app.domains.enums import UserStatus
    from app.domains.wallet.service import get_or_create_wallet, post_transaction
    from app.domains.enums import CreditTxType

    Base.metadata.create_all(engine)

    falhas: list[str] = []

    def check(nome: str, ok: bool, extra: str = "") -> None:
        print(f"{'  OK ' if ok else '  XX '} {nome}{'' if ok else '  <-- ' + extra}")
        if not ok:
            falhas.append(nome)

    db = SessionLocal()
    user = User(full_name="Ana Lima", email="ana@teste.com", cpf="15350946056",
                phone="11912345678", status=UserStatus.active)
    db.add(user)
    db.commit()
    db.refresh(user)

    wallet = get_or_create_wallet(db, user.id)
    post_transaction(db, wallet=wallet, tx_type=CreditTxType.bonus, amount=Decimal("3"),
                     idempotency_key="seed-credits", description="créditos iniciais de teste")
    db.commit()

    fake_snapshot = ({"fake": True}, "Brazil", "Argentina")

    with patch.object(analysis_service, "_generate_snapshot", return_value=fake_snapshot), \
         patch.object(analysis_service, "_model_fingerprint", return_value=(None, None)):

        print("\n[1] Copa do Mundo é grátis, mesmo repetida (não desconta nem consome a cota diária)")
        req_wc = schemas.AnalysisRequest(home_team="Brazil", away_team="Argentina",
                                         tournament="Copa do Mundo", type="independent")
        a1 = analysis_service.create_analysis(db, user, req_wc)
        check("is_free=True", a1.is_free is True)
        check("credits_consumed=0", a1.credits_consumed == 0, str(a1.credits_consumed))
        wallet_after_wc = get_or_create_wallet(db, user.id)
        check("saldo intocado (3)", Decimal(wallet_after_wc.available_balance) == Decimal("3"),
              str(wallet_after_wc.available_balance))

        a2 = analysis_service.create_analysis(db, user, req_wc)
        check("2a análise de Copa também grátis", a2.is_free is True and a2.credits_consumed == 0)

        print("\n[2] 1a análise do dia de outro torneio é grátis (cota diária)")
        req_other = schemas.AnalysisRequest(home_team="Brazil", away_team="Argentina",
                                            tournament="Amistoso", type="independent")
        a3 = analysis_service.create_analysis(db, user, req_other)
        check("is_free=True (cota diária)", a3.is_free is True)
        check("credits_consumed=0", a3.credits_consumed == 0, str(a3.credits_consumed))
        wallet_after_daily = get_or_create_wallet(db, user.id)
        check("saldo ainda 3 (cota diária não gasta crédito)",
              Decimal(wallet_after_daily.available_balance) == Decimal("3"),
              str(wallet_after_daily.available_balance))

        print("\n[3] 2a análise do MESMO dia já desconta crédito normalmente")
        a4 = analysis_service.create_analysis(db, user, req_other)
        check("is_free=False", a4.is_free is False)
        check("credits_consumed=1", a4.credits_consumed == 1, str(a4.credits_consumed))
        wallet_after_2nd = get_or_create_wallet(db, user.id)
        check("saldo caiu para 2", Decimal(wallet_after_2nd.available_balance) == Decimal("2"),
              str(wallet_after_2nd.available_balance))

        print("\n[4] No dia seguinte, a cota grátis volta a valer")
        from app.domains.analysis.models import FreeDailyUse
        from sqlalchemy import select
        yesterday_row = db.execute(select(FreeDailyUse).where(FreeDailyUse.user_id == user.id)).scalar_one()
        yesterday_row.used_on = date.today() - timedelta(days=1)
        db.commit()
        a5 = analysis_service.create_analysis(db, user, req_other)
        check("is_free=True de novo (novo dia)", a5.is_free is True)

    print("\n" + "=" * 56)
    if falhas:
        print(f"FALHAS: {len(falhas)} -> {falhas}")
        return 1
    print("ANÁLISE GRÁTIS (COPA DO MUNDO + COTA DIÁRIA): TUDO PASSOU")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
