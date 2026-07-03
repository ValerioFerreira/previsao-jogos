"""
Base do ORM declarativo (SQLAlchemy 2.0) para a camada transacional (usuários, carteira,
pagamentos, apostas, promoções). Isolada do pipeline de dados (que usa SQLAlchemy Core +
pandas). Todas as tabelas usam o prefixo `app_` para não colidir com as tabelas de dados
(matches, fixture_index, odds_registry...) no schema public.

Reusa a mesma engine/SessionLocal de app.db.connection (Neon Postgres em produção,
SQLite em memória no fallback local).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB as _PGJSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.connection import SessionLocal, engine  # noqa: F401  (reexport)

# JSONB no Postgres (produção), JSON no SQLite (fallback local) — mesmo código de modelo.
JSONB = JSON().with_variant(_PGJSONB, "postgresql")


def enum_type(py_enum):
    """Coluna de enum portável (VARCHAR + CHECK), guardando o .value de cada membro."""
    return SAEnum(
        py_enum,
        native_enum=False,
        length=40,
        values_callable=lambda e: [m.value for m in e],
    )


class Base(DeclarativeBase):
    """Base declarativa comum a todos os modelos da camada de aplicação."""


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def get_session():
    """Dependency FastAPI: sessão ORM transacional (commit/rollback pelo chamador)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
