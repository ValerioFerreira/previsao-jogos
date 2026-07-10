"""
app/services/aggregates.py
==========================
PRECOMPUTE de agregados pequenos a partir do detalhe bruto dos jogos, para o site NÃO
precisar varrer os ~44 MB de `match_detail_cache` em runtime. Roda no job diário (máquina
local, lendo o espelho local via raw_cache) e grava tabelas PEQUENAS no Neon:

- `referee_stats_agg`  (~1.700 linhas, ~120 KB): cartões/faltas médios por árbitro.
- `goal_timing_agg`    (~340 linhas): minutagem de gols por seleção (blocos de 15').
- `competition_bench_agg` (~5 linhas): faixa típica de ataque/defesa por competição.
- `agg_kv`             (metadados: benchmark de árbitro, timestamp).

Os endpoints leem 1 linha dessas tabelas (bytes) em vez de escanear o bruto (MB).
"""
from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text


def _write_df(engine, df: "pd.DataFrame", table: str) -> None:
    """Grava a tabela pequena em LOTE (multi-row INSERT) — evita centenas de round-trips
    linha-a-linha na conexão Neon (que travava o precompute)."""
    df.to_sql(table, engine, if_exists="replace", index=False, method="multi", chunksize=400)

_FINISHED = {"FT", "AET", "PEN"}
_TIMING_LABELS = ["1-15", "16-30", "31-45", "46-60", "61-75", "76-90+"]


