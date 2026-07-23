from __future__ import annotations

import os
import json
import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
import pandas as pd

from predictor import Predictor, TEAM_ALIASES
from app.services.odds import enrich_with_odds
from anomaly_detector import detect_anomalies


def _json_safe(obj):
    """Substitui NaN/Infinity (float) por None recursivamente. `json.dumps` padrão
    aceita NaN como token literal, mas o parser JSON/JSONB do Postgres não -- o
    INSERT em app_analyses.snapshot::JSONB falhava (DataError, "Token NaN is
    invalid") pra QUALQUER par de times sem confronto direto anterior (h2h com
    campos NaN), virando 500 pro cliente (às vezes mascarado como erro de CORS,
    achado 2026-07-22). Fonte já corrigida em predictor.py::head_to_head/
    predict_from_row (usam None, não NaN); isto aqui é a rede de segurança pro
    resto da resposta, caso outro campo numérico algum dia vire NaN."""
    if isinstance(obj, float):
        return obj if (obj == obj and obj not in (float("inf"), float("-inf"))) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _norm(name: str) -> str:
    """Canoniza nome de seleção (alias) — leve, para listas e lookups."""
    return TEAM_ALIASES.get(name, name) if name else name


def _fix_mojibake(s: str | None) -> str | None:
    """Repara texto UTF-8 duplo-codificado vindo da fonte (ex.: 'PaquetÃ¡' -> 'Paquetá').
    Só age quando há marcadores típicos e o resultado é válido, preservando nomes corretos."""
    if not s or not any(m in s for m in ("Ã", "Â", "â€")):
        return s
    try:
        r = s.encode("latin-1").decode("utf-8")
        return r if "�" not in r else s
    except UnicodeError:
        return s


import functools as _functools
_READER_MEMO: dict = {}


def _cache_nonempty(fn):
    """Como lru_cache(maxsize=1) para funções sem args, MAS só memoriza resultado
    não-vazio. Evita 'envenenar' o cache com [] / {} de uma falha transitória de
    cold-start do Neon (que deixava árbitros/times vazios até reiniciar o processo)."""
    @_functools.wraps(fn)
    def wrapper():
        name = fn.__name__
        if name in _READER_MEMO:
            return _READER_MEMO[name]
        v = fn()
        if v:
            _READER_MEMO[name] = v
        return v
    return wrapper


API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT
ARTIFACT_DIR = API_ROOT / "model_artifacts"
ARTIFACT_DIR_CLUBES = API_ROOT / "model_artifacts_clubes"
PARQUET_PATH = REPO_ROOT / "data" / "built" / "matches.parquet"
LAST_UPDATE_PATH = REPO_ROOT / "data" / "state" / "last_update.json"
LOG_FILE_PATH = REPO_ROOT / "data" / "state" / "predictions_log.jsonl"
REFEREES_PATH = REPO_ROOT / "data" / "built" / "referees.json"
TEAM_IDS_PATH = REPO_ROOT / "data" / "built" / "team_ids.json"
ODDS_REGISTRY_PATH = REPO_ROOT / "data" / "odds" / "registry.json"


@_cache_nonempty
def get_referees() -> list[str]:
    """Lista de árbitros (autocomplete). Extraída da base de dados."""
    from app.db.connection import engine
    try:
        df = pd.read_sql("SELECT name FROM referees ORDER BY name ASC", con=engine)
        return df["name"].tolist()
    except Exception as e:
        print(f"[ERRO DB] referees: {e}")
        return []


# Alias explícitos nome-canônico -> chave presente no team_ids (quando a normalização
# "loose" não casa: FYR vs North, Mação vs Macau).
_TEAM_ID_ALIASES = {
    "North Macedonia": "FYR Macedonia",
    "Macau": "Mação",
}


