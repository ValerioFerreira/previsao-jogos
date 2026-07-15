#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_clubs_dataset.py
==============================
Constrói o dataset de treino de CLUBES (pesquisa branch `clubs`) a partir do espelho
local `data/club_raw_cache.sqlite` (criado por mirror_club_cache.py — zero Neon).

Duas etapas:
  1. PARSE   → data/built/club_matches.parquet   (longo: 1 linha por time x jogo, schema
               compatível com matches.parquet de seleções, p/ reusar compute_sb_features)
             → data/built/club_fixtures.parquet  (largo: 1 linha por jogo, com HT/xG/árbitro/venue)
  2. FEATURES→ data/built/club_features_enriched.parquet — análogo ao features_enriched de
               seleções, MESMOS nomes de colunas (Linha A roda a arquitetura atual sem mudanças).

Decisões (documentadas em docs/PESQUISA_CLUBES.md):
  - Times identificados por "Nome#id" (evita colisão River Plate ARG x URU etc.).
  - Elo de clubes: K por tipo de competição (liga 20 / copa 24 / continental 28), multiplicador
    de margem igual ao de seleções, HOME_ADV=65, time novo entra com 1450 (chega por
    promoção/qualificação, em média mais fraco que a média da base).
  - neutral=1 só em finais únicas de competição continental (aproximação documentada).
  - Sem filtro de corte: coluna `matches_played_before` permite ao treino descartar burn-in.
  - xG (expected_goals) extraído — clubes têm cobertura ampla, diferente de seleções.

Uso:
    python scripts/build_clubs_dataset.py [--stage parse|features|all]
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_final_dataset import (  # reuso deliberado da lógica de seleções (Linha A)
    build_gamelog, compute_form_features, compute_h2h, compute_sb_features,
    WINDOWS, HOME_ADV_ELO,
)

MIRROR = ROOT / "data" / "club_raw_cache.sqlite"
BUILT = ROOT / "data" / "built"
MATCHES_OUT = BUILT / "club_matches.parquet"
FIXTURES_OUT = BUILT / "club_fixtures.parquet"
FEATURES_OUT = BUILT / "club_features_enriched.parquet"

ELO_START = 1500.0
ELO_START_NEW = 1450.0  # time entra mid-history (promovido/classificado) — abaixo da média

CONTINENTAL = {2, 3, 848, 13, 11}
DOMESTIC_CUP = {73}
LEAGUE_NAMES = {
    71: "Brasileirao Serie A", 72: "Brasileirao Serie B", 73: "Copa do Brasil",
    39: "Premier League", 140: "La Liga", 135: "Serie A Italia", 78: "Bundesliga",
    61: "Ligue 1", 2: "Champions League", 3: "Europa League", 848: "Conference League",
    13: "Copa Libertadores", 11: "Copa Sul-Americana",
}

STAT_MAP = {
    "Total Shots":     "sb_shots",
    "Shots on Goal":   "sb_shots_on_target",
    "Corner Kicks":    "sb_corners",
    "Offsides":        "sb_offsides",
    "Yellow Cards":    "sb_yellow",
    "Red Cards":       "sb_red",
    "Fouls":           "sb_fouls",
    "Ball Possession": "sb_possession",
    "Total passes":    "sb_passes",
    "expected_goals":  "sb_xg",
}
FINISHED = {"FT", "AET", "PEN"}


def _norm_value(v):
    if v is None:
        return None
    if isinstance(v, str) and v.endswith("%"):
        try:
            return float(v[:-1])
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def team_key(t: dict) -> str:
    return f"{(t.get('name') or '').strip()}#{t.get('id')}"