def _block_idx(elapsed: int) -> int:
    if elapsed <= 0:
        return 0
    return min((elapsed - 1) // 15, 5)


def _to_int(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def ensure_tables(engine) -> None:
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS referee_stats_agg ("
                       "referee TEXT PRIMARY KEY, n INT, n_c INT, n_f INT, "
                       "avg_yellow REAL, avg_red REAL, avg_cards REAL, avg_fouls REAL)"))
        c.execute(text("CREATE TABLE IF NOT EXISTS goal_timing_agg ("
                       "team_id BIGINT PRIMARY KEY, n_matches INT, total_scored INT, "
                       "total_conceded INT, blocks TEXT)"))
        c.execute(text("CREATE TABLE IF NOT EXISTS competition_bench_agg ("
                       "tournament TEXT PRIMARY KEY, attack_mean REAL, attack_std REAL, "
                       "defense_mean REAL, defense_std REAL, n_teams INT, scope TEXT)"))
        c.execute(text("CREATE TABLE IF NOT EXISTS agg_kv (k TEXT PRIMARY KEY, v TEXT)"))


# --------------------------------------------------------------- PRECOMPUTE (job local)
def precompute_from_raw(engine, raw_iter) -> dict[str, int]:
    """Uma única passada sobre o bruto (via raw_cache local) -> árbitro + minutagem.
    Grava as tabelas pequenas no Neon. Retorna contagens."""
    refs: dict[str, dict[str, float]] = {}
    tot_cards = tot_fouls = 0.0
    n_card_m = n_foul_m = 0
    timing: dict[int, dict[str, Any]] = {}

    def gt(tid: int) -> dict[str, Any]:
        return timing.setdefault(tid, {"n": 0, "scored": [0] * 6, "conceded": [0] * 6})

    for d in raw_iter:
        if not d:
            continue
        fx = d.get("fixture") or {}
        if ((fx.get("status") or {}).get("short")) not in _FINISHED:
            continue
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id")
        aid = (teams.get("away") or {}).get("id")

        # --- árbitro (cartões/faltas somando os dois times) ---
        ref = ((fx.get("referee")) or "").split(",")[0].strip()
        y = r = fouls = 0
        has_cards = has_fouls = False
        for st in (d.get("statistics") or []):
            for s2 in (st.get("statistics") or []):
                t, v = s2.get("type"), s2.get("value")
                if t == "Yellow Cards" and v is not None:
                    y += _to_int(v); has_cards = True
                elif t == "Red Cards" and v is not None:
                    r += _to_int(v); has_cards = True
                elif t == "Fouls" and v is not None:
                    fouls += _to_int(v); has_fouls = True
        if has_cards:
            tot_cards += (y + r); n_card_m += 1
        if has_fouls:
            tot_fouls += fouls; n_foul_m += 1
        if ref:
            e = refs.setdefault(ref, {"n": 0, "n_c": 0, "n_f": 0, "y": 0.0, "r": 0.0, "fouls": 0.0})
            e["n"] += 1
            if has_cards:
                e["n_c"] += 1; e["y"] += y; e["r"] += r
            if has_fouls:
                e["n_f"] += 1; e["fouls"] += fouls

        # --- minutagem de gols (para os dois times do jogo) ---
        if hid and aid:
            gt(hid)["n"] += 1
            gt(aid)["n"] += 1
            for ev in (d.get("events") or []):
                if (ev.get("type") or "").lower() != "goal":
                    continue
                detail = ev.get("detail") or ""
                if "Missed" in detail:
                    continue
                et = (ev.get("team") or {}).get("id")
                if et not in (hid, aid):
                    continue
                own = "Own" in detail
                scorer = et if not own else (aid if et == hid else hid)
                conceder = aid if scorer == hid else hid
                bi = _block_idx(_to_int((ev.get("time") or {}).get("elapsed")))
                gt(scorer)["scored"][bi] += 1
                gt(conceder)["conceded"][bi] += 1

    bench_cards = round(tot_cards / n_card_m, 2) if n_card_m else 0.0
    bench_fouls = round(tot_fouls / n_foul_m, 2) if n_foul_m else 0.0

    ref_rows = []
    for name, e in refs.items():
        nc, nf = e["n_c"], e["n_f"]
        ref_rows.append({"referee": name, "n": e["n"], "n_c": nc, "n_f": nf,
                         "avg_yellow": round(e["y"] / nc, 2) if nc else 0.0,
                         "avg_red": round(e["r"] / nc, 2) if nc else 0.0,
                         "avg_cards": round((e["y"] + e["r"]) / nc, 2) if nc else 0.0,
                         "avg_fouls": round(e["fouls"] / nf, 2) if nf else 0.0})
    gt_rows = []
    for tid, g in timing.items():
        blocks = [{"label": _TIMING_LABELS[i], "scored": g["scored"][i], "conceded": g["conceded"][i]} for i in range(6)]
        gt_rows.append({"team_id": int(tid), "n_matches": g["n"], "total_scored": sum(g["scored"]),
                        "total_conceded": sum(g["conceded"]), "blocks": json.dumps(blocks)})

    _write_df(engine, pd.DataFrame(ref_rows or [{"referee": None, "n": 0, "n_c": 0, "n_f": 0,
              "avg_yellow": 0.0, "avg_red": 0.0, "avg_cards": 0.0, "avg_fouls": 0.0}]), "referee_stats_agg")
    _write_df(engine, pd.DataFrame(gt_rows or [{"team_id": 0, "n_matches": 0, "total_scored": 0,
              "total_conceded": 0, "blocks": "[]"}]), "goal_timing_agg")
    _write_df(engine, pd.DataFrame([{"k": "bench_cards", "v": str(bench_cards)},
                                    {"k": "bench_fouls", "v": str(bench_fouls)}]), "agg_kv")
    return {"referees": len(refs), "teams": len(timing)}


def precompute_benchmarks(engine, buckets: dict[str, list[str]]) -> int:
    """Faixa típica de ataque/defesa por competição, a partir da tabela `matches`
    (leitura pequena). Grava competition_bench_agg. `buckets` = mapa torneio->patterns."""
    import pandas as pd
    ensure_tables(engine)
    try:
        df = pd.read_sql("SELECT team, competition, goals_scored, goals_conceded FROM matches", con=engine)
    except Exception as e:
        print(f"[ERRO DB] precompute_benchmarks: {e}")
        return 0
    if df.empty:
        return 0
    out_rows = []
    for tournament, patterns in buckets.items():
        if tournament == "Copa do Mundo":
            mask = df["competition"] == "World Cup"
        elif tournament == "Eliminatorias":
            mask = df["competition"].str.contains("Qualification", na=False)
        else:
            mask = df["competition"].apply(lambda x: any(p in str(x) for p in patterns))
        teams_in = set(df.loc[mask, "team"].unique())
        scope = "competition"
        if len(teams_in) < 4:
            teams_in = set(df["team"].unique()); scope = "global"
        sub = df[df["team"].isin(teams_in)]
        per = sub.groupby("team").agg(atk=("goals_scored", "mean"), dff=("goals_conceded", "mean"),
                                      n=("goals_scored", "size"))
        per = per[per["n"] >= 5]
        if per.empty:
            continue
        out_rows.append({"tournament": tournament, "attack_mean": round(float(per["atk"].mean()), 3),
                         "attack_std": round(float(per["atk"].std(ddof=0)), 3),
                         "defense_mean": round(float(per["dff"].mean()), 3),
                         "defense_std": round(float(per["dff"].std(ddof=0)), 3),
                         "n_teams": int(len(per)), "scope": scope})
    if not out_rows:
        return 0
    _write_df(engine, pd.DataFrame(out_rows), "competition_bench_agg")
    return len(out_rows)


# ------------------------------------------------------------------- LEITURA (runtime)
def _bench(engine) -> tuple[float, float]:
    try:
        with engine.connect() as c:
            rows = dict(c.execute(text("SELECT k, v FROM agg_kv WHERE k IN ('bench_cards','bench_fouls')")).fetchall())
        return float(rows.get("bench_cards", 0) or 0), float(rows.get("bench_fouls", 0) or 0)
    except Exception:
        return 0.0, 0.0


def read_referee_stats(engine, referee_name: str) -> Optional[dict]:
    """Lê 1 linha de referee_stats_agg. None se a tabela ainda não foi precomputada."""
    try:
        with engine.connect() as c:
            if c.execute(text("SELECT 1 FROM referee_stats_agg LIMIT 1")).first() is None:
                return None
            row = c.execute(text("SELECT referee,n,n_c,n_f,avg_yellow,avg_red,avg_cards,avg_fouls "
                                 "FROM referee_stats_agg WHERE referee=:r"), {"r": referee_name}).first()
    except Exception:
        return None
    bench_cards, bench_fouls = _bench(engine)
    if row is None:
        return {"referee": referee_name, "n_matches": 0, "n_card_matches": 0, "n_foul_matches": 0,
                "avg_yellow": 0.0, "avg_red": 0.0, "avg_cards": 0.0, "avg_fouls": 0.0,
                "bench_cards": bench_cards, "bench_fouls": bench_fouls, "_hit": True}
    return {"referee": row[0], "n_matches": row[1], "n_card_matches": row[2], "n_foul_matches": row[3],
            "avg_yellow": row[4], "avg_red": row[5], "avg_cards": row[6], "avg_fouls": row[7],
            "bench_cards": bench_cards, "bench_fouls": bench_fouls, "_hit": True}


def read_goal_timing(engine, team_id: int, team_name: str) -> Optional[dict]:
    try:
        with engine.connect() as c:
            if c.execute(text("SELECT 1 FROM goal_timing_agg LIMIT 1")).first() is None:
                return None
            row = c.execute(text("SELECT n_matches,total_scored,total_conceded,blocks "
                                 "FROM goal_timing_agg WHERE team_id=:t"), {"t": int(team_id)}).first()
    except Exception:
        return None
    if row is None:
        blocks = [{"label": l, "scored": 0, "conceded": 0} for l in _TIMING_LABELS]
        return {"team": team_name, "n_matches": 0, "total_scored": 0, "total_conceded": 0, "blocks": blocks, "_hit": True}
    return {"team": team_name, "n_matches": row[0], "total_scored": row[1], "total_conceded": row[2],
            "blocks": json.loads(row[3]), "_hit": True}


def read_benchmark(engine, tournament: str) -> Optional[dict]:
    try:
        with engine.connect() as c:
            if c.execute(text("SELECT 1 FROM competition_bench_agg LIMIT 1")).first() is None:
                return None
            row = c.execute(text("SELECT attack_mean,attack_std,defense_mean,defense_std,n_teams,scope "
                                 "FROM competition_bench_agg WHERE tournament=:t"), {"t": tournament}).first()
    except Exception:
        return None
    if row is None:
        return None  # sem linha p/ esse torneio -> deixa o caller usar defaults
    return {"attack_mean": row[0], "attack_std": row[1], "defense_mean": row[2],
            "defense_std": row[3], "n_teams": row[4], "scope": row[5], "_hit": True}