def _loose_team_key(s: str) -> str:
    """Chave frouxa p/ casar grafias: sem acento, minúscula, &->and, Rep.->Republic,
    remove FYR/Islands e pontuação."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace(".", " ")
    s = re.sub(r"\brep\b", "republic", s)
    s = re.sub(r"\bfyr\b", "", s)
    s = re.sub(r"\bislands?\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


_TEAM_IDS_MEMO: dict[str, dict[str, int]] = {}


def get_team_ids(scope: str = "selecao") -> dict[str, int]:
    """Mapa nome_do_time -> team_id (para logo E busca de partidas antigas).
    Resolve grafias divergentes (ex.: 'Bosnia and Herzegovina' vs 'Bosnia & Herzegovina',
    'North Macedonia' vs 'FYR Macedonia') casando os nomes canônicos por normalização
    frouxa + aliases, para que todo time com id disponível fique acessível pelo nome.
    A tabela `team_ids` do Neon só é preenchida para seleção (`build_referees_and_team_ids.py`,
    fonte = cache de fixtures de seleção) -- clube resolve localmente a partir do próprio
    `meta.json` do artefato (`team_ids`, já com nomes desambiguados/limpos, ver
    `build_clubs_production_artifacts.py`), sem tocar o Neon."""
    if scope in _TEAM_IDS_MEMO:
        return _TEAM_IDS_MEMO[scope]

    if scope == "clube":
        try:
            raw = dict(_predictor_for("clube").meta.get("team_ids", {}))
        except Exception as e:
            print(f"[ERRO] team_ids (clube): {e}")
            raw = {}
    else:
        from app.db.connection import engine
        try:
            df = pd.read_sql("SELECT team_name, team_id FROM team_ids", con=engine)
            raw = dict(zip(df["team_name"], df["team_id"]))
        except Exception as e:
            print(f"[ERRO DB] team_ids: {e}")
            raw = {}

    out = dict(raw)
    for name, tid in raw.items():
        out.setdefault(_norm(name), tid)

    # índice frouxo das chaves cruas
    loose_idx: dict[str, int] = {}
    for name, tid in raw.items():
        loose_idx.setdefault(_loose_team_key(name), tid)

    # resolve cada nome canônico (do escopo pedido) que ainda não tem id
    try:
        canon = _predictor_for(scope).teams()
    except Exception:
        canon = []
    for name in canon:
        if name in out:
            continue
        tid = None
        alias = _TEAM_ID_ALIASES.get(name)
        if alias and alias in raw:
            tid = raw[alias]
        if tid is None:
            tid = loose_idx.get(_loose_team_key(name))
        if tid is not None:
            out[name] = tid
    if out:
        _TEAM_IDS_MEMO[scope] = out
    return out


FIXTURE_INDEX_PATH = REPO_ROOT / "data" / "built" / "fixture_index.json"
PAST_FIXTURES_PATH = REPO_ROOT / "data" / "built" / "past_fixtures.json"


@_cache_nonempty
def get_past_fixtures() -> list[dict[str, Any]]:
    """Lista de partidas já disputadas (para o seletor de Partidas Passadas)."""
    from app.db.connection import engine
    try:
        query = "SELECT * FROM past_fixtures ORDER BY date DESC"
        df = pd.read_sql(query, con=engine)
        raw = df.to_dict(orient="records")
    except Exception as e:
        print(f"[ERRO DB] past_fixtures: {e}")
        raw = []
        
    for f in raw:
        f["home"] = _norm(f.get("home"))
        f["away"] = _norm(f.get("away"))
        if not f.get("scope"):
            t = str(f.get("tournament") or f.get("league_name") or "").lower()
            is_club = any(x in t for x in [
                "serie a", "serie b", "brasileirao", "copa do brasil", 
                "premier league", "championship", "la liga", "champions league", 
                "libertadores", "sul-americana", "sudamericana", "bundesliga", 
                "ligue 1", "serie a italia", "copa del rey", "dfb pokal", 
                "fa cup", "primeira liga", "eredivisie"
            ])
            f["scope"] = "clube" if is_club else "selecao"
    return raw


@_cache_nonempty
def _fixture_index() -> dict[str, str]:
    from app.db.connection import engine
    try:
        df = pd.read_sql("SELECT key, path FROM fixture_index", con=engine)
        return dict(zip(df["key"], df["path"]))
    except Exception as e:
        print(f"[ERRO DB] fixture_index: {e}")
        return {}


@_cache_nonempty
def _fixture_index_norm() -> dict[str, str]:
    """Índice com chaves canonizadas (date|norm(home)|norm(away)) -> caminho."""
    idx = {}
    for k, path in _fixture_index().items():
        parts = k.split("|")
        if len(parts) == 3:
            idx[f"{parts[0]}|{_norm(parts[1])}|{_norm(parts[2])}"] = path
    return idx


def get_match_detail(home: str, away: str, date: str, scope: str = "selecao") -> dict[str, Any]:
    """Wrapper defensivo: NUNCA propaga exceção (um 500 não leva header CORS e o
    browser mascara como erro de CORS). Em qualquer falha, devolve found=False."""
    try:
        return _match_detail_impl(home, away, date, scope=scope)
    except Exception as e:
        print(f"[ERRO match_detail] {home} x {away} {date}: {type(e).__name__}: {e}")
        return {"found": False}


def _match_detail_impl(home: str, away: str, date: str, scope: str = "selecao") -> dict[str, Any]:
    """Detalhe completo de uma partida JÁ DISPUTADA: cache(Neon) -> .gz local -> API / base local de clubes.
    Robusto a dados ausentes (jogos antigos/ligas menores).
    """
    import gzip
    from app.services.fixture_fetch import cache_get, get_or_fetch_detail
    d10 = date[:10]
    key = f"{d10}|{_norm(home)}|{_norm(away)}"

    if scope == "clube":
        df = _load_club_matches_long()
        if not df.empty:
            from predictor import TEAM_ALIASES
            nhome = TEAM_ALIASES.get(home, home)
            naway = TEAM_ALIASES.get(away, away)
            df_match = df[(df["date"].dt.strftime("%Y-%m-%d") == d10) & 
                          (((df["team"] == nhome) & (df["opponent"] == naway)) | 
                           ((df["team"] == naway) & (df["opponent"] == nhome)))]
            if not df_match.empty:
                home_row = df_match[df_match["team"] == nhome]
                away_row = df_match[df_match["team"] == naway]
                if home_row.empty and not away_row.empty:
                    ar = away_row.iloc[0]
                    h_goals = int(ar["goals_conceded"])
                    a_goals = int(ar["goals_scored"])
                    comp = str(ar["competition"])
                    h_shots, a_shots = 0.0, float(ar["sb_shots"]) if pd.notna(ar.get("sb_shots")) else 0.0
                    h_sot, a_sot = 0.0, float(ar["sb_shots_on_target"]) if pd.notna(ar.get("sb_shots_on_target")) else 0.0
                    h_corners, a_corners = 0.0, float(ar["sb_corners"]) if pd.notna(ar.get("sb_corners")) else 0.0
                    h_cards, a_cards = 0.0, float(ar["sb_cards"]) if pd.notna(ar.get("sb_cards")) else 0.0
                    h_fouls, a_fouls = 0.0, float(ar["sb_fouls"]) if pd.notna(ar.get("sb_fouls")) else 0.0
                    h_offsides, a_offsides = 0.0, float(ar["sb_offsides"]) if pd.notna(ar.get("sb_offsides")) else 0.0
                    h_poss, a_poss = 0.0, float(ar["sb_possession"]) if pd.notna(ar.get("sb_possession")) else 0.0
                    h_passes, a_passes = 0.0, float(ar["sb_passes"]) if pd.notna(ar.get("sb_passes")) else 0.0
                else:
                    hr = home_row.iloc[0]
                    h_goals = int(hr["goals_scored"])
                    a_goals = int(hr["goals_conceded"])
                    comp = str(hr["competition"])
                    h_shots = float(hr["sb_shots"]) if pd.notna(hr.get("sb_shots")) else 0.0
                    h_sot = float(hr["sb_shots_on_target"]) if pd.notna(hr.get("sb_shots_on_target")) else 0.0
                    h_corners = float(hr["sb_corners"]) if pd.notna(hr.get("sb_corners")) else 0.0
                    h_cards = float(hr["sb_cards"]) if pd.notna(hr.get("sb_cards")) else 0.0
                    h_fouls = float(hr["sb_fouls"]) if pd.notna(hr.get("sb_fouls")) else 0.0
                    h_offsides = float(hr["sb_offsides"]) if pd.notna(hr.get("sb_offsides")) else 0.0
                    h_poss = float(hr["sb_possession"]) if pd.notna(hr.get("sb_possession")) else 0.0
                    h_passes = float(hr["sb_passes"]) if pd.notna(hr.get("sb_passes")) else 0.0

                    if not away_row.empty:
                        ar = away_row.iloc[0]
                        a_shots = float(ar["sb_shots"]) if pd.notna(ar.get("sb_shots")) else 0.0
                        a_sot = float(ar["sb_shots_on_target"]) if pd.notna(ar.get("sb_shots_on_target")) else 0.0
                        a_corners = float(ar["sb_corners"]) if pd.notna(ar.get("sb_corners")) else 0.0
                        a_cards = float(ar["sb_cards"]) if pd.notna(ar.get("sb_cards")) else 0.0
                        a_fouls = float(ar["sb_fouls"]) if pd.notna(ar.get("sb_fouls")) else 0.0
                        a_offsides = float(ar["sb_offsides"]) if pd.notna(ar.get("sb_offsides")) else 0.0
                        a_poss = float(ar["sb_possession"]) if pd.notna(ar.get("sb_possession")) else 0.0
                        a_passes = float(ar["sb_passes"]) if pd.notna(ar.get("sb_passes")) else 0.0
                    else:
                        a_shots = a_sot = a_corners = a_cards = a_fouls = a_offsides = a_poss = a_passes = 0.0

                return {
                    "found": True,
                    "info": {
                        "date": d10,
                        "status": "Match Finished",
                        "referee": None,
                        "venue": None,
                        "city": None,
                        "league": comp,
                        "league_logo": None,
                        "country": None,
                        "season": d10[:4],
                        "round": None,
                        "home": nhome,
                        "home_id": None,
                        "away": naway,
                        "away_id": None,
                    },
                    "goals": {"home": h_goals, "away": a_goals},
                    "score": {"fulltime": {"home": h_goals, "away": a_goals}},
                    "statistics": [
                        {
                            "team": nhome,
                            "stats": {
                                "Shots on Goal": h_sot,
                                "Total Shots": h_shots,
                                "Corner Kicks": h_corners,
                                "Fouls": h_fouls,
                                "Yellow Cards": h_cards,
                                "Offsides": h_offsides,
                                "Ball Possession": f"{h_poss:.0f}%" if h_poss else None,
                                "Total passes": h_passes,
                            }
                        },
                        {
                            "team": naway,
                            "stats": {
                                "Shots on Goal": a_sot,
                                "Total Shots": a_shots,
                                "Corner Kicks": a_corners,
                                "Fouls": a_fouls,
                                "Yellow Cards": a_cards,
                                "Offsides": a_offsides,
                                "Ball Possession": f"{a_poss:.0f}%" if a_poss else None,
                                "Total passes": a_passes,
                            }
                        }
                    ],
                    "events": [],
                    "lineups": [],
                    "players": []
                }

    d = cache_get(key)  # 1) cache no Neon (preenchido pela API/precache)
    if d is None:       # 2) .gz local (dev)
        rel = (_fixture_index().get(f"{d10}|{home}|{away}")
               or _fixture_index_norm().get(key))
        if rel:
            try:
                d = json.load(gzip.open(REPO_ROOT / rel))
            except Exception:
                d = None
    if d is None:       # 3) API ao vivo (e cacheia no Neon para a próxima)
        d = get_or_fetch_detail(_norm(home), _norm(away), d10, key, get_team_ids(scope))
    if d is None:
        return {"found": False}

    fx = d.get("fixture") or {}
    lg = d.get("league") or {}
    teams = d.get("teams") or {}
    th, ta = teams.get("home") or {}, teams.get("away") or {}
    venue = fx.get("venue") or {}

    def _stats_block(entry):
        return {
            "team": (entry.get("team") or {}).get("name"),
            "team_id": (entry.get("team") or {}).get("id"),
            "stats": {s.get("type"): s.get("value") for s in (entry.get("statistics") or [])},
        }

    def _lineup_block(entry):
        def _pl(p):
            pl = (p or {}).get("player") or {}
            return {"id": pl.get("id"), "name": pl.get("name"),
                    "number": pl.get("number"), "pos": pl.get("pos"), "grid": pl.get("grid")}
        coach = entry.get("coach") or {}
        return {
            "team": (entry.get("team") or {}).get("name"),
            "team_id": (entry.get("team") or {}).get("id"),
            "formation": entry.get("formation"),
            "coach": {"id": coach.get("id"), "name": coach.get("name")},
            "startXI": [_pl(p) for p in (entry.get("startXI") or [])],
            "substitutes": [_pl(p) for p in (entry.get("substitutes") or [])],
        }

    def _player_block(entry):
        out = []
        for p in (entry.get("players") or []):
            pl = p.get("player") or {}
            st = (p.get("statistics") or [{}])[0]
            g = st.get("games") or {}
            out.append({
                "id": pl.get("id"), "name": pl.get("name"),
                "pos": g.get("position"), "number": g.get("number"),
                "rating": g.get("rating"), "minutes": g.get("minutes"),
                "goals": (st.get("goals") or {}).get("total"),
                "assists": (st.get("goals") or {}).get("assists"),
                "shots_total": (st.get("shots") or {}).get("total"),
                "shots_on": (st.get("shots") or {}).get("on"),
                "passes": (st.get("passes") or {}).get("total"),
                "key_passes": (st.get("passes") or {}).get("key"),
                "tackles": (st.get("tackles") or {}).get("total"),
                "yellow": (st.get("cards") or {}).get("yellow"),
                "red": (st.get("cards") or {}).get("red"),
            })
        return {"team": (entry.get("team") or {}).get("name"),
                "team_id": (entry.get("team") or {}).get("id"), "players": out}

    events = []
    for e in (d.get("events") or []):
        t = e.get("time") or {}
        events.append({
            "minute": t.get("elapsed"), "extra": t.get("extra"),
            "type": e.get("type"), "detail": e.get("detail"),
            "team": (e.get("team") or {}).get("name"),
            "team_id": (e.get("team") or {}).get("id"),
            "player": (e.get("player") or {}).get("name"),
            "assist": (e.get("assist") or {}).get("name"),
        })
    events.sort(key=lambda x: (x["minute"] or 0, x["extra"] or 0))

    score = d.get("score") or {}
    return {
        "found": True,
        "info": {
            "date": fx.get("date"),
            "status": (fx.get("status") or {}).get("long"),
            "referee": fx.get("referee"),
            "venue": venue.get("name"), "city": venue.get("city"),
            "league": lg.get("name"), "league_logo": lg.get("logo"),
            "country": lg.get("country"), "season": lg.get("season"), "round": lg.get("round"),
            "home": _norm(th.get("name")), "home_id": th.get("id"),
            "away": _norm(ta.get("name")), "away_id": ta.get("id"),
        },
        "goals": d.get("goals") or {},
        "score": {"halftime": score.get("halftime"), "fulltime": score.get("fulltime"),
                  "extratime": score.get("extratime"), "penalty": score.get("penalty")},
        "statistics": [_stats_block(s) for s in (d.get("statistics") or [])],
        "events": events,
        "lineups": [_lineup_block(l) for l in (d.get("lineups") or [])],
        "players": [_player_block(p) for p in (d.get("players") or [])],
    }


def _load_registry() -> dict[str, dict]:
    """Registry de jogos futuros. Fonte primária: tabela odds_registry no Neon
    (produção, mantida fresca pelo coletor local). Fallback: arquivo local do
    coletor (dev). Assim o Render serve partidas futuras sem disco local."""
    from app.db.connection import engine
    try:
        df = pd.read_sql("SELECT * FROM odds_registry", con=engine)
        if not df.empty:
            return {str(r["fixture_id"]): r for r in df.to_dict(orient="records")}
    except Exception as e:
        print(f"[ERRO DB] odds_registry: {e}")
    if ODDS_REGISTRY_PATH.exists():
        try:
            return json.loads(ODDS_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _load_club_registry() -> dict[str, dict]:
    """Registry de jogos futuros de CLUBE -- tabela separada `club_odds_registry`
    (nunca mistura com `odds_registry` de seleções, ver collect_club_odds_forward.py)."""
    from app.db.connection import engine
    try:
        df = pd.read_sql("SELECT * FROM club_odds_registry", con=engine)
        if not df.empty:
            return {str(r["fixture_id"]): r for r in df.to_dict(orient="records")}
    except Exception as e:
        print(f"[ERRO DB] club_odds_registry: {e}")
    return {}


def get_upcoming_fixtures() -> list[dict[str, Any]]:
    """Partidas futuras a partir do registry do coletor de odds (sem cota nova).
    Já traz tournament/neutral mapeados para o nosso sistema. Mescla seleções
    (odds_registry, scope='selecao') e clubes (club_odds_registry, scope='clube')
    -- o front deriva a análise correta (predictor/mercados) a partir de `scope`,
    sem o usuário precisar escolher manualmente."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = []

    reg = _load_registry()
    for fid, info in reg.items():
        date = info.get("fixture_date", "")
        if date and date < now:
            continue  # já ocorreu
        out.append({
            "fixture_id": fid,
            "home": _norm(info.get("home")),
            "away": _norm(info.get("away")),
            "tournament": info.get("tournament", "Amistoso"),
            "neutral": bool(info.get("neutral", False)),
            "date": date,
            "league_name": info.get("league_name", ""),
            "league_id": info.get("league_id"),
            "scope": "selecao",
        })

    club_reg = _load_club_registry()
    for fid, info in club_reg.items():
        date = info.get("fixture_date", "")
        if date and date < now:
            continue
        tournament = info.get("league_name") or "Clubes"
        out.append({
            "fixture_id": fid,
            "home": info.get("home"),
            "away": info.get("away"),
            "tournament": tournament,
            "neutral": False,  # jogo de clube: mando real, salvo raras finais neutras (fora de escopo hoje)
            "date": date,
            "league_name": tournament,
            "league_id": info.get("league_id"),
            "scope": "clube",
        })

    out.sort(key=lambda x: x["date"] or "")
    return out


