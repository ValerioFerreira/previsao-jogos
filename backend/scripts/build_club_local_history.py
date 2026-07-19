#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_club_local_history.py
=====================================
Fecha o gap documentado em `app/services/predictor_service.py` (get_recent_matches,
get_team_history, get_goal_timing, get_competition_benchmark): essas funções
degradam vazio para scope="clube" porque a tabela `matches`/`match_detail_cache_agg`
do Neon só cobre seleção. O dado BRUTO de clube já existe 100% local
(club_features_enriched.parquet tem o box-score do jogo atual em home/away_cur_sb_*;
club_raw_cache.sqlite tem os eventos de gol por minuto) -- só nunca foi agregado
num formato servível.

Gera dois artefatos locais (comprometidos no git junto com o resto de
model_artifacts_clubes/, mesmo padrão do elo_history.csv):

  model_artifacts_clubes/club_matches_long.parquet
      Uma linha por (time, partida) -- equivalente ao que a tabela `matches` do
      Neon é para seleção. Usado por get_recent_matches/get_team_history/
      get_competition_benchmark.

  model_artifacts_clubes/club_goal_timing.parquet
      Uma linha por time, com contagem de gols marcados/sofridos por bloco de 15'
      -- equivalente ao que get_goal_timing calcula on-the-fly do match_detail_cache
      de seleção, mas pré-computado (o scan de club_raw_cache.sqlite, 5GB+, não pode
      rodar em runtime/request).

Nomes de time usam a MESMA desambiguação de build_clubs_production_artifacts.py
(disambiguate_collisions) -- reaproveitada daqui, não reimplementada, para não
divergir do que o artefato treinado (team_ids/meta.json) já usa.

Uso:
  python scripts/build_club_local_history.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from scripts.build_clubs_production_artifacts import disambiguate_collisions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
RAW_CACHE = ROOT / "data" / "club_raw_cache.sqlite"
OUT_DIR = ROOT / "model_artifacts_clubes"

_MOJIBAKE_RE = re.compile("[ÃÂ]|â€")


def _fix_mojibake(s):
    if not isinstance(s, str) or not _MOJIBAKE_RE.search(s):
        return s
    try:
        r = s.encode("latin-1").decode("utf-8")
        return r if "�" not in r else s
    except UnicodeError:
        return s


_TIMING_BLOCKS = [(1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 999)]