# ─── Etapa 1: PARSE ──────────────────────────────────────────────────────────
def stage_parse():
    conn = sqlite3.connect(f"file:{MIRROR}?mode=ro", uri=True, timeout=60)
    n_total = conn.execute("SELECT count(*) FROM raw").fetchone()[0]
    print(f"[parse] {n_total} jogos no espelho local")

    fixture_rows, team_rows = [], []
    cur = conn.execute("SELECT league_id, season, raw FROM raw")
    i = 0
    for league_id, season, raw in cur:
        i += 1
        if i % 5000 == 0:
            print(f"  {i}/{n_total}...", flush=True)
        d = json.loads(raw)
        fx = d.get("fixture") or {}
        status = ((fx.get("status") or {}).get("short")) or ""
        if status not in FINISHED:
            continue
        lg = d.get("league") or {}
        teams = d.get("teams") or {}
        goals = d.get("goals") or {}
        score = d.get("score") or {}
        ht = score.get("halftime") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        hk, ak = team_key(home), team_key(away)
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None or not home.get("id") or not away.get("id"):
            continue
        venue = fx.get("venue") or {}
        round_str = lg.get("round") or ""

        # estatísticas por lado
        stats_by_key = {}
        for entry in d.get("statistics") or []:
            tk = team_key(entry.get("team") or {})
            stats = {s.get("type"): _norm_value(s.get("value"))
                     for s in entry.get("statistics") or [] if s.get("type")}
            stats_by_key[tk] = stats

        frow = {
            "fixture_id": fx.get("id"), "date": (fx.get("date") or "")[:10],
            "timestamp": fx.get("timestamp"),
            "league_id": int(league_id), "season": int(season),
            "tournament": LEAGUE_NAMES.get(int(league_id), lg.get("name") or ""),
            "country": lg.get("country") or "", "round": round_str,
            "home_team": hk, "away_team": ak,
            "home_team_id": home.get("id"), "away_team_id": away.get("id"),
            "home_score": int(hg), "away_score": int(ag),
            "ht_home": ht.get("home"), "ht_away": ht.get("away"),
            "status": status,
            "referee": (fx.get("referee") or "").strip() or None,
            "venue_name": (venue.get("name") or "").strip() or None,
            "venue_city": (venue.get("city") or "").strip() or None,
        }

        has_stats = len(stats_by_key) >= 2
        for side, tk_side, opp_key, gf, ga in [("home", hk, ak, int(hg), int(ag)),
                                               ("away", ak, hk, int(ag), int(hg))]:
            st = stats_by_key.get(tk_side, {})
            trow = {
                "date": frow["date"], "team": tk_side, "opponent": opp_key,
                "is_home": int(side == "home"),
                "competition": frow["tournament"], "league_id": frow["league_id"],
                "season": frow["season"],
                "goals_scored": gf, "goals_conceded": ga,
            }
            for api_type, col in STAT_MAP.items():
                trow[col] = st.get(api_type)
            y, r = trow.get("sb_yellow"), trow.get("sb_red")
            if y is None and r is None:
                trow["sb_cards"] = None
            else:
                trow["sb_yellow"], trow["sb_red"] = float(y or 0.0), float(r or 0.0)
                trow["sb_cards"] = trow["sb_yellow"] + trow["sb_red"]
            if has_stats:
                team_rows.append(trow)
            for col in ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_cards",
                        "sb_fouls", "sb_xg", "sb_possession", "sb_passes", "sb_offsides"]:
                frow[f"{side}_cur_{col}"] = trow.get(col)
        frow["has_advanced_stats"] = int(has_stats)
        fixture_rows.append(frow)
    conn.close()

    BUILT.mkdir(parents=True, exist_ok=True)
    fdf = pd.DataFrame(fixture_rows).sort_values(["date", "fixture_id"]).reset_index(drop=True)
    tdf = pd.DataFrame(team_rows)
    tdf["date"] = pd.to_datetime(tdf["date"])
    fdf.to_parquet(FIXTURES_OUT, index=False)
    tdf.to_parquet(MATCHES_OUT, index=False)
    print(f"[parse] fixtures: {len(fdf)} | linhas time-jogo c/ stats: {len(tdf)}")
    print(f"[parse] cobertura box-score: {fdf['has_advanced_stats'].mean():.1%}")
    xg_cov = fdf["home_cur_sb_xg"].notna().mean()
    print(f"[parse] cobertura xG: {xg_cov:.1%}")
    return fdf, tdf


# ─── Etapa 2: FEATURES ───────────────────────────────────────────────────────
def classify_round(league_id: int, round_str: str, season: int):
    """Contexto de competição/fase análogo ao classify_tournament de seleções."""
    rl = (round_str or "").lower()
    is_continental = int(league_id in CONTINENTAL)
    is_cup = int(league_id in DOMESTIC_CUP or is_continental)
    is_knockout = int(bool(re.search(
        r"final|semi|quarter|16|32|round of|knockout|play-?off|preliminar", rl)))
    is_final = int(rl.strip() == "final")
    is_group = int("group" in rl or "league stage" in rl or "regular season" in rl)
    m = re.search(r"regular season\s*-\s*(\d+)", rl)
    round_num = int(m.group(1)) if m else None
    if league_id in CONTINENTAL:
        weight, k = 1.0, 28.0
    elif league_id in DOMESTIC_CUP:
        weight, k = 0.85, 24.0
    else:
        weight, k = 0.9, 20.0
    if is_final:
        k += 6.0
    return {"tournament_weight": weight, "k": k, "is_cup": is_cup,
            "is_continental": is_continental, "is_knockout": is_knockout,
            "is_major_final": is_final, "is_group": is_group, "round_num": round_num}