@lru_cache(maxsize=1)
def get_predictor() -> Predictor:
    return Predictor(art_dir=str(ARTIFACT_DIR))


@lru_cache(maxsize=1)
def get_club_predictor() -> Predictor:
    return Predictor(art_dir=str(ARTIFACT_DIR_CLUBES))


def _predictor_for(scope: str = "selecao") -> Predictor:
    """Escopo 'clube' usa o Predictor treinado em dados de clube (mesma arquitetura,
    artefatos separados -- ver scripts/build_clubs_production_artifacts.py). Qualquer
    valor != 'clube' cai no Predictor de seleções (compatibilidade retroativa)."""
    return get_club_predictor() if scope == "clube" else get_predictor()


def clean_values(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {key: value for key, value in values.items() if value is not None}


def predict_match(payload: Any, scope: str = "selecao") -> dict[str, Any]:
    predictor = _predictor_for(scope)
    raw = predictor.predict(
        payload.home_team,
        payload.away_team,
        neutral=payload.neutral,
        tournament=payload.tournament,
        home_vals=clean_values(payload.home_vals),
        away_vals=clean_values(payload.away_vals),
        context_overrides=clean_values(payload.context_overrides),
        h2h_overrides=clean_values(payload.h2h_overrides),
    )
    res = {
        **raw,
        "odds": enrich_with_odds(raw, predictor.meta.get("n_train", {})),
    }
    res = _json_safe(res)

    # Módulo 4.1: Registro de Logs em JSON Lines
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_payload = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "home_team": payload.home_team,
            "away_team": payload.away_team,
            "neutral": payload.neutral,
            "tournament": payload.tournament,
            "home_vals": clean_values(payload.home_vals),
            "away_vals": clean_values(payload.away_vals),
            "prediction": res
        }
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_payload, default=str) + "\n")
    except Exception as e:
        # Registrar o erro sem travar a resposta da requisição do usuário
        print(f"[LOG ERROR] Falha ao gravar log de previsão: {e}")

    return res


