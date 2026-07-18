#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_clubs/club_features.py
=================================
Fase 5 — engenharia de atributos PRÓPRIA de clubes (docs/PLANO_PESQUISA_CLUBES.md §5).
Cada função recebe o df de fixtures/features já ordenado por data e devolve as
colunas do grupo, sempre point-in-time (shift(1) implícito nos rolling/expanding).

Grupos: 5.1 congestão, 5.2 altitude+viagem, 5.3 fase/mata-mata, 5.4 rotação de
elenco, 5.5 xG estendido (over/under-performance), 5.6 GAP ratings, 5.7 importância
da partida (tabela corrente simulada).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .ratings import compute_gap_ratings

# ─── 5.2 altitude — cidades de referência (Libertadores/Sul-Americana; efeito
# empírico mais documentado do futebol sul-americano) ────────────────────────
ALTITUDE_M = {
    "La Paz": 3625, "El Alto": 4150, "Quito": 2850, "Bogota": 2640, "Bogotá": 2640,
    "Cusco": 3399, "Sucre": 2810, "Cochabamba": 2558, "Huancayo": 3259,
    "Ciudad Bolivar": 500, "Mexico City": 2240,
}


def group_congestion(df: pd.DataFrame) -> pd.DataFrame:
    """5.1 — jogos nos últimos 7/14/30 dias, POR TIME, em QUALQUER competição
    (o dataset já unifica as 13 ligas por time via Nome#id)."""
    n = len(df)
    # uid único por linha (posição), preservado através do sort — evita o bug de
    # realinhar por .iloc após reordenar por team/date (índices duplicados 0..n-1
    # entre home/away tornariam .loc ambíguo).
    home = pd.DataFrame({"uid": np.arange(n), "side": "home",
                        "date": df["date"].to_numpy(), "team": df["home_team"].to_numpy()})
    away = pd.DataFrame({"uid": np.arange(n), "side": "away",
                        "date": df["date"].to_numpy(), "team": df["away_team"].to_numpy()})
    long = pd.concat([home, away], ignore_index=True)
    long = long.sort_values(["team", "date"]).reset_index(drop=True)

    for w, name in [(7, "g7"), (14, "g14"), (30, "g30")]:
        out = np.zeros(len(long), dtype=int)
        for team, grp in long.groupby("team", sort=False):
            dates = grp["date"].to_numpy()
            cnt = np.zeros(len(dates), dtype=int)
            for i in range(len(dates)):
                lo = dates[i] - np.timedelta64(w, "D")
                cnt[i] = int(((dates[:i] > lo) & (dates[:i] < dates[i])).sum())
            out[grp.index.to_numpy()] = cnt
        long[name] = out

    res = pd.DataFrame(index=df.index)
    for name, out_name in [("g7", "l7"), ("g14", "l14"), ("g30", "l30")]:
        # reordena por uid (posição original 0..n-1) antes de extrair, já que
        # `long` está fisicamente ordenado por team/date neste ponto
        h_sub = long[long["side"] == "home"].sort_values("uid")[name].to_numpy()
        a_sub = long[long["side"] == "away"].sort_values("uid")[name].to_numpy()
        res[f"home_games_{out_name}"] = h_sub
        res[f"away_games_{out_name}"] = a_sub
        res[f"diff_games_{out_name}"] = h_sub - a_sub
    return res


def _norm_city(city):
    if not isinstance(city, str):
        return None
    c = city.split(",")[0].strip()
    return c


def group_altitude_travel(df: pd.DataFrame) -> pd.DataFrame:
    """5.2 — altitude do palco (efeito visitante de baixa altitude jogando em
    altitude) + indicador de "acabou de viajar" (cidade mudou desde o último jogo
    do time, qualquer competição) — proxy de viagem sem depender de geocodificação
    exaustiva (1055 cidades distintas, muitas com mojibake de acentuação)."""
    res = pd.DataFrame(index=df.index)
    city = df["venue_city"].map(_norm_city)
    alt = city.map(ALTITUDE_M).fillna(0.0)
    res["venue_altitude_m"] = alt.to_numpy()
    res["is_high_altitude"] = (alt >= 2000).astype(int).to_numpy()

    for side, team_col in [("home", "home_team"), ("away", "away_team")]:
        long = df[["date", team_col]].rename(columns={team_col: "team"}).copy()
        long["city"] = city
        long = long.sort_values(["team", "date"])
        long["prev_city"] = long.groupby("team")["city"].shift(1)
        long["just_traveled"] = (long["city"] != long["prev_city"]).astype(int)
        long.loc[long["prev_city"].isna(), "just_traveled"] = 0
        res[f"{side}_just_traveled"] = long["just_traveled"].reindex(df.index).to_numpy()
    res["diff_just_traveled"] = res["home_just_traveled"] - res["away_just_traveled"]
    return res