def compute_club_elo(df):
    """Elo pré-jogo por clube. df ordenado por data. Retorna (home_elos, away_elos)."""
    ratings = {}
    home_elos, away_elos = [], []
    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        ra = ratings.get(ht, ELO_START if len(ratings) < 40 else ELO_START_NEW)
        rb = ratings.get(at, ELO_START if len(ratings) < 40 else ELO_START_NEW)
        home_elos.append(ra)
        away_elos.append(rb)
        h = 0.0 if row["neutral"] else HOME_ADV_ELO
        we = 1.0 / (1.0 + 10.0 ** ((rb - (ra + h)) / 400.0))
        hs, ag = row["home_score"], row["away_score"]
        s = 1.0 if hs > ag else (0.0 if hs < ag else 0.5)
        gd = abs(hs - ag)
        mult = 1.0 if gd <= 1 else (1.5 if gd == 2 else (1.75 if gd == 3 else 1.75 + (gd - 3) / 8.0))
        k = row["elo_k"]
        ratings[ht] = ra + k * mult * (s - we)
        ratings[at] = rb + k * mult * ((1.0 - s) - (1.0 - we))
    return home_elos, away_elos


def stage_features():
    df = pd.read_parquet(FIXTURES_OUT)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "fixture_id"]).reset_index(drop=True)
    df["match_id"] = range(1, len(df) + 1)
    print(f"[features] {len(df)} jogos")

    # contexto
    ctx = [classify_round(l, r, s) for l, r, s in
           zip(df["league_id"], df["round"], df["season"])]
    for kcol in ["tournament_weight", "is_cup", "is_continental", "is_knockout",
                 "is_major_final", "is_group", "round_num"]:
        df[kcol] = [c[kcol] for c in ctx]
    df["elo_k"] = [c["k"] for c in ctx]
    df["is_friendly"] = 0
    df["is_qualification"] = 0
    df["is_competitive"] = 1
    df["neutral"] = ((df["is_major_final"] == 1) & (df["is_continental"] == 1) &
                     (df["season"] >= 2019)).astype(int)
    df["real_home_advantage"] = 1 - df["neutral"]
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["decade"] = (df["year"] // 10) * 10

    # progresso da temporada (liga): rodada / máximo de rodadas da temporada
    max_round = df.groupby(["league_id", "season"])["round_num"].transform("max")
    df["season_progress"] = df["round_num"] / max_round

    # alvos
    df["goal_diff"] = df["home_score"] - df["away_score"]
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["result"] = df["goal_diff"].apply(lambda x: "H" if x > 0 else ("A" if x < 0 else "D"))
    df["home_win"] = (df["goal_diff"] > 0).astype(int)
    df["away_win"] = (df["goal_diff"] < 0).astype(int)
    df["draw"] = (df["goal_diff"] == 0).astype(int)
    df["btts"] = ((df["home_score"] > 0) & (df["away_score"] > 0)).astype(int)
    df["over_2_5"] = (df["total_goals"] >= 3).astype(int)

    # Elo
    print("[features] Elo de clubes...")
    he, ae = compute_club_elo(df)
    df["home_elo_pre"], df["away_elo_pre"] = he, ae
    df["elo_diff"] = df["home_elo_pre"] - df["away_elo_pre"]
    h_arr = np.where(df["neutral"].astype(bool).values, 0.0, HOME_ADV_ELO)
    df["elo_home_winprob"] = 1.0 / (1.0 + 10.0 ** (
        (df["away_elo_pre"].values - (df["home_elo_pre"].values + h_arr)) / 400.0))

    # forma (reuso de seleções — gamelog + rolling l3/l5/l10 + streaks)
    print("[features] gamelog + forma...")
    gamelog = build_gamelog(df, pd.DataFrame(columns=["date", "home_team", "away_team", "winner"]))
    form_df = compute_form_features(gamelog)
    feat_cols = [c for c in form_df.columns if c not in ["team", "match_idx"]]
    for side in ["home", "away"]:
        m = (form_df.merge(df[["match_id", f"{side}_team"]],
                           left_on=["match_idx", "team"],
                           right_on=["match_id", f"{side}_team"], how="inner")
             [feat_cols + ["match_id"]]
             .rename(columns={c: f"{side}_{c}" for c in feat_cols}))
        df = df.merge(m, on="match_id", how="left")

    # H2H
    print("[features] H2H...")
    h2h_played, h2h_wr, h2h_gd, days_h2h = compute_h2h(df)
    df["h2h_played"] = h2h_played
    df["h2h_home_winrate"] = h2h_wr
    df["h2h_home_gd_mean"] = h2h_gd
    df["days_since_last_h2h"] = days_h2h

    # diffs
    DIFF_BASES = (["matches_played_before", "days_rest"] +
                  [f"{m}_l{w}" for m in ["gf", "ga", "gd", "ppg", "winrate", "drawrate",
                                          "lossrate", "csrate", "ftsrate", "bttsrate", "pensfor"]
                   for w in WINDOWS] +
                  ["win_streak", "unbeaten_streak", "winless_streak",
                   "scoring_streak", "shootout_winrate_pre"])
    for b in DIFF_BASES:
        hc, ac = f"home_{b}", f"away_{b}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{b}"] = df[hc] - df[ac]

    # SB rolling (reuso de compute_sb_features; usa MATCHES_OUT)
    print("[features] SB rolling (box-score) — pode demorar...")
    sb_df = compute_sb_features(MATCHES_OUT, df)
    if sb_df is not None:
        overlap = [c for c in sb_df.columns if c in df.columns]
        df = df.drop(columns=overlap)
        df = df.join(sb_df, how="left")

    SB_COLS_ = ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_offsides",
                "sb_cards", "sb_yellow", "sb_red", "sb_fouls", "sb_possession", "sb_passes"]
    for col in [f"{c}_{s}" for c in SB_COLS_ for s in ["l3", "l5", "against_l3", "against_l5"]]:
        hc, ac = f"home_{col}", f"away_{col}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{col}"] = df[hc] - df[ac]

    df["has_boxscore_signal"] = df["has_advanced_stats"].fillna(0).astype(int)

    # estilo: imputação indicativa (mediana por competição → elo bin → global)
    STYLE = [f"{side}_style_{sfx}" for side in ["home", "away"]
             for sfx in ["crosses_l5", "crosses_l10", "ppda_l5", "ppda_l10",
                         "fouls_suff_ratio_l5", "fouls_suff_ratio_l10"]]
    df["home_elo_bin"] = (df["home_elo_pre"] // 100) * 100
    df["away_elo_bin"] = (df["away_elo_pre"] // 100) * 100
    for feat in STYLE:
        if feat not in df.columns:
            df[feat] = np.nan
        df[feat] = df[feat].fillna(df.groupby("tournament")[feat].transform("median"))
        side = "home" if feat.startswith("home_") else "away"
        df[feat] = df[feat].fillna(df.groupby(f"{side}_elo_bin")[feat].transform("median"))
        g = df[feat].median()
        df[feat] = df[feat].fillna(0.0 if pd.isna(g) else g)
    df = df.drop(columns=["home_elo_bin", "away_elo_bin"])
    for b in ["style_crosses_l5", "style_crosses_l10", "style_ppda_l5", "style_ppda_l10",
              "style_fouls_suff_ratio_l5", "style_fouls_suff_ratio_l10"]:
        df[f"diff_{b}"] = df[f"home_{b}"] - df[f"away_{b}"]

    # pace (promovido em seleções)
    df["pace_gf"] = df["home_gf_l10"] + df["away_gf_l10"]
    df["pace_ga"] = df["home_ga_l10"] + df["away_ga_l10"]
    df["pace_total"] = df["pace_gf"] + df["pace_ga"]
    df["btts_sum"] = df["home_bttsrate_l10"] + df["away_bttsrate_l10"]

    # xG rolling (novidade de clubes — não existe em seleções)
    print("[features] xG rolling...")
    t = pd.read_parquet(MATCHES_OUT)
    t = t.sort_values(["team", "date"]).reset_index(drop=True)
    xg_roll = {}
    for team, grp in t.groupby("team", sort=False):
        grp = grp.sort_values("date")
        s = grp["sb_xg"].shift(1)
        d5 = s.rolling(5, min_periods=2).mean()
        d10 = s.rolling(10, min_periods=3).mean()
        for dt, v5, v10 in zip(grp["date"], d5, d10):
            xg_roll[(team, dt.strftime("%Y-%m-%d"))] = (v5, v10)
    for side in ["home", "away"]:
        v5s, v10s = [], []
        for tk, dt in zip(df[f"{side}_team"], df["date"]):
            v = xg_roll.get((tk, dt.strftime("%Y-%m-%d")), (np.nan, np.nan))
            v5s.append(v[0]); v10s.append(v[1])
        df[f"{side}_sb_xg_l5"] = v5s
        df[f"{side}_sb_xg_l10"] = v10s
    df["diff_sb_xg_l5"] = df["home_sb_xg_l5"] - df["away_sb_xg_l5"]
    df["diff_sb_xg_l10"] = df["home_sb_xg_l10"] - df["away_sb_xg_l10"]

    df.to_parquet(FEATURES_OUT, index=False)
    print(f"[features] salvo {FEATURES_OUT}: {len(df)} linhas x {len(df.columns)} colunas")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["parse", "features", "all"], default="all")
    a = ap.parse_args()
    if a.stage in ("parse", "all"):
        stage_parse()
    if a.stage in ("features", "all"):
        stage_features()


if __name__ == "__main__":
    main()