def get_system_status() -> dict[str, str]:
    """Retorna o timestamp da última atualização bem-sucedida do pipeline."""
    if LAST_UPDATE_PATH.exists():
        try:
            with open(LAST_UPDATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback se o arquivo de timestamp ainda não foi criado
    return {"last_successful_run": "2026-06-22 00:00:00"}


_CLUB_MATCHES_LONG_MEMO: pd.DataFrame | None = None
_CLUB_GOAL_TIMING_MEMO: pd.DataFrame | None = None


def _load_club_matches_long() -> pd.DataFrame:
    """club_matches_long.parquet (scripts/build_club_local_history.py) -- equivalente
    local da tabela `matches` do Neon, mas para clube. Memoizado em processo."""
    global _CLUB_MATCHES_LONG_MEMO
    if _CLUB_MATCHES_LONG_MEMO is None:
        path = ARTIFACT_DIR_CLUBES / "club_matches_long.parquet"
        try:
            df = pd.read_parquet(path)
            df["date"] = pd.to_datetime(df["date"])
        except Exception as e:
            print(f"[AVISO] club_matches_long.parquet: {e}")
            df = pd.DataFrame(columns=["team", "opponent", "date", "competition", "is_home",
                                        "goals_scored", "goals_conceded", "sb_shots",
                                        "sb_shots_on_target", "sb_corners", "sb_cards",
                                        "sb_offsides", "sb_fouls", "sb_possession", "sb_passes"])
        _CLUB_MATCHES_LONG_MEMO = df
    return _CLUB_MATCHES_LONG_MEMO


def _load_club_goal_timing() -> pd.DataFrame:
    global _CLUB_GOAL_TIMING_MEMO
    if _CLUB_GOAL_TIMING_MEMO is None:
        path = ARTIFACT_DIR_CLUBES / "club_goal_timing.parquet"
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            print(f"[AVISO] club_goal_timing.parquet: {e}")
            df = pd.DataFrame(columns=["team", "n_matches"] +
                               [f"scored_{i}" for i in range(6)] + [f"conceded_{i}" for i in range(6)])
        _CLUB_GOAL_TIMING_MEMO = df
    return _CLUB_GOAL_TIMING_MEMO


def _club_recent_matches(team_name: str) -> dict[str, Any]:
    df = _load_club_matches_long()
    sub = df[df["team"] == team_name]
    if sub.empty:
        return {"matches": [], "total_matches": 0}
    sub = sub.sort_values("date", ascending=False)
    matches = []
    for _, row in sub.head(60).iterrows():
        def _f(col):
            v = row.get(col)
            return float(v) if pd.notna(v) else 0.0
        matches.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "opponent": str(row["opponent"]),
            "competition": str(row["competition"]) if pd.notna(row.get("competition")) else "",
            "is_home": bool(row["is_home"]),
            "goals_scored": int(_f("goals_scored")),
            "goals_conceded": int(_f("goals_conceded")),
            "sb_shots": _f("sb_shots"),
            "sb_shots_on_target": _f("sb_shots_on_target"),
            "sb_corners": _f("sb_corners"),
            "sb_cards": _f("sb_cards"),
            "sb_offsides": _f("sb_offsides"),
            "sb_fouls": _f("sb_fouls"),
            "sb_possession": _f("sb_possession"),
            "sb_passes": _f("sb_passes"),
        })
    return {"matches": matches, "total_matches": len(sub)}


