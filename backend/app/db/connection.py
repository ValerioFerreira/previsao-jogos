import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _load_local_dotenv() -> None:
    """Carrega backend/.env para o ambiente ao rodar localmente (coletores, builds,
    dev). Em produção (Render) as variáveis já vêm do ambiente e têm precedência —
    usamos setdefault para nunca sobrescrevê-las."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_dotenv()
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
        # Causa raiz do travamento dos jobs de coleta (2026-07-08..14): o pooler do Neon
        # às vezes derruba a conexão TCP sem avisar (RST silencioso) e o psycopg2 NÃO tem
        # timeout por padrão — o processo fica preso indefinidamente num connect() ou numa
        # query, nunca levanta exceção, e o `prefetch_wc.cmd` nunca chega nas etapas
        # seguintes (rebuild/precompute/prefetch de clubes). Com timeouts explícitos, a
        # conexão trava no máximo alguns segundos e levanta OperationalError — que o
        # código já trata (cache_get/cache_put fazem try/except e seguem em frente).
        # OBS: "options": "-c statement_timeout=..." NÃO funciona aqui -- o endpoint é o
        # pooler (pgbouncer) do Neon, que rejeita parâmetros de startup arbitrários
        # ("unsupported startup parameter in options"). Usamos keepalives (nível TCP,
        # não passa pelo protocolo de startup) para detectar a conexão morta rápido, e
        # aplicamos o statement_timeout via SET logo após conectar (evento "connect").
        "connect_args": {
            "connect_timeout": 10,      # segundos p/ completar o handshake TCP/SSL
            "keepalives": 1,
            "keepalives_idle": 15,      # segundos ocioso antes do 1º probe
            "keepalives_interval": 5,   # segundos entre probes
            "keepalives_count": 3,      # probes sem resposta até considerar morta
        },
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)

if DATABASE_URL.startswith("postgresql"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_statement_timeout(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET statement_timeout = 20000")  # 20s max por query no servidor
        cursor.close()
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
