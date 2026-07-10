"""
app/services/raw_cache.py
=========================
Espelho LOCAL (SQLite) do detalhe bruto dos jogos (match_detail_cache). Objetivo:
os jobs pesados (rebuilds de modelo, precompute de agregados) leem o bruto do disco
local — na máquina 24h — em vez de puxar ~44 MB do Neon a cada execução. Isso elimina
a maior fonte de Network Transfer (egress) do Neon.

- `iter_all_raw()` itera os dicts do bruto: do SQLite local se disponível, senão do Neon.
- `local_put()` grava um jogo no espelho (o prefetch chama junto do write no Neon).
- `mirror_from_neon()` faz o backfill único (uma leitura de ~44 MB do Neon -> SQLite).

Runtime do site NÃO usa este módulo (os endpoints leem os agregados pequenos); ele é só
para os jobs locais. Se o SQLite não existir (ex.: no Render), cai no Neon com segurança.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

LOCAL_PATH = Path(__file__).resolve().parents[2] / "data" / "raw_cache.sqlite"


def _conn() -> sqlite3.Connection:
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOCAL_PATH))
    conn.execute("CREATE TABLE IF NOT EXISTS raw (key TEXT PRIMARY KEY, fixture_id INTEGER, raw TEXT)")
    return conn


def local_available() -> bool:
    if not LOCAL_PATH.exists():
        return False
    try:
        conn = _conn()
        n = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def local_count() -> int:
    try:
        conn = _conn()
        n = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
        conn.close()
        return int(n)
    except Exception:
        return 0


def local_put(key: str, fixture_id, raw: dict) -> None:
    """Grava/atualiza um jogo no espelho local (idempotente). Silencioso em falha."""
    try:
        conn = _conn()
        conn.execute("INSERT OR REPLACE INTO raw(key, fixture_id, raw) VALUES (?,?,?)",
                     (key, fixture_id, json.dumps(raw, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AVISO] raw_cache.local_put {key}: {e}")


def iter_all_raw():
    """Itera todos os `raw` (dicts) do detalhe de jogos — do SQLite LOCAL se disponível
    (zero Neon), senão faz fallback para o Neon (leitura streaming)."""
    if local_available():
        conn = _conn()
        try:
            cur = conn.execute("SELECT raw FROM raw")
            for (rawj,) in cur:
                try:
                    yield json.loads(rawj)
                except Exception:
                    continue
        finally:
            conn.close()
    else:
        from app.db.connection import engine
        from sqlalchemy import text
        with engine.connect().execution_options(stream_results=True) as c:
            for (rawj,) in c.execute(text("SELECT raw FROM match_detail_cache")):
                try:
                    yield json.loads(rawj) if isinstance(rawj, str) else rawj
                except Exception:
                    continue


def mirror_from_neon(tables=("match_detail_cache",)) -> int:
    """Backfill único: copia o bruto do Neon para o SQLite local (uma leitura ~44 MB).
    A partir daí os jobs leem local. Retorna o nº de linhas copiadas."""
    from app.db.connection import engine
    from sqlalchemy import text
    conn = _conn()
    n = 0
    with engine.connect().execution_options(stream_results=True) as c:
        for tbl in tables:
            try:
                for (key, fid, rawj) in c.execute(text(f"SELECT key, fixture_id, raw FROM {tbl}")):
                    conn.execute("INSERT OR REPLACE INTO raw(key, fixture_id, raw) VALUES (?,?,?)",
                                 (key, fid, rawj if isinstance(rawj, str) else json.dumps(rawj, ensure_ascii=False)))
                    n += 1
            except Exception as e:
                print(f"[AVISO] mirror_from_neon {tbl}: {e}")
    conn.commit()
    conn.close()
    return n