def get_recent_matches(team_name: str, scope: str = "selecao") -> dict[str, Any]:
    """Consulta PostgreSQL e extrai as últimas 60 partidas reais da equipe.

    60 (e não 10) para dar sinal suficiente aos cálculos de momentum/tendência da
    página de Estatísticas (comparando os 10 mais recentes com os 50 anteriores).

    Escopo 'clube': lê o equivalente local club_matches_long.parquet (ver
    scripts/build_club_local_history.py) -- 100% local, sem tocar o Neon.
    """
    if scope == "clube":
        return _club_recent_matches(team_name)
    from app.db.connection import engine
    from sqlalchemy import text as _text
    try:
        # Só as colunas usadas + parametrizado (sem f-string).
        query = _text("SELECT date, opponent, competition, is_home, goals_scored, goals_conceded, "
                      "sb_shots, sb_shots_on_target, sb_corners, sb_cards, sb_offsides, sb_fouls, "
                      "sb_possession, sb_passes FROM matches WHERE team = :team ORDER BY date DESC LIMIT 60")
        df_recent = pd.read_sql(query, con=engine, params={"team": team_name})

        total_df = pd.read_sql(_text("SELECT COUNT(*) as count FROM matches WHERE team = :team"),
                               con=engine, params={"team": team_name})
        total_matches = int(total_df.iloc[0]["count"]) if not total_df.empty else 0
    except Exception as e:
        print(f"[ERRO DB] {e}")
        return {"matches": [], "total_matches": 0}
        
    if total_matches == 0:
        return {"matches": [], "total_matches": 0}
    
    matches = []
    for _, row in df_recent.iterrows():
        def _f(col):
            return float(row[col]) if col in row and pd.notna(row[col]) else 0.0
        matches.append({
            "date": str(row["date"]),
            "opponent": str(row["opponent"]),
            "competition": str(row["competition"]) if pd.notna(row.get("competition")) else "",
            "is_home": bool(row["is_home"] == 1),
            "goals_scored": int(row["goals_scored"]),
            "goals_conceded": int(row["goals_conceded"]),
            "sb_shots": _f("sb_shots"),
            "sb_shots_on_target": _f("sb_shots_on_target"),
            "sb_corners": _f("sb_corners"),
            "sb_cards": _f("sb_cards"),
            "sb_offsides": _f("sb_offsides"),
            "sb_fouls": _f("sb_fouls"),
            "sb_possession": _f("sb_possession"),
            "sb_passes": _f("sb_passes"),
        })
        
    return {"matches": matches, "total_matches": total_matches}


_ELO_HISTORY_MEMO: dict[str, pd.DataFrame] = {}
_ELO_WINDOW_YEARS = {"selecao": 7, "clube": 3}


def _load_elo_history(scope: str) -> pd.DataFrame:
    """CSV pré-computado (scripts/build_elo_history.py) com Elo mensal por time,
    a partir de home_elo_pre/away_elo_pre já calculados no dataset de treino --
    nunca escaneia o Neon em runtime. Memoizado em processo (arquivo pequeno)."""
    if scope in _ELO_HISTORY_MEMO:
        return _ELO_HISTORY_MEMO[scope]
    path = (ARTIFACT_DIR_CLUBES if scope == "clube" else ARTIFACT_DIR) / "elo_history.csv"
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"[AVISO] elo_history.csv ({scope}): {e}")
        df = pd.DataFrame(columns=["team", "date", "elo"])
    _ELO_HISTORY_MEMO[scope] = df
    return df


def get_team_history(team_name: str, scope: str = "selecao") -> dict[str, Any]:
    """Extrai histórico do time para os gráficos da página de Estatísticas.
    Escopo 'clube': mesmo gap da `matches` que get_recent_matches -- estatísticas
    reais (attack_avg/corners_freq/etc) seguem vazias por ora, mas o Elo histórico
    já é servido (fonte independente, vem do dataset de treino de clubes)."""
    elo_df = _load_elo_history(scope)
    team_elo = elo_df[elo_df["team"] == team_name]
    years = _ELO_WINDOW_YEARS.get(scope, 7)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=365 * years)).strftime("%Y-%m")
    elo_history = [
        {"date": r["date"], "elo": float(r["elo"])}
        for _, r in team_elo[team_elo["date"] >= cutoff].iterrows()
    ]

    if scope == "clube":
        df_team = _load_club_matches_long()
        df_team = df_team[df_team["team"] == team_name].sort_values("date", ascending=True)
        if df_team.empty:
            return {"team": team_name, "elo_history": elo_history, "attack_avg": 0.0,
                    "defense_avg": 0.0, "corners_freq": [], "cards_freq": []}
        return _team_history_from_matches(team_name, df_team, elo_history)
    from app.db.connection import engine
    from sqlalchemy import text as _text
    try:
        # Só as colunas usadas (tendências/atk-def/escanteios/cartões) + parametrizado.
        query = _text("SELECT date, goals_scored, goals_conceded, sb_corners, sb_cards "
                      "FROM matches WHERE team = :team ORDER BY date ASC")
        df_team = pd.read_sql(query, con=engine, params={"team": team_name})
    except Exception as e:
        print(f"[ERRO DB] {e}")
        return {"team": team_name, "elo_history": elo_history, "attack_avg": 0.0, "defense_avg": 0.0, "corners_freq": [], "cards_freq": []}

    if df_team.empty:
        return {"team": team_name, "elo_history": elo_history, "attack_avg": 0.0, "defense_avg": 0.0, "corners_freq": [], "cards_freq": []}

    return _team_history_from_matches(team_name, df_team, elo_history)