def group_phase(df: pd.DataFrame) -> pd.DataFrame:
    """5.3 — mata-mata ida/volta (extraído do texto do round) e "decisão" (jogo 2
    de mata-mata = maior pressão)."""
    res = pd.DataFrame(index=df.index)
    rl = df["round"].fillna("").str.lower()
    res["is_second_leg"] = rl.str.contains(r"2nd leg|leg 2|volta").astype(int)
    res["is_first_leg"] = rl.str.contains(r"1st leg|leg 1|ida").astype(int)
    res["is_decision_game"] = ((df["is_knockout"] == 1) &
                               (res["is_second_leg"] == 1)).astype(int)
    return res


def group_squad_rotation(df: pd.DataFrame, lineups: pd.DataFrame) -> pd.DataFrame:
    """5.4 — nº de mudanças no XI vs o último jogo do time (qualquer competição).
    `lineups`: fixture_id, team, player_ids (string csv de 11 ids)."""
    lu = lineups.copy()
    lu["ids_set"] = lu["player_ids"].str.split(",").apply(lambda l: frozenset(l))
    lu_map = lu.set_index(["fixture_id", "team"])["ids_set"]

    res = pd.DataFrame(index=df.index)
    for side, team_col in [("home", "home_team"), ("away", "away_team")]:
        long = df[["date", "fixture_id", team_col]].rename(columns={team_col: "team"}).copy()
        long["ids"] = long.apply(lambda r: lu_map.get((r["fixture_id"], r["team"])), axis=1)
        long = long.sort_values(["team", "date"])
        long["prev_ids"] = long.groupby("team")["ids"].shift(1)

        def _changes(row):
            a, b = row["ids"], row["prev_ids"]
            if not isinstance(a, frozenset) or not isinstance(b, frozenset):
                return np.nan
            return len(a.symmetric_difference(b)) / 2.0
        long["rotation"] = long.apply(_changes, axis=1)
        res[f"{side}_squad_rotation"] = long["rotation"].reindex(df.index).to_numpy()
    med = pd.concat([res["home_squad_rotation"], res["away_squad_rotation"]]).median()
    res = res.fillna(med if pd.notna(med) else 3.0)
    res["diff_squad_rotation"] = res["home_squad_rotation"] - res["away_squad_rotation"]
    return res


def group_xg_overperformance(df: pd.DataFrame, matches_long: pd.DataFrame) -> pd.DataFrame:
    """5.5 — over/under-performance de finalização: (gols - xG) rolling l5/l10 por
    time. Sinal de "sorte"/eficiência que tende a reverter à média (regressão à
    média é um achado replicado na literatura de xG)."""
    t = matches_long.sort_values(["team", "date"]).copy()
    t["diff_g_xg"] = t["goals_scored"] - t["sb_xg"]
    for w in [5, 10]:
        t[f"g_minus_xg_l{w}"] = (t.groupby("team")["diff_g_xg"]
                                 .transform(lambda s: s.shift(1).rolling(w, min_periods=2).mean()))
    key_map = t.set_index(["team", "date"])[["g_minus_xg_l5", "g_minus_xg_l10"]]
    res = pd.DataFrame(index=df.index)
    for side, team_col in [("home", "home_team"), ("away", "away_team")]:
        vals5, vals10 = [], []
        for tk, dt in zip(df[team_col], df["date"]):
            try:
                row = key_map.loc[(tk, dt)]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                vals5.append(row["g_minus_xg_l5"]); vals10.append(row["g_minus_xg_l10"])
            except KeyError:
                vals5.append(np.nan); vals10.append(np.nan)
        res[f"{side}_g_minus_xg_l5"] = vals5
        res[f"{side}_g_minus_xg_l10"] = vals10
    res["diff_g_minus_xg_l5"] = res["home_g_minus_xg_l5"] - res["away_g_minus_xg_l5"]
    res["diff_g_minus_xg_l10"] = res["home_g_minus_xg_l10"] - res["away_g_minus_xg_l10"]
    return res


