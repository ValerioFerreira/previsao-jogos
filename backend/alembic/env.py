"""Ambiente Alembic — migrations da camada de aplicação (tabelas app_*).

Usa o Base.metadata do projeto (app.db.models) e a mesma DATABASE_URL do backend.
As tabelas de DADOS (matches, fixture_index, odds_registry...) NÃO são geridas aqui —
elas são materializadas pelo pipeline de ETL. Por isso filtramos para tocar só em app_*.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# garante que o pacote `app` seja importável ao rodar `alembic` da pasta backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.connection import DATABASE_URL  # noqa: E402
from app.db.models import Base  # noqa: E402  (importa todos os modelos)

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Só gerencia objetos da camada de aplicação (prefixo app_)."""
    if type_ == "table":
        return bool(name and name.startswith("app_"))
    parent = getattr(obj, "table", None)
    if parent is not None:
        return parent.name.startswith("app_")
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