def _team_history_from_matches(team_name: str, df_team: pd.DataFrame, elo_history: list) -> dict[str, Any]:
    """Trend/ataque-defesa/frequência de escanteios-cartões a partir de um df já
    ordenado por data ASC com colunas goals_scored/goals_conceded/sb_corners/sb_cards
    -- compartilhado entre seleção (via Neon) e clube (via club_matches_long local)."""
    # Tendência de gols nas últimas 10 partidas (marcados vs sofridos).
    goal_trend = []
    for _, row in df_team.tail(10).iterrows():
        goal_trend.append({
            "label": pd.to_datetime(row["date"]).strftime("%d/%m/%y"),
            "scored": int(row["goals_scored"]),
            "conceded": int(row["goals_conceded"]),
        })

    # 2. Attack vs Defense nas últimas 20 partidas (Ataque = Gols pró, Defesa = Gols sofridos)
    df_recent_20 = df_team.tail(20)
    if len(df_recent_20) > 0:
        attack_avg = df_recent_20["goals_scored"].mean()
        defense_avg = df_recent_20["goals_conceded"].mean()
    else:
        attack_avg = 0.0
        defense_avg = 0.0

    # 3. Frequência de Escanteios (últimas 20 partidas)
    corners_freq = []
    cards_freq = []

    if len(df_recent_20) > 0:
        corners_counts = df_recent_20["sb_corners"].value_counts().sort_index()
        for val, count in corners_counts.items():
            if pd.notna(val):
                corners_freq.append({"label": str(int(val)), "frequency": int(count)})

        cards_counts = df_recent_20["sb_cards"].value_counts().sort_index()
        for val, count in cards_counts.items():
            if pd.notna(val):
                cards_freq.append({"label": str(int(val)), "frequency": int(count)})

    return {
        "team": team_name,
        "elo_history": elo_history,
        "goal_trend": goal_trend,
        "attack_avg": float(attack_avg),
        "defense_avg": float(defense_avg),
        "corners_freq": corners_freq,
        "cards_freq": cards_freq
    }


_GOAL_TIMING_MEMO: dict[str, dict] = {}
_TIMING_BLOCKS = [(1, 15, "1-15"), (16, 30, "16-30"), (31, 45, "31-45"),
                  (46, 60, "46-60"), (61, 75, "61-75"), (76, 90, "76-90+")]


