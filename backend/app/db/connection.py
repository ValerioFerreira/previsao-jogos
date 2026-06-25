import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

# Provide a fallback for local testing if not set (optional)
if not DATABASE_URL:
    print("[WARNING] DATABASE_URL não definida, usando SQLite temporário em memória para fallback.")
    DATABASE_URL = "sqlite:///:memory:"

# Create Engine with Neon Serverless requirements (pool_pre_ping)
# We only apply pooling settings to PostgreSQL, SQLite doesn't support them in the same way
engine_kwargs = {}
if DATABASE_URL.startswith("postgresql"):
    engine_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 300, # Reciclar conexões a cada 5 min para evitar drops
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency para uso no FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def truncate_and_append(df, table_name: str, con):
    """
    Realiza o TRUNCATE da tabela (se existir) mantendo o schema e os indexes,
    e então insere o dataframe via append na mesma transação para garantir atomicidade.
    """
    from sqlalchemy import inspect

    # con.begin() devolve a CONEXÃO transacionada; usamos ela (não o Engine) tanto
    # para o execute quanto para o to_sql — caso contrário, no SQLAlchemy 2.0 o Engine
    # não expõe .execute/.cursor e a escrita falha. Verificamos a existência da tabela
    # antes do TRUNCATE para não abortar a transação no Postgres quando ela ainda não existe.
    with con.begin() as conn:
        if inspect(conn).has_table(table_name):
            if conn.dialect.name.startswith("sqlite"):
                conn.execute(text(f'DELETE FROM "{table_name}"'))
            else:
                conn.execute(text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'))

        # Append usando a MESMA conexão/transação (atomicidade real: se o insert falhar,
        # o TRUNCATE sofre rollback junto).
        df.to_sql(name=table_name, con=conn, if_exists="append", index=False, method="multi", chunksize=1000)

def upsert_df(df, table_name: str, con, unique_keys: list[str]):
    """
    Insere os dados, atualizando as linhas existentes em caso de conflito
    (apenas para PostgreSQL). Se for SQLite, realiza um to_sql simples (append/replace).
    """
    if df.empty:
        return
        
    if not con.engine.url.drivername.startswith("postgresql"):
        # Fallback local
        df.to_sql(name=table_name, con=con, if_exists="replace", index=False, method="multi")
        return
        
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy import MetaData, Table

    metadata = MetaData()
    # Reflete a tabela
    try:
        table = Table(table_name, metadata, autoload_with=con)
    except Exception:
        # Se a tabela não existir, criamos a primeira vez
        with con.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists="replace", index=False, method="multi", chunksize=1000)
            # Adicionar as constraints unique manualmente, se possível
            keys_str = ", ".join(f'"{k}"' for k in unique_keys)
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{table_name}_unique_constraint" UNIQUE ({keys_str})'))
        return

    records = df.to_dict(orient="records")

    with con.begin() as conn:
        stmt = insert(table).values(records)

        # Cria o dicionário de update (tudo exceto as chaves únicas)
        update_dict = {c.name: c for c in stmt.excluded if c.name not in unique_keys}

        if update_dict:
            stmt = stmt.on_conflict_do_update(
                index_elements=unique_keys,
                set_=update_dict
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=unique_keys)

        conn.execute(stmt)
