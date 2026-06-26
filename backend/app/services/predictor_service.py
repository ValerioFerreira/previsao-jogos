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


def _norm(name: str) -> str:
    """Canoniza nome de seleção (alias) — leve, para listas e lookups."""
    return TEAM_ALIASES.get(name, name) if name else name


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


@_cache_nonempty
def get_team_ids() -> dict[str, int]:
    """Mapa nome_da_seleção -> team_id (para montar URL do logo).
    Inclui as chaves canonizadas (alias)."""
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


def get_match_detail(home: str, away: str, date: str) -> dict[str, Any]:
    """Wrapper defensivo: NUNCA propaga exceção (um 500 não leva header CORS e o
    browser mascara como erro de CORS). Em qualquer falha, devolve found=False."""
    try:
        return _match_detail_impl(home, away, date)
    except Exception as e:
        print(f"[ERRO match_detail] {home} x {away} {date}: {type(e).__name__}: {e}")
        return {"found": False}


def _match_detail_impl(home: str, away: str, date: str) -> dict[str, Any]:
    """Detalhe completo de uma partida JÁ DISPUTADA: cache(Neon) -> .gz local -> API.
    Robusto a dados ausentes (jogos antigos/ligas menores).
    """
    import gzip
    from app.services.fixture_fetch import cache_get, get_or_fetch_detail
    d10 = date[:10]
    key = f"{d10}|{_norm(home)}|{_norm(away)}"

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
        d = get_or_fetch_detail(_norm(home), _norm(away), d10, key, get_team_ids())
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


def get_upcoming_fixtures() -> list[dict[str, Any]]:
    """Partidas futuras a partir do registry do coletor de odds (sem cota nova).
    Já traz tournament/neutral mapeados para o nosso sistema."""
    reg = _load_registry()
    if not reg:
        return []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out = []
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
        })
    out.sort(key=lambda x: x["date"] or "")
    return out


@lru_cache(maxsize=1)
def get_predictor() -> Predictor:
    return Predictor(art_dir=str(ARTIFACT_DIR))


def clean_values(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {key: value for key, value in values.items() if value is not None}


def predict_match(payload: Any) -> dict[str, Any]:
    predictor = get_predictor()
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


def get_recent_matches(team_name: str) -> dict[str, Any]:
    """Consulta PostgreSQL e extrai as últimas 5 partidas reais da equipe."""
    from app.db.connection import engine
    try:
        query = f"SELECT * FROM matches WHERE team = '{team_name}' ORDER BY date DESC LIMIT 5"
        df_recent = pd.read_sql(query, con=engine)
        
        # Get total matches count efficiently
        total_query = f"SELECT COUNT(*) as count FROM matches WHERE team = '{team_name}'"
        total_df = pd.read_sql(total_query, con=engine)
        total_matches = int(total_df.iloc[0]["count"]) if not total_df.empty else 0
    except Exception as e:
        print(f"[ERRO DB] {e}")
        return {"matches": [], "total_matches": 0}
        
    if total_matches == 0:
        return {"matches": [], "total_matches": 0}
    
    matches = []
    for _, row in df_recent.iterrows():
        matches.append({
            "date": str(row["date"]),
            "opponent": str(row["opponent"]),
            "competition": str(row["competition"]) if pd.notna(row.get("competition")) else "",
            "is_home": bool(row["is_home"] == 1),
            "goals_scored": int(row["goals_scored"]),
            "goals_conceded": int(row["goals_conceded"]),
            "sb_shots": float(row["sb_shots"]) if pd.notna(row["sb_shots"]) else 0.0,
            "sb_shots_on_target": float(row["sb_shots_on_target"]) if pd.notna(row["sb_shots_on_target"]) else 0.0,
            "sb_corners": float(row["sb_corners"]) if pd.notna(row["sb_corners"]) else 0.0,
            "sb_cards": float(row["sb_cards"]) if pd.notna(row["sb_cards"]) else 0.0
        })
        
    return {"matches": matches, "total_matches": total_matches}


def get_team_history(team_name: str) -> dict[str, Any]:
    """Extrai histórico do time para os gráficos da página de Estatísticas."""
    from app.db.connection import engine
    try:
        # Pega as últimas 20 partidas para calcular tendências de ataque/defesa
        query = f"SELECT * FROM matches WHERE team = '{team_name}' ORDER BY date ASC"
        df_team = pd.read_sql(query, con=engine)
    except Exception as e:
        print(f"[ERRO DB] {e}")
        return {"team": team_name, "elo_history": [], "attack_avg": 0.0, "defense_avg": 0.0, "corners_freq": [], "cards_freq": []}

    if df_team.empty:
        return {"team": team_name, "elo_history": [], "attack_avg": 0.0, "defense_avg": 0.0, "corners_freq": [], "cards_freq": []}
    
    # 1. Histórico de Elo Rating (pegando um ponto por ano para simplificar ou todos)
    elo_history = []
    # Pegamos o Elo pre_match
    # Como pode haver muitos jogos, agrupamos por ano para plotar a evolução temporal anual
    df_team['year'] = pd.to_datetime(df_team['date']).dt.year
    # matches.parquet pode não ter Elo pré-jogo; só monta a série se a coluna existir.
    elo_col = next((c for c in ("pre_match_elo", "elo_pre", "elo_rating") if c in df_team.columns), None)
    if elo_col:
        elo_yearly = df_team.groupby('year')[elo_col].last().reset_index()
        for _, row in elo_yearly.iterrows():
            if pd.notna(row[elo_col]):
                elo_history.append({"date": str(row['year']), "elo": float(row[elo_col])})
    
    # Se nao houver elo pre-match disponivel
    if not elo_history:
        predictor = get_predictor()
        current_elo = predictor.team_defaults(team_name).get("elo_rating", 1500)
        elo_history.append({"date": "Current", "elo": float(current_elo)})

    # 1b. Tendência de gols nas últimas 10 partidas (marcados vs sofridos) — dado real,
    # substitui a antiga série de Elo (matches.parquet não tem Elo histórico).
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


def get_team_anomalies(team_name: str) -> list[dict[str, Any]]:
    """Detecta anomalias estatísticas recentes baseadas no Z-Score da equipe."""
    # Obter o torneio padrão para determinar a classe competitivo/amistoso
    return detect_anomalies(team_name, target_competition="World Cup")


def allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_URL") or os.getenv("FRONTEND_ORIGIN") or "http://localhost:3000"
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "http://localhost:3000" not in origins:
        origins.append("http://localhost:3000")
    return origins