def _timing_block_idx(elapsed: int) -> int:
    """Bloco de 15' pelo minuto REGULAMENTAR (elapsed), acréscimos entram no bloco do
    tempo (45+X -> 31-45, 90+X -> 76-90). Prorrogação (>90) cai no último bloco."""
    if elapsed <= 0:
        return 0
    return min((elapsed - 1) // 15, 5)


def _club_goal_timing(team_name: str) -> dict[str, Any]:
    blocks = [{"label": lbl, "scored": 0, "conceded": 0} for _, _, lbl in _TIMING_BLOCKS]
    empty = {"team": team_name, "n_matches": 0, "total_scored": 0, "total_conceded": 0, "blocks": blocks}
    df = _load_club_goal_timing()
    row = df[df["team"] == team_name]
    if row.empty:
        return empty
    r = row.iloc[0]
    blocks = [{"label": lbl, "scored": int(r[f"scored_{i}"]), "conceded": int(r[f"conceded_{i}"])}
              for i, (_, _, lbl) in enumerate(_TIMING_BLOCKS)]
    return {
        "team": team_name,
        "n_matches": int(r["n_matches"]),
        "total_scored": sum(b["scored"] for b in blocks),
        "total_conceded": sum(b["conceded"] for b in blocks),
        "blocks": blocks,
    }


def get_goal_timing(team_name: str, scope: str = "selecao") -> dict[str, Any]:
    """Distribuição de MINUTAGEM de gols (marcados e sofridos) por blocos de 15',
    agregada do histórico já cacheado (match_detail_cache). Zero chamada à API.
    Escopo 'clube': lê club_goal_timing.parquet (pré-computado localmente por
    scripts/build_club_local_history.py a partir do club_raw_cache.sqlite)."""
    blocks = [{"label": lbl, "scored": 0, "conceded": 0} for _, _, lbl in _TIMING_BLOCKS]
    empty = {"team": team_name, "n_matches": 0, "total_scored": 0, "total_conceded": 0, "blocks": blocks}
    if scope == "clube":
        return _club_goal_timing(team_name)
    if team_name in _GOAL_TIMING_MEMO:
        return _GOAL_TIMING_MEMO[team_name]

    team_id = get_team_ids().get(team_name)
    if not team_id:
        return empty

    from app.db.connection import engine
    from app.services import aggregates
    agg = aggregates.read_goal_timing(engine, team_id, team_name)
    if agg is not None:  # tabela precomputada -> lê bytes, não escaneia o bruto
        agg.pop("_hit", None)
        return agg

    from sqlalchemy import text as _text
    try:
        # Casa a seleção como mandante (…|TIME|…) ou visitante (…|TIME) na chave do cache.
        rows = pd.read_sql(
            _text("SELECT raw FROM match_detail_cache WHERE key LIKE :h OR key LIKE :a"),
            con=engine, params={"h": f"%|{team_name}|%", "a": f"%|{team_name}"},
        )
    except Exception as e:
        print(f"[ERRO DB] goal_timing {team_name}: {e}")
        return empty

    n_matches = 0
    for raw_json in rows["raw"]:
        try:
            d = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            continue
        if not d:
            continue
        status = (((d.get("fixture") or {}).get("status") or {}).get("short"))
        if status not in ("FT", "AET", "PEN"):  # só partidas efetivamente disputadas
            continue
        # Confirma que a seleção participou (por id) e evita falso-positivo do LIKE.
        teams = d.get("teams") or {}
        ids = {((teams.get("home") or {}).get("id")), ((teams.get("away") or {}).get("id"))}
        if team_id not in ids:
            continue
        n_matches += 1
        for e in (d.get("events") or []):
            if (e.get("type") or "").lower() != "goal":
                continue
            detail = e.get("detail") or ""
            if "Missed" in detail:  # pênalti perdido não é gol
                continue
            elapsed = ((e.get("time") or {}).get("elapsed")) or 0
            is_team_event = ((e.get("team") or {}).get("id")) == team_id
            own = "Own" in detail
            scored_by_team = is_team_event != own  # XOR: gol contra inverte o lado
            bi = _timing_block_idx(int(elapsed))
            blocks[bi]["scored" if scored_by_team else "conceded"] += 1

    out = {
        "team": team_name,
        "n_matches": n_matches,
        "total_scored": sum(b["scored"] for b in blocks),
        "total_conceded": sum(b["conceded"] for b in blocks),
        "blocks": blocks,
    }
    if n_matches:
        _GOAL_TIMING_MEMO[team_name] = out
    return out


_REFEREE_TABLE: dict[str, Any] | None = None


def _to_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _build_referee_table() -> dict[str, Any]:
    """Agrega, do match_detail_cache, cartões e faltas por árbitro (uma varredura por
    processo). Zero chamada à API. Retorna {refs:{nome:{...}}, bench:{cards,fouls}}."""
    from app.db.connection import engine
    from sqlalchemy import text as _text
    refs: dict[str, dict[str, float]] = {}
    tot_cards = tot_fouls = 0.0
    n_card_matches = n_foul_matches = 0
    try:
        with engine.connect() as c:
            rows = c.execute(_text("SELECT raw FROM match_detail_cache")).fetchall()
    except Exception as e:
        print(f"[ERRO DB] referee_table: {e}")
        return {"refs": {}, "bench": {"cards": 0.0, "fouls": 0.0}}

    for (raw_json,) in rows:
        try:
            d = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            continue
        if not d:
            continue
        status = (((d.get("fixture") or {}).get("status") or {}).get("short"))
        if status not in ("FT", "AET", "PEN"):
            continue
        ref = ((d.get("fixture") or {}).get("referee")) or ""
        ref = ref.split(",")[0].strip()  # remove sufixo de país, se houver
        stats = d.get("statistics") or []
        y = r = fouls = 0
        has_cards = has_fouls = False
        for st in stats:
            for s2 in (st.get("statistics") or []):
                t, v = s2.get("type"), s2.get("value")
                if t == "Yellow Cards" and v is not None:
                    y += _to_int(v); has_cards = True
                elif t == "Red Cards" and v is not None:
                    r += _to_int(v); has_cards = True
                elif t == "Fouls" and v is not None:
                    fouls += _to_int(v); has_fouls = True
        if has_cards:
            tot_cards += (y + r); n_card_matches += 1
        if has_fouls:
            tot_fouls += fouls; n_foul_matches += 1
        if not ref:
            continue
        e = refs.setdefault(ref, {"n": 0, "n_c": 0, "n_f": 0, "y": 0.0, "r": 0.0, "fouls": 0.0})
        e["n"] += 1
        if has_cards:
            e["n_c"] += 1; e["y"] += y; e["r"] += r
        if has_fouls:
            e["n_f"] += 1; e["fouls"] += fouls

    bench = {
        "cards": round(tot_cards / n_card_matches, 2) if n_card_matches else 0.0,
        "fouls": round(tot_fouls / n_foul_matches, 2) if n_foul_matches else 0.0,
    }
    return {"refs": refs, "bench": bench}


def _referee_table() -> dict[str, Any]:
    global _REFEREE_TABLE
    if _REFEREE_TABLE is None or not _REFEREE_TABLE.get("refs"):
        _REFEREE_TABLE = _build_referee_table()
    return _REFEREE_TABLE


def get_referee_stats(referee_name: str) -> dict[str, Any]:
    """Tendência disciplinar de um árbitro (média de cartões/faltas por jogo) vs a média
    geral. Lê a tabela PRECOMPUTADA `referee_stats_agg` (bytes); só cai na varredura do
    bruto (44 MB) se a precompute ainda não tiver rodado."""
    from app.db.connection import engine
    from app.services import aggregates
    agg = aggregates.read_referee_stats(engine, referee_name)
    if agg is not None:
        agg.pop("_hit", None)
        return agg
    # Fallback (tabela ainda não precomputada): varredura em processo, memoizada.
    tbl = _referee_table()
    bench = tbl["bench"]
    empty = {
        "referee": referee_name, "n_matches": 0, "n_card_matches": 0, "n_foul_matches": 0,
        "avg_yellow": 0.0, "avg_red": 0.0, "avg_cards": 0.0, "avg_fouls": 0.0,
        "bench_cards": bench["cards"], "bench_fouls": bench["fouls"],
    }
    e = tbl["refs"].get(referee_name)
    if not e:  # tenta casar por normalização frouxa (case/acentos)
        key = _loose_team_key(referee_name)
        for name, rec in tbl["refs"].items():
            if _loose_team_key(name) == key:
                e = rec; referee_name = name; break
    if not e:
        return empty
    nc, nf = e["n_c"], e["n_f"]
    return {
        "referee": referee_name, "n_matches": e["n"], "n_card_matches": nc, "n_foul_matches": nf,
        "avg_yellow": round(e["y"] / nc, 2) if nc else 0.0,
        "avg_red": round(e["r"] / nc, 2) if nc else 0.0,
        "avg_cards": round((e["y"] + e["r"]) / nc, 2) if nc else 0.0,
        "avg_fouls": round(e["fouls"] / nf, 2) if nf else 0.0,
        "bench_cards": bench["cards"], "bench_fouls": bench["fouls"],
    }


_PMF_PREVIEW_MEMO: dict[str, dict] = {}


def get_pmf_preview(home: str, away: str, neutral: bool = False,
                    tournament: str = "Copa do Mundo", scope: str = "selecao") -> dict[str, Any]:
    """Prévia REDUZIDA (grátis) da PMF: só a linha principal — distribuição de gols
    totais + Over/Under 2.5 + 1X2. Versão completa (todos os mercados) fica na Análise
    paga. Memoizado por confronto para não recomputar o modelo a cada visita."""
    predictor = _predictor_for(scope)
    h, a = predictor.norm_team(home), predictor.norm_team(away)
    key = f"{scope}|{h}|{a}|{int(bool(neutral))}|{tournament}"
    if key in _PMF_PREVIEW_MEMO:
        return _PMF_PREVIEW_MEMO[key]

    raw = predictor.predict(h, a, neutral=neutral, tournament=tournament)
    gols = raw.get("gols") or {}
    over = raw.get("over_2_5") or {}
    venc = (raw.get("vencedor") or {}).get("probabilidades") or {}
    p_over = float(over.get("prob_sim", 0) or 0) / 100.0
    out = {
        "home": h, "away": a,
        "expected_goals": gols.get("estimativa"),
        "interval": gols.get("intervalo") or [],
        "confidence": gols.get("confianca"),
        "distribution": gols.get("distribuicao") or [],
        "prob_over_2_5": round(100 * p_over, 1),
        "odd_over_2_5": round(1 / p_over, 2) if p_over > 0 else None,
        "odd_under_2_5": round(1 / (1 - p_over), 2) if p_over < 1 else None,
        "prob_home": venc.get(h),
        "prob_draw": venc.get("Empate"),
        "prob_away": venc.get(a),
    }
    _PMF_PREVIEW_MEMO[key] = out
    return out


def get_injuries(team_name: str, scope: str = "selecao") -> dict[str, Any]:
    """Boletim de desfalques (lesões/suspensões) atual da equipe. Consulta a API
    com cache diário no Neon; deduplica por jogador (registro mais recente)."""
    team_id = get_team_ids(scope).get(team_name)
    if not team_id:
        return {"team": team_name, "season": None, "players": []}

    from app.services.fixture_fetch import fetch_injuries
    year = datetime.date.today().year
    resp = fetch_injuries(int(team_id), year)
    if not resp:  # início de ano/temporada vazia: tenta o ano anterior
        resp = fetch_injuries(int(team_id), year - 1)

    latest: dict[int, dict[str, Any]] = {}
    for r in resp or []:
        p = r.get("player") or {}
        f = r.get("fixture") or {}
        pid = p.get("id")
        if pid is None:
            continue
        fdate = (f.get("date") or "")
        cur = latest.get(pid)
        if cur is None or fdate > cur["_date"]:
            latest[pid] = {
                "player_id": pid,
                "name": _fix_mojibake(p.get("name")),
                "reason": p.get("reason"),
                "type": p.get("type"),
                "_date": fdate,
            }
    players = sorted(latest.values(), key=lambda x: x["_date"], reverse=True)
    for pl in players:
        pl.pop("_date", None)
    return {"team": team_name, "season": year, "players": players}


_COMP_BENCH_MEMO: dict[str, dict] = {}
# Buckets de torneio do front -> competições cruas na tabela `matches`.
_COMP_BUCKETS: dict[str, list[str]] = {
    "Copa do Mundo": ["World Cup"],  # tratado como exato (exclui Qualification)
    "Amistoso": ["Friendlies"],
    "Eliminatorias": ["Qualification"],
    "Liga das Nacoes": ["Nations League"],
    "Copa America / Euro / Copa Africana": ["Copa America", "Euro Championship",
                                            "Africa Cup", "Asian Cup", "Gold Cup"],
}


def _club_competition_benchmark(tournament: str) -> dict[str, Any]:
    empty = {"attack_mean": 0.0, "attack_std": 0.0, "defense_mean": 0.0,
             "defense_std": 0.0, "n_teams": 0, "scope": "global", "team_stats": {}}
    df = _load_club_matches_long()
    if df.empty:
        return empty

    df_comp = df[df["competition"] == tournament].copy()
    scope_out = "competition"

    if df_comp.empty or df_comp["team"].nunique() < 4:
        df_comp = df.copy()
        scope_out = "global"
    else:
        df_comp["year"] = pd.to_datetime(df_comp["date"]).dt.year
        max_year = df_comp["year"].max()
        sub = df_comp[df_comp["year"] == max_year]
        if sub["team"].nunique() < 4:
            sub = df_comp[df_comp["year"] >= (max_year - 1)]
        df_comp = sub

    per = df_comp.groupby("team").agg(atk=("goals_scored", "mean"),
                                      dff=("goals_conceded", "mean"),
                                      n=("goals_scored", "size"))
    per = per[per["n"] >= 1]
    if per.empty:
        return empty

    out = {
        "attack_mean": round(float(per["atk"].mean()), 3),
        "attack_std": round(float(per["atk"].std(ddof=0)), 3),
        "defense_mean": round(float(per["dff"].mean()), 3),
        "defense_std": round(float(per["dff"].std(ddof=0)), 3),
        "n_teams": int(len(per)),
        "scope": scope_out,
    }

    team_stats = {}
    from predictor import TEAM_ALIASES
    for team, row in per.iterrows():
        norm_t = TEAM_ALIASES.get(str(team), str(team))
        team_stats[norm_t] = {
            "attack": round(float(row["atk"]), 3),
            "defense": round(float(row["dff"]), 3)
        }
    out["team_stats"] = team_stats
    return out


def get_competition_benchmark(tournament: str, scope: str = "selecao") -> dict[str, Any]:
    """Faixa típica de ataque/defesa (gols pró/contra por jogo) das seleções que disputam
    a competição analisada — usada para desenhar o 'cardume' no gráfico de quadrantes.
    Escopo 'clube': lê club_matches_long.parquet (local, ver build_club_local_history.py)
    e filtra pela competição exata (fx.tournament cru vindo do frontend)."""
    empty0 = {"attack_mean": 0.0, "attack_std": 0.0, "defense_mean": 0.0,
              "defense_std": 0.0, "n_teams": 0, "scope": "global", "team_stats": {}}
    if scope == "clube":
        return _club_competition_benchmark(tournament)
    key = tournament or "_"
    if key in _COMP_BENCH_MEMO:
        return _COMP_BENCH_MEMO[key]

    from app.db.connection import engine
    from app.services import aggregates
    agg = aggregates.read_benchmark(engine, tournament)
    if agg is not None and agg.get("team_stats"):  # tabela precomputada com team_stats
        agg.pop("_hit", None)
        _COMP_BENCH_MEMO[key] = agg
        return agg

    empty = {"attack_mean": 0.0, "attack_std": 0.0, "defense_mean": 0.0,
             "defense_std": 0.0, "n_teams": 0, "scope": "global", "team_stats": {}}
    try:
        df = pd.read_sql("SELECT team, competition, goals_scored, goals_conceded FROM matches", con=engine)
    except Exception as e:
        print(f"[ERRO DB] competition_benchmark: {e}")
        return empty
    if df.empty:
        return empty

    patterns = _COMP_BUCKETS.get(tournament)
    scope_val = "global"
    if patterns:
        if tournament == "Copa do Mundo":
            mask = df["competition"] == "World Cup"
        elif tournament == "Eliminatorias":
            mask = df["competition"].str.contains("Qualification", na=False)
        else:
            mask = df["competition"].apply(lambda c: any(p in str(c) for p in patterns))
        teams_in = set(df.loc[mask, "team"].unique())
        if len(teams_in) >= 4:
            scope_val = "competition"
        else:
            teams_in = set(df["team"].unique())
    else:
        teams_in = set(df["team"].unique())

    sub = df[df["team"].isin(teams_in)]
    per = sub.groupby("team").agg(atk=("goals_scored", "mean"),
                                  dff=("goals_conceded", "mean"),
                                  n=("goals_scored", "size"))
    per = per[per["n"] >= 5]
    if per.empty:
        return empty
    out = {
        "attack_mean": round(float(per["atk"].mean()), 3),
        "attack_std": round(float(per["atk"].std(ddof=0)), 3),
        "defense_mean": round(float(per["dff"].mean()), 3),
        "defense_std": round(float(per["dff"].std(ddof=0)), 3),
        "n_teams": int(len(per)),
        "scope": scope_val,
    }

    team_stats = {}
    from predictor import TEAM_ALIASES
    for team, row in per.iterrows():
        norm_t = TEAM_ALIASES.get(str(team), str(team))
        team_stats[norm_t] = {
            "attack": round(float(row["atk"]), 3),
            "defense": round(float(row["dff"]), 3)
        }
    out["team_stats"] = team_stats

    _COMP_BENCH_MEMO[key] = out
    return out


def get_team_anomalies(team_name: str, scope: str = "selecao") -> list[dict[str, Any]]:
    """Detecta anomalias estatísticas recentes baseadas no Z-Score da equipe.
    Escopo 'clube': feature pensada p/ o ciclo de seleção (competitivo vs amistoso
    em torno de Copas) -- não se aplica a calendário de liga de clube; vazio."""
    if scope == "clube":
        return []
    # Obter o torneio padrão para determinar a classe competitivo/amistoso
    return detect_anomalies(team_name, target_competition="World Cup")


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_URL") or os.getenv("FRONTEND_ORIGIN") or "http://localhost:3000"
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "http://localhost:3000" not in origins:
        origins.append("http://localhost:3000")
    if "https://www.apostainfo.com.br" not in origins:
        origins.append("https://www.apostainfo.com.br")
    if "https://apostainfo.com.br" not in origins:
        origins.append("https://apostainfo.com.br")
    return origins
