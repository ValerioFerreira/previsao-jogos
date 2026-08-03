"""
app/services/club_live_topup.py
================================
"Top-up" de dados de clube disparado por tráfego real (não é o backfill exaustivo,
que é outro processo -- ver backend/scripts/prefetch_clubs_exhaustive.py /
discover_team_leagues.py, construído em paralelo por outro agente).

Duas funções:
  - fetch_live_h2h: SÍNCRONA, chamada dentro do request de /predict quando o
    confronto direto local não tem NENHUM jogo conhecido (h2h_played == 0).
    Timeout agressivo -- nunca deixa a análise mais lenta que o timeout, e nunca
    quebra a resposta (qualquer erro vira lista vazia).
  - topup_team_history_background: ASSÍNCRONA (BackgroundTasks do FastAPI), roda
    DEPOIS da resposta já ter sido enviada ao cliente. Busca jogos recentes (2
    temporadas) de um time e grava o que faltar em `club_match_detail_cache` no
    Neon -- decisão já tomada com o dono: o disco do Render é efêmero, então o
    cache do top-up orgânico tem que ir para o Neon (não para o espelho sqlite
    local), mesmo que isso reintroduza um pouco de crescimento nessa tabela
    (volume pequeno: só times que usuários de verdade buscam).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

import httpx
from sqlalchemy import text

from app.services.fixture_fetch import BASE, _key

logger = logging.getLogger("app.services.club_live_topup")

FINISHED = {"FT", "AET", "PEN"}
CACHE_TABLE = "club_match_detail_cache"

# --------------------------------------------------------------------- h2h síncrono


def fetch_live_h2h(home_id: int, away_id: int, home_name: str = None, away_name: str = None,
                    timeout: float = 3.0) -> list[dict]:
    """Busca o confronto direto na api-football (GET /fixtures/headtohead).
    Timeout agressivo e à prova de falha -- qualquer problema (timeout, erro HTTP,
    chave ausente) retorna lista vazia silenciosamente, só um log de aviso.

    Os dicts retornados usam os NOMES CANÔNICOS (home_name/away_name, já resolvidos
    pelo chamador via Predictor.norm_team) -- nunca o nome cru vindo da API. O lado
    (home/away) é decidido comparando o `team.id` de cada fixture contra
    home_id/away_id (o mando pode estar invertido em relação ao par pedido).

    Se home_name/away_name não forem passados, usa o nome cru da API como fallback
    (só acontece se o chamador não resolveu os nomes -- não deveria, na prática).
    """
    if not home_id or not away_id:
        return []
    try:
        r = httpx.get(
            f"{BASE}/fixtures/headtohead",
            headers={"x-apisports-key": _key()},
            params={"h2h": f"{home_id}-{away_id}"},
            timeout=timeout,
        )
        r.raise_for_status()
        resp = r.json().get("response", []) or []
    except Exception as e:
        logger.warning("fetch_live_h2h(%s,%s): %s", home_id, away_id, e)
        return []

    out = []
    try:
        for fx in resp:
            status = ((fx.get("fixture") or {}).get("status") or {}).get("short")
            if status not in FINISHED:
                continue
            teams = fx.get("teams") or {}
            t_home = teams.get("home") or {}
            goals = fx.get("goals") or {}
            date_iso = (fx.get("fixture") or {}).get("date")
            hs, as_ = goals.get("home"), goals.get("away")
            if not date_iso or hs is None or as_ is None:
                continue
            # decide qual lado é o nosso "home_id"/"away_id" pelo id cru da API.
            if t_home.get("id") == home_id:
                row_home, row_away = (home_name or t_home.get("name")), (away_name or (teams.get("away") or {}).get("name"))
                row_hs, row_as = hs, as_
            elif t_home.get("id") == away_id:
                row_home, row_away = (home_name or (teams.get("away") or {}).get("name")), (away_name or t_home.get("name"))
                row_hs, row_as = as_, hs
            else:
                continue
            league = fx.get("league") or {}
            out.append({
                "home_team": row_home, "away_team": row_away,
                "home_score": row_hs, "away_score": row_as,
                "date": date_iso[:10], "tournament": league.get("name"),
            })
    except Exception as e:
        logger.warning("fetch_live_h2h(%s,%s) parse: %s", home_id, away_id, e)
        return []
    return out


# --------------------------------------------------------------------- backfill leve em background

_recently_checked: dict[int, float] = {}
_recently_checked_lock = threading.Lock()
_RECHECK_TTL_SECONDS = 6 * 3600  # 6h

_MAX_DETAIL_CALLS = 20  # teto de chamadas de detalhe por invocação -- resto fica p/ próxima vez
_QUOTA_FLOOR = 20000    # abaixo disso, aborta -- protege a cota das coletas agendadas


def _already_checked_recently(team_id: int) -> bool:
    now = time.time()
    with _recently_checked_lock:
        ts = _recently_checked.get(team_id)
        if ts is not None and (now - ts) < _RECHECK_TTL_SECONDS:
            return True
        _recently_checked[team_id] = now
        return False


def _ensure_table():
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"CREATE TABLE IF NOT EXISTS {CACHE_TABLE} ("
            "key TEXT PRIMARY KEY, fixture_id BIGINT, league_id INT, season INT, raw TEXT, "
            "cached_at TIMESTAMPTZ DEFAULT now())"
        ))


def topup_team_history_background(team_id: int, team_name: str, seasons: int = 2) -> None:
    """Fire-and-forget: roda em BackgroundTasks DEPOIS da resposta já ter sido
    enviada. Nunca deixa exceção subir -- ninguém está esperando o resultado.

    Propositalmente SÍNCRONA (não `async def`): o corpo faz várias chamadas HTTP
    bloqueantes (httpx.get síncrono) + queries SQLAlchemy bloqueantes. Se fosse uma
    coroutine, o Starlette a executaria direto no event loop e ela bloquearia TODAS
    as outras requisições concorrentes no mesmo worker pelo tempo inteiro do top-up
    (até ~40 chamadas HTTP) -- confirmado localmente (uma segunda requisição chegou
    a esperar ~25s pelo top-up da primeira). Sendo síncrona, o Starlette despacha
    para uma threadpool automaticamente (BackgroundTask.__call__ -> run_in_threadpool
    quando `iscoroutinefunction(func)` é False), liberando o event loop.
    """
    try:
        _topup_team_history_background_impl(team_id, team_name, seasons)
    except Exception as e:
        logger.warning("topup_team_history_background(%s/%s): %s", team_id, team_name, e)


def _topup_team_history_background_impl(team_id: int, team_name: str, seasons: int) -> None:
    if not team_id:
        return
    if _already_checked_recently(team_id):
        return

    try:
        import scripts.quota_tracker as quota_tracker
    except Exception as e:
        logger.warning("quota_tracker indisponível, abortando top-up: %s", e)
        return

    try:
        if quota_tracker.remaining() < _QUOTA_FLOOR:
            logger.info("top-up de %s (%s) abortado: cota abaixo do piso de %d", team_name, team_id, _QUOTA_FLOOR)
            return
    except Exception as e:
        # não sabemos a cota real -- por segurança, não gasta.
        logger.warning("quota_tracker.remaining() falhou, abortando top-up: %s", e)
        return

    current_year = datetime.now().year
    target_seasons = [current_year - i for i in range(max(1, seasons))]

    _ensure_table()
    from app.db.connection import engine

    calls_used = 0
    for season in target_seasons:
        if calls_used >= _MAX_DETAIL_CALLS:
            break
        try:
            r = httpx.get(
                f"{BASE}/fixtures",
                headers={"x-apisports-key": _key()},
                params={"team": team_id, "season": season},
                timeout=10.0,
            )
            r.raise_for_status()
            quota_tracker.note_call()
            fixtures = r.json().get("response", []) or []
        except Exception as e:
            logger.warning("top-up fixtures %s/%s: %s", team_id, season, e)
            continue

        finished = []
        for fx in fixtures:
            status = ((fx.get("fixture") or {}).get("status") or {}).get("short")
            fid = (fx.get("fixture") or {}).get("id")
            if status in FINISHED and fid:
                finished.append((fid, fx))
        if not finished:
            continue

        ids = [fid for fid, _ in finished]
        try:
            with engine.connect() as c:
                rows = c.execute(
                    text(f"SELECT fixture_id FROM {CACHE_TABLE} WHERE fixture_id = ANY(:ids)"),
                    {"ids": ids},
                ).fetchall()
            existing = {row[0] for row in rows}
        except Exception as e:
            logger.warning("top-up SELECT fixture_id existentes %s/%s: %s", team_id, season, e)
            existing = set()

        missing = [(fid, fx) for fid, fx in finished if fid not in existing]
        if not missing:
            continue
        # mais recentes primeiro
        missing.sort(key=lambda t: (t[1].get("fixture") or {}).get("date") or "", reverse=True)

        batch = []
        for fid, fx in missing:
            if calls_used >= _MAX_DETAIL_CALLS:
                break
            try:
                rd = httpx.get(
                    f"{BASE}/fixtures",
                    headers={"x-apisports-key": _key()},
                    params={"id": fid},
                    timeout=10.0,
                )
                rd.raise_for_status()
                quota_tracker.note_call()
                calls_used += 1
                detail_resp = rd.json().get("response", []) or []
            except Exception as e:
                logger.warning("top-up detalhe fixture %s: %s", fid, e)
                continue
            if not detail_resp:
                continue
            detail = detail_resp[0]
            league_id = (fx.get("league") or {}).get("id")
            key = f"club|{league_id}|{fid}"
            batch.append({"key": key, "fixture_id": fid, "league_id": league_id,
                           "season": season, "raw": detail})

        if batch:
            import json
            try:
                with engine.begin() as c:
                    c.execute(
                        text(
                            f"INSERT INTO {CACHE_TABLE} (key, fixture_id, league_id, season, raw, cached_at) "
                            "VALUES (:key, :fixture_id, :league_id, :season, :raw, now()) "
                            "ON CONFLICT (key) DO UPDATE SET raw=EXCLUDED.raw, cached_at=now()"
                        ),
                        [{**b, "raw": json.dumps(b["raw"], ensure_ascii=False)} for b in batch],
                    )
                logger.info("top-up gravou %d fixtures novas de %s (season %s)", len(batch), team_name, season)
            except Exception as e:
                logger.warning("top-up INSERT %s/%s: %s", team_id, season, e)
