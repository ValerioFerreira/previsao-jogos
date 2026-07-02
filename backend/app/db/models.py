"""Registro central de modelos ORM da camada de aplicação.

Importa Base + TODOS os modelos de domínio, para que `Base.metadata` conheça todas as
tabelas (usado pelo Alembic autogenerate e por create_all no fallback de dev).
Importe este módulo (não os modelos avulsos) quando precisar do metadata completo.
"""
from __future__ import annotations

from app.db.base import Base  # noqa: F401

# Ordem importa por causa das FKs entre domínios (users primeiro).
from app.domains.users import models as users_models  # noqa: F401
from app.domains.legal import models as legal_models  # noqa: F401
from app.domains.wallet import models as wallet_models  # noqa: F401
from app.domains.payments import models as payments_models  # noqa: F401
from app.domains.analysis import models as analysis_models  # noqa: F401
from app.domains.promotions import models as promotions_models  # noqa: F401
from app.domains.bets import models as bets_models  # noqa: F401
from app.domains.admin import models as admin_models  # noqa: F401

__all__ = ["Base"]