def _timing_block_idx(elapsed: int) -> int:
    if elapsed <= 0:
        return 0
    return min((elapsed - 1) // 15, 5)


def build_matches_long(df: pd.DataFrame) -> pd.DataFrame:
    """Melt home/away -> uma linha por time, colunas no mesmo shape da tabela
    `matches` (seleção) para que predictor_service reuse a mesma lógica de
    trend/attack-defense/corners-freq/cards-freq/recent-matches."""
    df = df.copy()
    df["tournament"] = df["tournament"].map(_fix_mojibake)

    def side(prefix_self: str, prefix_opp: str, is_home: bool) -> pd.DataFrame:
        out = pd.DataFrame({
            "team": df[f"{prefix_self}_team"],
            "opponent": df[f"{prefix_opp}_team"],
            "date": df["date"],
            "competition": df["tournament"],
            "is_home": is_home,
            "goals_scored": df[f"{prefix_self}_score"],
            "goals_conceded": df[f"{prefix_opp}_score"],
            "sb_shots": df[f"{prefix_self}_cur_sb_shots"],
            "sb_shots_on_target": df[f"{prefix_self}_cur_sb_shots_on_target"],
            "sb_corners": df[f"{prefix_self}_cur_sb_corners"],
            "sb_cards": df[f"{prefix_self}_cur_sb_cards"],
            "sb_offsides": df[f"{prefix_self}_cur_sb_offsides"],
            "sb_fouls": df[f"{prefix_self}_cur_sb_fouls"],
            "sb_possession": df[f"{prefix_self}_cur_sb_possession"],
            "sb_passes": df[f"{prefix_self}_cur_sb_passes"],
        })
        return out

    long = pd.concat([
        side("home", "away", True),
        side("away", "home", False),
    ], ignore_index=True)
    long = long.sort_values("date").reset_index(drop=True)
    return long


def _fixture_team_map(df: pd.DataFrame) -> dict[int, tuple[int, int, str, str]]:
    """fixture_id -> (home_team_id, away_team_id, home_team_canonico, away_team_canonico)."""
    out = {}
    for r in df.itertuples(index=False):
        out[int(r.fixture_id)] = (
            int(r.home_team_id) if pd.notna(r.home_team_id) else None,
            int(r.away_team_id) if pd.notna(r.away_team_id) else None,
            r.home_team, r.away_team,
        )
    return out


def build_goal_timing(fixture_map: dict[int, tuple]) -> pd.DataFrame:
    """Varre club_raw_cache.sqlite (1x, local) e agrega gols por bloco de 15' por
    time -- mesma lógica de app/services/predictor_service.py::get_goal_timing."""
    con = sqlite3.connect(str(RAW_CACHE))
    con.row_factory = None
    cur = con.execute("SELECT fixture_id, raw FROM raw")

    acc: dict[str, dict] = {}

    def _team_acc(name: str) -> dict:
        e = acc.get(name)
        if e is None:
            e = {"n_matches": 0, "scored": [0] * 6, "conceded": [0] * 6}
            acc[name] = e
        return e

    n_rows = 0
    seen_fixtures = set()
    for fixture_id, raw_json in cur:
        n_rows += 1
        if fixture_id in seen_fixtures:
            continue
        info = fixture_map.get(int(fixture_id)) if fixture_id is not None else None
        if info is None:
            continue
        seen_fixtures.add(fixture_id)
        home_id, away_id, home_name, away_name = info
        try:
            d = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        except Exception:
            continue
        if not d:
            continue
        status = (((d.get("fixture") or {}).get("status") or {}).get("short"))
        if status not in ("FT", "AET", "PEN"):
            continue

        h_acc = _team_acc(home_name)
        a_acc = _team_acc(away_name)
        h_acc["n_matches"] += 1
        a_acc["n_matches"] += 1

        for e in (d.get("events") or []):
            if (e.get("type") or "").lower() != "goal":
                continue
            detail = e.get("detail") or ""
            if "Missed" in detail:
                continue
            elapsed = ((e.get("time") or {}).get("elapsed")) or 0
            bi = _timing_block_idx(int(elapsed))
            event_team_id = (e.get("team") or {}).get("id")
            own = "Own" in detail
            is_home_event = event_team_id == home_id
            scored_by_home = is_home_event != own
            if scored_by_home:
                h_acc["scored"][bi] += 1
                a_acc["conceded"][bi] += 1
            else:
                a_acc["scored"][bi] += 1
                h_acc["conceded"][bi] += 1

    con.close()
    print(f"   linhas escaneadas: {n_rows}, fixtures com evento processado: {len(seen_fixtures)}")

    rows = []
    for team, e in acc.items():
        rows.append({
            "team": team,
            "n_matches": e["n_matches"],
            **{f"scored_{i}": e["scored"][i] for i in range(6)},
            **{f"conceded_{i}": e["conceded"][i] for i in range(6)},
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print(" BUILD: histórico local servível de clube (matches long + goal timing)")
    print("=" * 80)

    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Base: {len(df)} jogos ({df['date'].min().date()} -> {df['date'].max().date()})")

    _, df = disambiguate_collisions(df)

    print(">> Montando club_matches_long...")
    long = build_matches_long(df)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    long_path = OUT_DIR / "club_matches_long.parquet"
    long.to_parquet(long_path, index=False)
    print(f"   {len(long)} linhas ({len(long) // 2} jogos x 2 times) -> {long_path} "
          f"({long_path.stat().st_size / 1e6:.1f} MB)")

    print(">> Montando club_goal_timing (varredura de club_raw_cache.sqlite)...")
    fixture_map = _fixture_team_map(df)
    timing = build_goal_timing(fixture_map)
    timing_path = OUT_DIR / "club_goal_timing.parquet"
    timing.to_parquet(timing_path, index=False)
    print(f"   {len(timing)} times -> {timing_path} ({timing_path.stat().st_size / 1e6:.1f} MB)")

    print("\nOK.")


if __name__ == "__main__":
    main()
