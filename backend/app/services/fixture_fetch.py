"""
app/services/fixture_fetch.py
=============================
Busca e CACHE de detalhe de partidas da api-football, persistido no Neon
(disco do Render é efêmero). Primitivo compartilhado por:
  - get_match_detail (Estatísticas): base/cache -> API -> cache.
  - precache das seleções da Copa.
  - coleta diária de jogos resolvidos.

O detalhe completo de uma partida (events/lineups/players/statistics) vem de UMA
chamada: GET /fixtures?id={fixture_id}.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import httpx  # já é dependência (requirements); 'requests' não está instalado no Render
from sqlalchemy import text

BASE = "https://v3.football.api-sports.io"
CACHE_TABLE = "match_detail_cache"


def _key() -> str:
    # Em produção (Render) a var vem do ambiente; localmente carregamos backend/.env.
    k = os.environ.get("APIFOOTBALL_KEY") or os.environ.get("API_FOOTBALL_KEY")
    if not k:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("APIFOOTBALL_KEY=") or line.startswith("API_FOOTBALL_KEY="):
                    k = line.split("=", 1)[1].strip()
                    break
    if not k:
        raise RuntimeError("APIFOOTBALL_KEY ausente (env/.env).")
    return k


def _get(path: str, **params) -> tuple[list, Optional[str]]:
    r = httpx.get(BASE + path, headers={"x-apisports-key": _key()}, params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("response", []), r.headers.get("x-ratelimit-requests-remaining")


_table_ready = False


def _ensure_table():
    global _table_ready
    if _table_ready:
        return
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"CREATE TABLE IF NOT EXISTS {CACHE_TABLE} ("
            "key TEXT PRIMARY KEY, fixture_id BIGINT, raw TEXT, cached_at TIMESTAMPTZ DEFAULT now())"
        ))
    _table_ready = True


def cache_get(key: str) -> Optional[dict]:
    try:
        _ensure_table()
        from app.db.connection import engine
        with engine.connect() as c:
            row = c.execute(text(f"SELECT raw FROM {CACHE_TABLE} WHERE key=:k"), {"k": key}).first()
        return json.loads(row[0]) if row and row[0] else None
    except Exception as e:
        print(f"[ERRO DB] cache_get {key}: {e}")
        return None


def cache_put(key: str, fixture_id: Optional[int], raw: dict):
    try:
        _ensure_table()
        from app.db.connection import engine
        with engine.begin() as c:
            c.execute(text(
                f"INSERT INTO {CACHE_TABLE} (key, fixture_id, raw, cached_at) "
                "VALUES (:k, :f, :r, now()) "
                "ON CONFLICT (key) DO UPDATE SET fixture_id=EXCLUDED.fixture_id, raw=EXCLUDED.raw, cached_at=now()"
            ), {"k": key, "f": fixture_id, "r": json.dumps(raw, ensure_ascii=False)})
    except Exception as e:
        print(f"[ERRO DB] cache_put {key}: {e}")


def fetch_full_by_id(fixture_id: int) -> Optional[dict]:
    """Detalhe completo (events/lineups/players/statistics) de uma fixture."""
    resp, _ = _get("/fixtures", id=fixture_id)
    return resp[0] if resp else None


def resolve_fixture_id(home_id: int, away_id: Optional[int], away_name: str, d10: str) -> Optional[int]:
    """Acha o fixture_id de uma partida do time `home_id` contra `away_name` na data
    d10. O filtro `date=` da api-football às vezes não retorna o jogo (timezone), então
    caímos para a busca por temporada. Casa as duas orientações (home/away)."""
    from predictor import TEAM_ALIASES  # noqa
    def norm(n): return (TEAM_ALIASES.get(n, n) if n else n) or ""
    target = norm(away_name).lower()

    def find(resp):
        for f in resp:
            if ((f.get("fixture") or {}).get("date") or "")[:10] != d10:
                continue
            t = f.get("teams") or {}
            for side in ("home", "away"):
                o = t.get(side) or {}
                if (away_id and o.get("id") == away_id) or norm(o.get("name")).lower() == target:
                    return (f.get("fixture") or {}).get("id")
        return None

    resp, _ = _get("/fixtures", date=d10, team=home_id)
    fid = find(resp)
    if fid:
        return fid
    year = int(d10[:4])
    for s in (year, year - 1):
        resp, _ = _get("/fixtures", team=home_id, season=s)
        fid = find(resp)
        if fid:
            return fid
    return None


def get_or_fetch_detail(home: str, away: str, d10: str, key: str,
                        team_ids: dict[str, int]) -> Optional[dict]:
    """base/cache -> API -> cache. Retorna o dict cru da fixture (ou None)."""
    cached = cache_get(key)
    if cached is not None:
        return cached
    hid = team_ids.get(home); aid = team_ids.get(away)
    if not hid:
        return None
    try:
        fid = resolve_fixture_id(hid, aid, away, d10)
        if not fid:
            return None
        d = fetch_full_by_id(fid)
        if d:
            cache_put(key, fid, d)
        return d
    except Exception as e:
        print(f"[AVISO] fetch detalhe {key}: {e}")
        return None


def recent_fixture_ids(team_id: int, last: int = 5) -> list[dict]:
    """Últimas N partidas (resolvidas) de um time: lista de fixtures base."""
    resp, _ = _get("/fixtures", team=team_id, last=last)
    return resp