def group_gap_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """5.6 — GAP ratings (Wheatcroft) para chutes e escanteios, plugando o módulo
    já pronto em research_clubs/ratings.py."""
    df_sorted = df.sort_values("date")
    parts = []
    for stat, prefix in [("home_cur_sb_shots", "gap_shots"), ("home_cur_sb_corners", "gap_corners")]:
        away_col = stat.replace("home_", "away_")
        g = compute_gap_ratings(df_sorted, stat, away_col, prefix=prefix)
        parts.append(g)
    res = pd.concat(parts, axis=1)
    return res.reindex(df.index)


def group_match_importance(df: pd.DataFrame) -> pd.DataFrame:
    """5.7 — tabela corrente simulada por (league_id, season) para competições em
    formato de liga (is_group==1 nas domésticas + fase de grupos continental):
    posição e distância a pontos do G4 (título/vaga)/Z4 (rebaixamento), calculadas
    SÓ com jogos anteriores da própria temporada (point-in-time)."""
    res = pd.DataFrame(index=df.index, columns=[
        "home_table_pos", "home_pts_to_top4", "home_pts_to_relegation",
        "away_table_pos", "away_pts_to_top4", "away_pts_to_relegation"], dtype=float)
    for (lid, season), grp in df.groupby(["league_id", "season"]):
        grp = grp.sort_values(["date", "fixture_id"])
        pts = {}
        played = {}
        n_teams = len(set(grp["home_team"]) | set(grp["away_team"]))
        for idx, row in grp.iterrows():
            ht, at = row["home_team"], row["away_team"]
            standings = sorted(pts.items(), key=lambda kv: -kv[1])
            rank = {t: i + 1 for i, (t, _) in enumerate(standings)}
            top4_pts = standings[3][1] if len(standings) > 3 else (standings[-1][1] if standings else 0)
            bot4_idx = max(n_teams - 4, 0)
            bot4_pts = standings[bot4_idx][1] if len(standings) > bot4_idx else (
                standings[-1][1] if standings else 0)
            for side, team in [("home", ht), ("away", at)]:
                p = pts.get(team, 0)
                res.loc[idx, f"{side}_table_pos"] = rank.get(team, n_teams)
                res.loc[idx, f"{side}_pts_to_top4"] = top4_pts - p
                res.loc[idx, f"{side}_pts_to_relegation"] = p - bot4_pts
            hg, ag = row["home_score"], row["away_score"]
            ph = 3 if hg > ag else (1 if hg == ag else 0)
            pa = 3 if ag > hg else (1 if hg == ag else 0)
            pts[ht] = pts.get(ht, 0) + ph
            pts[at] = pts.get(at, 0) + pa
    res["diff_table_pos"] = res["away_table_pos"] - res["home_table_pos"]  # positivo = mandante melhor
    med = res.median(numeric_only=True)
    return res.fillna(med)


def build_all_groups(df: pd.DataFrame, lineups: pd.DataFrame, matches_long: pd.DataFrame) -> dict:
    """Retorna {nome_grupo: DataFrame} para uso em ablação (Fase 5 — testar cada
    grupo isoladamente sobre o baseline vencedor da Fase 1)."""
    df = df.sort_values("date").reset_index(drop=False).rename(columns={"index": "_orig_idx"})
    df = df.set_index("_orig_idx")
    groups = {}
    print("  [5.1] congestão...", flush=True)
    groups["congestion"] = group_congestion(df)
    print("  [5.2] altitude/viagem...", flush=True)
    groups["altitude_travel"] = group_altitude_travel(df)
    print("  [5.3] fase/mata-mata...", flush=True)
    groups["phase"] = group_phase(df)
    print("  [5.4] rotação de elenco...", flush=True)
    groups["squad_rotation"] = group_squad_rotation(df, lineups)
    print("  [5.5] xG over/under-performance...", flush=True)
    groups["xg_overperf"] = group_xg_overperformance(df, matches_long)
    print("  [5.6] GAP ratings...", flush=True)
    groups["gap_ratings"] = group_gap_ratings(df)
    print("  [5.7] importância da partida...", flush=True)
    groups["match_importance"] = group_match_importance(df)
    return groups
