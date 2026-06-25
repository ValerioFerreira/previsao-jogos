#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_final_dataset.py
======================
Reconstroi international_features_enriched_apifootball.csv usando:
  - Base martj42 (auto-baixada e cacheada) como fonte de resultados historicos
  - apifootball_match_team_stats.csv como fonte de estatisticas avancadas

IMPORTANTE: Nao sobrescreve international_features_enriched.csv original.
            Ao final, compara features base com o CSV original para validacao.

Uso:
    python build_final_dataset.py

Saida:
    international_features_enriched_apifootball.csv  (raiz do projeto)
"""

import sys
import warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

# Caminhos
RESULTS_URL     = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SHOOTOUTS_URL   = "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv"
CACHE_DIR       = Path("cache_apifootball")
RESULTS_CACHE   = CACHE_DIR / "results_martj42.csv"
SHOOTOUTS_CACHE = CACHE_DIR / "shootouts_martj42.csv"
STATS_CSV       = Path("data/built/matches.parquet")
OUTPUT_CSV      = Path("international_features_enriched_apifootball.csv")
ORIGINAL_CSV    = Path("api/international_features_enriched.csv")

CUTOFF_YEAR  = 2016
HOME_ADV_ELO = 65.0
ELO_START    = 1500.0
WINDOWS      = [3, 5, 10]


# ─── Download / cache base martj42 ───────────────────────────────────────────
def _download_csv(url, cache_file, label):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if cache_file.exists():
        print(f">> Usando cache local: {cache_file} ({label})")
        return pd.read_csv(cache_file, parse_dates=["date"])
    print(f">> Baixando {label} de {url} ...")
    try:
        df = pd.read_csv(url, parse_dates=["date"])
        df.to_csv(cache_file, index=False)
        print(f"   Cacheado em {cache_file}")
        return df
    except Exception as e:
        print(f"   [AVISO] Falha ao baixar {label}: {e}")
        return pd.DataFrame()


def load_base_data():
    results   = _download_csv(RESULTS_URL, RESULTS_CACHE, "results.csv (martj42)")
    shootouts = _download_csv(SHOOTOUTS_URL, SHOOTOUTS_CACHE, "shootouts.csv (martj42)")
    # Remover partidas sem placar (canceladas/abandonadas)
    results = results.dropna(subset=["home_score", "away_score"]).copy()
    results   = results.sort_values("date").reset_index(drop=True)
    results["match_id"] = range(1, len(results) + 1)
    return results, shootouts


# ─── Classificacao de torneio ─────────────────────────────────────────────────
def classify_tournament(t):
    tl = str(t).lower()
    if "world cup" in tl and "qualif" not in tl and "olympic" not in tl:
        return {"category": "Copa do Mundo",  "weight": 1.00,
                "is_friendly": 0, "is_qualification": 0, "is_major_final": 1,
                "is_competitive": 1, "k": 60}
    if any(x in tl for x in ["qualif", "qualifier", "qualifying"]):
        return {"category": "Eliminatorias",  "weight": 0.60,
                "is_friendly": 0, "is_qualification": 1, "is_major_final": 0,
                "is_competitive": 1, "k": 35}
    if any(x in tl for x in ["euro", "copa am", "africa cup", "gold cup",
                               "asian cup", "confederations", "oceania",
                               "carib", "concacaf championship"]):
        return {"category": "Copa America / Euro / Copa Africana", "weight": 0.85,
                "is_friendly": 0, "is_qualification": 0, "is_major_final": 1,
                "is_competitive": 1, "k": 50}
    if any(x in tl for x in ["nations league", "nations cup", "uefa nations"]):
        return {"category": "Liga das Nacoes", "weight": 0.70,
                "is_friendly": 0, "is_qualification": 0, "is_major_final": 0,
                "is_competitive": 1, "k": 40}
    if any(x in tl for x in ["friendly", "international friendly"]):
        return {"category": "Amistoso", "weight": 0.20,
                "is_friendly": 1, "is_qualification": 0, "is_major_final": 0,
                "is_competitive": 0, "k": 20}
    return {"category": "Outros", "weight": 0.40,
            "is_friendly": 0, "is_qualification": 0, "is_major_final": 0,
            "is_competitive": 1, "k": 30}


# ─── Elo ──────────────────────────────────────────────────────────────────────
def get_base_k(tournament):
    t_clean = str(tournament).strip()
    if "Copa Am" in t_clean:
        if "qualif" in t_clean.lower():
            return 22.0
        return 34.0
        
    t_map = {
        'Friendly': 8.0,
        'FIFA World Cup qualification': 24.0,
        'African Cup of Nations qualification': 20.0,
        'UEFA Nations League': 28.0,
        'UEFA Euro qualification': 22.0,
        'CONCACAF Nations League': 16.0,
        'African Cup of Nations': 34.0,
        'AFC Asian Cup qualification': 20.0,
        'COSAFA Cup': 16.0,
        'UEFA Euro': 34.0,
        'Gold Cup': 30.0,
        'FIFA World Cup': 40.0,
        'AFC Asian Cup': 32.0,
        'Confederations Cup': 30.0,
    }
    
    if t_clean in t_map:
        return t_map[t_clean]
        
    t_lower = t_clean.lower()
    if "friendly" in t_lower:
        return 8.0
    if "world cup" in t_lower:
        if "qualif" in t_lower:
            return 24.0
        return 40.0
    if "nations league" in t_lower:
        if "uefa" in t_lower:
            return 28.0
        return 16.0
    if "euro" in t_lower:
        if "qualif" in t_lower:
            return 22.0
        return 34.0
    if "african cup" in t_lower or "africa cup" in t_lower:
        if "qualif" in t_lower:
            return 20.0
        return 34.0
    if "asian cup" in t_lower:
        if "qualif" in t_lower:
            return 20.0
        return 32.0
    if "gold cup" in t_lower:
        if "qualif" in t_lower:
            return 16.0
        return 30.0
    if "copa am" in t_lower:
        if "qualif" in t_lower:
            return 22.0
        return 34.0
    if "qualification" in t_lower or "qualifying" in t_lower or "qualif" in t_lower:
        return 20.0
        
    return 16.0


def compute_elo(df):
    """Calcula Elo pre-partida para cada linha do df (ordenado por data)."""
    ratings = {}
    home_elos, away_elos = [], []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        ra = ratings.get(ht, ELO_START)
        rb = ratings.get(at, ELO_START)
        home_elos.append(ra)
        away_elos.append(rb)

        k       = get_base_k(row["tournament"])
        neutral = bool(row.get("neutral", 0))
        h       = 0.0 if neutral else HOME_ADV_ELO

        we_home = 1.0 / (1.0 + 10.0 ** ((rb - (ra + h)) / 400.0))
        hs, ag = row["home_score"], row["away_score"]
        s_home = 1.0 if hs > ag else (0.0 if hs < ag else 0.5)

        gd = abs(hs - ag)
        if gd <= 1:
            mult = 1.0
        elif gd == 2:
            mult = 1.5
        elif gd == 3:
            mult = 1.75
        else:
            mult = 1.75 + (gd - 3) / 8.0

        ratings[ht] = ra + k * mult * (s_home - we_home)
        ratings[at] = rb + k * mult * ((1.0 - s_home) - (1.0 - we_home))

    return home_elos, away_elos



# ─── Gamelog de cada time ─────────────────────────────────────────────────────
def build_gamelog(df, shootouts):
    """
    Cria DataFrame longo: uma linha por time x partida.
    Columns: date, team, opponent, match_idx,
             goals_for, goals_against, win, draw, loss, ppg,
             cs (clean sheet), fts (fail to score), btts, pens_win
    """
    # Mapa de shootouts: (date, winner) -> quem ganhou
    shoot_win = {}
    for _, sr in shootouts.iterrows():
        d = pd.Timestamp(sr["date"]).date() if not isinstance(sr["date"], pd.Timestamp) else sr["date"].date()
        shoot_win[(d, str(sr["home_team"]).strip(), str(sr["away_team"]).strip())] = str(sr["winner"]).strip()

    records = []
    for idx, row in df.iterrows():
        d  = row["date"].date()
        ht, at = str(row["home_team"]).strip(), str(row["away_team"]).strip()
        hg, ag = int(row["home_score"]), int(row["away_score"])
        sw = shoot_win.get((d, ht, at))

        for team, gf, ga in [(ht, hg, ag), (at, ag, hg)]:
            opp   = at if team == ht else ht
            win   = int(gf > ga)
            draw  = int(gf == ga)
            loss  = int(gf < ga)
            ppg   = 3 * win + draw
            cs    = int(ga == 0)
            fts   = int(gf == 0)
            btts  = int(gf > 0 and ga > 0)
            pens  = int(sw == team) if sw else 0
            records.append({
                "date":         row["date"],
                "team":         team,
                "opponent":     opp,
                "match_idx":    row["match_id"],
                "goals_for":    gf,
                "goals_against":ga,
                "win":          win,
                "draw":         draw,
                "loss":         loss,
                "ppg":          ppg,
                "cs":           cs,
                "fts":          fts,
                "btts":         btts,
                "pens_win":     pens,
            })

    return pd.DataFrame(records)


# ─── Streaks ──────────────────────────────────────────────────────────────────
def _streak(arr, cond_fn):
    """Retorna array de streaks ANTES de cada posicao (shift implicito)."""
    out = np.zeros(len(arr), dtype=int)
    for i in range(1, len(arr)):
        s = 0
        for j in range(i - 1, -1, -1):
            if cond_fn(arr[j]):
                s += 1
            else:
                break
        out[i] = s
    return out


# ─── Features de forma ───────────────────────────────────────────────────────
def compute_form_features(gamelog):
    """
    Para cada time, calcula via rolling+shift:
      gf/ga/gd/ppg/winrate/drawrate/lossrate/csrate/ftsrate/bttsrate/pensfor (l3/l5/l10)
      win_streak, unbeaten_streak, winless_streak, scoring_streak
      matches_played_before, days_rest, shootout_winrate_pre
    Retorna DataFrame indexado por match_idx (home ou away).
    """
    all_rows = []

    ROLL_COLS = {
        "goals_for":   "gf",
        "goals_against":"ga",
        "gd_raw":      "gd",   # calculado abaixo
        "ppg":         "ppg",
        "win":         "winrate",
        "draw":        "drawrate",
        "loss":        "lossrate",
        "cs":          "csrate",
        "fts":         "ftsrate",
        "btts":        "bttsrate",
        "pens_win":    "pensfor",
    }

    for team, grp in gamelog.groupby("team", sort=False):
        grp = grp.sort_values(["date", "match_idx"]).reset_index(drop=True)
        grp["gd_raw"] = grp["goals_for"] - grp["goals_against"]

        n = len(grp)
        # matches_played_before = indice (0-based) dentro do historico do time
        mb = np.arange(n)

        # days_rest (shift 1 — dias desde ultima partida, nao a atual)
        dr = grp["date"].diff().dt.days.values.copy()
        dr[0] = np.nan


        # Rolling features com shift(1)
        form_vals = {
            "team":      [team] * n,
            "match_idx": grp["match_idx"].values,
            "matches_played_before": mb,
            "days_rest": dr,
        }

        for raw_col, feat_name in ROLL_COLS.items():
            s = grp[raw_col]
            shifted = s.shift(1)
            for w in WINDOWS:
                form_vals[f"{feat_name}_l{w}"] = shifted.rolling(w, min_periods=1).mean().values

        # Streaks
        wins  = grp["win"].values
        draws = grp["draw"].values
        losses= grp["loss"].values
        gfs   = grp["goals_for"].values

        form_vals["win_streak"]      = _streak(wins,  lambda x: x == 1)
        form_vals["unbeaten_streak"] = _streak(losses, lambda x: x == 0)
        form_vals["winless_streak"]  = _streak(wins,  lambda x: x != 1)
        form_vals["scoring_streak"]  = _streak(gfs,   lambda x: x > 0)

        # Shootout winrate pre (historico acumulado, shift 1)
        pens_s = grp["pens_win"].shift(1)
        form_vals["shootout_winrate_pre"] = (
            pens_s.expanding().mean().values
        )

        all_rows.append(pd.DataFrame(form_vals))

    return pd.concat(all_rows, ignore_index=True)


# ─── H2H ─────────────────────────────────────────────────────────────────────
def compute_h2h(df):
    """
    Calcula h2h_played, h2h_home_winrate, h2h_home_gd_mean, days_since_last_h2h
    para cada linha do df (processando em ordem cronologica).
    """
    # historico por par de times: lista de {date, gd_ht}
    h2h_hist = defaultdict(list)

    h2h_played_list       = []
    h2h_home_winrate_list = []
    h2h_home_gd_mean_list = []
    days_since_h2h_list   = []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        d      = row["date"]
        key    = tuple(sorted([ht, at]))
        hist   = h2h_hist[key]

        n = len(hist)
        if n == 0:
            h2h_played_list.append(0)
            h2h_home_winrate_list.append(np.nan)
            h2h_home_gd_mean_list.append(np.nan)
            days_since_h2h_list.append(np.nan)
        else:
            wins = 0
            total_gd = 0.0
            last_d = None
            for entry in hist:
                # entry["gd_ht"] = goal_diff do PRIMEIRO time do par ordenado
                # precisamos converter para perspectiva do ht atual
                first_team = key[0]
                gd_ht_raw  = entry["gd_ht"]
                gd = gd_ht_raw if ht == first_team else -gd_ht_raw
                if gd > 0:
                    wins += 1
                total_gd += gd
                if last_d is None or entry["date"] > last_d:
                    last_d = entry["date"]

            h2h_played_list.append(n)
            h2h_home_winrate_list.append(wins / n)
            h2h_home_gd_mean_list.append(total_gd / n)
            days_since_h2h_list.append((d - last_d).days)

        # Atualiza historico com este jogo
        first_team = key[0]
        gd_ht = row["home_score"] - row["away_score"]
        gd_first = gd_ht if ht == first_team else -gd_ht
        h2h_hist[key].append({"date": d, "gd_ht": gd_first})

    return (h2h_played_list, h2h_home_winrate_list,
            h2h_home_gd_mean_list, days_since_h2h_list)


# ─── Features SB (apifootball) ───────────────────────────────────────────────
SB_COLS = ["sb_shots", "sb_shots_on_target", "sb_corners",
           "sb_offsides", "sb_cards", "sb_yellow", "sb_red",
           "sb_fouls", "sb_possession", "sb_passes"]


def compute_sb_features(stats_csv_path, df_main):
    """
    Para cada partida de df_main, calcula:
      home/away_sb_*_l3 e l5 (medias moveis das ultimas 3/5 partidas com stats)
      home/away_cur_sb_* (stats reais do jogo — alvos dos regressores)
      has_advanced_stats

    Retorna DataFrame alinhado com df_main.index.
    """
    if not stats_csv_path.exists():
        print(f"   [AVISO] {stats_csv_path} nao encontrado — sb_* serao NaN.")
        return None

    stats = pd.read_parquet(stats_csv_path)
    stats["date"] = pd.to_datetime(stats["date"])
    stats["date_str"] = stats["date"].dt.strftime("%Y-%m-%d")
    stats = stats.drop_duplicates(subset=["date_str", "team"])
    stats = stats.sort_values(["date", "team"]).reset_index(drop=True)

    # Lookup (date_str, team) -> stats
    lookup = stats.set_index(["date_str", "team"])

    # Por time: calcular medias moveis l3/l5 (so de jogos com stats, shift 1)
    team_rolling = {}  # team -> DataFrame sorted by date com rolling cols

    # Medias de faltas do campeonato para Fouls_Suffered_Ratio
    global_mean_fouls = stats["sb_fouls"].mean()
    mean_comp_fouls_map = stats.groupby("competition")["sb_fouls"].mean().to_dict()

    for team, grp in stats.groupby("team", sort=False):
        grp = grp.sort_values("date").reset_index(drop=True)

        # stats "against" = stats do oponente nesse jogo
        against_rows = []
        for _, r in grp.iterrows():
            opp = r["opponent"]
            ds  = r["date"].strftime("%Y-%m-%d")
            key = (ds, opp)
            if key in lookup.index:
                against_rows.append(lookup.loc[key])
            else:
                against_rows.append(pd.Series({c: np.nan for c in SB_COLS}))
        against_df = pd.DataFrame(against_rows).reset_index(drop=True)

        # Tactical style features
        grp["style_crosses"] = grp["sb_corners"] * 2.0
        
        opp_passes = against_df["sb_passes"] if "sb_passes" in against_df.columns else pd.Series(np.nan, index=grp.index)
        grp["style_ppda"] = opp_passes / (grp["sb_fouls"] + 1e-5)
        
        opp_fouls = against_df["sb_fouls"] if "sb_fouls" in against_df.columns else pd.Series(np.nan, index=grp.index)
        mean_comp = grp["competition"].map(mean_comp_fouls_map).fillna(global_mean_fouls)
        grp["style_fouls_suff_ratio"] = opp_fouls / (mean_comp + 1e-5)

        rd = {"date": grp["date"].values}
        for col in SB_COLS:
            s = grp[col]
            s_ag = against_df[col] if col in against_df.columns else pd.Series(np.nan, index=grp.index)
            for w in [3, 5]:
                rd[f"{col}_l{w}"]         = s.shift(1).rolling(w, min_periods=1).mean().values
                rd[f"{col}_against_l{w}"] = s_ag.shift(1).rolling(w, min_periods=1).mean().values

        # Rolling windows 5 e 10 para as metricas de estilo
        for w in [5, 10]:
            rd[f"style_crosses_l{w}"] = grp["style_crosses"].shift(1).rolling(w, min_periods=1).mean().values
            rd[f"style_ppda_l{w}"] = grp["style_ppda"].shift(1).rolling(w, min_periods=1).mean().values
            rd[f"style_fouls_suff_ratio_l{w}"] = grp["style_fouls_suff_ratio"].shift(1).rolling(w, min_periods=1).mean().values

        team_rolling[team] = pd.DataFrame(rd)

    # Construir resultado alinhado com df_main
    result_rows = []
    for idx, row in df_main.iterrows():
        ht, at = row["home_team"], row["away_team"]
        d = row["date"]
        ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]

        out = {"idx": idx, "has_advanced_stats": 0}

        # Find match with stats (either exact date or within +-2 days if score matches)
        matched_ds = None
        has_stats = False
        
        for delta in [0, 1, -1, 2, -2]:
            c_d = d + pd.Timedelta(days=delta)
            c_ds = c_d.strftime("%Y-%m-%d")
            
            # 1. Normal (same venue designation)
            key_h = (c_ds, ht)
            key_a = (c_ds, at)
            if key_h in lookup.index and key_a in lookup.index:
                scores_match = True
                if delta != 0:
                    goals_h = lookup.loc[key_h, "goals_scored"]
                    goals_a = lookup.loc[key_a, "goals_scored"]
                    if isinstance(goals_h, pd.Series): goals_h = goals_h.iloc[0]
                    if isinstance(goals_a, pd.Series): goals_a = goals_a.iloc[0]
                    
                    if pd.isna(goals_h) or pd.isna(goals_a) or int(goals_h) != int(row["home_score"]) or int(goals_a) != int(row["away_score"]):
                        scores_match = False
                
                if scores_match:
                    row_h = lookup.loc[key_h]
                    row_a = lookup.loc[key_a]
                    stats_exist = True
                    for col in ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_cards"]:
                        val_h = row_h[col]
                        val_a = row_a[col]
                        if isinstance(val_h, pd.Series): val_h = val_h.iloc[0]
                        if isinstance(val_a, pd.Series): val_a = val_a.iloc[0]
                        if pd.isna(val_h) or pd.isna(val_a):
                            stats_exist = False
                            break
                    if stats_exist:
                        has_stats = True
                        matched_ds = c_ds
                        break
            
            # 2. Swapped venue (neutral venue designation)
            key_h_swapped = (c_ds, at)
            key_a_swapped = (c_ds, ht)
            if key_h_swapped in lookup.index and key_a_swapped in lookup.index:
                scores_match = True
                if delta != 0:
                    goals_h = lookup.loc[key_h_swapped, "goals_scored"]
                    goals_a = lookup.loc[key_a_swapped, "goals_scored"]
                    if isinstance(goals_h, pd.Series): goals_h = goals_h.iloc[0]
                    if isinstance(goals_a, pd.Series): goals_a = goals_a.iloc[0]
                    
                    if pd.isna(goals_h) or pd.isna(goals_a) or int(goals_h) != int(row["away_score"]) or int(goals_a) != int(row["home_score"]):
                        scores_match = False
                
                if scores_match:
                    row_h = lookup.loc[key_h_swapped]
                    row_a = lookup.loc[key_a_swapped]
                    stats_exist = True
                    for col in ["sb_shots", "sb_shots_on_target", "sb_corners", "sb_cards"]:
                        val_h = row_h[col]
                        val_a = row_a[col]
                        if isinstance(val_h, pd.Series): val_h = val_h.iloc[0]
                        if isinstance(val_a, pd.Series): val_a = val_a.iloc[0]
                        if pd.isna(val_h) or pd.isna(val_a):
                            stats_exist = False
                            break
                    if stats_exist:
                        has_stats = True
                        matched_ds = c_ds
                        break

        use_ds = matched_ds if matched_ds is not None else ds
        for side, team in [("home", ht), ("away", at)]:
            key = (use_ds, team)
            if key in lookup.index:
                for col in SB_COLS:
                    val = lookup.loc[key, col]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    out[f"{side}_cur_{col}"] = val
            else:
                for col in SB_COLS:
                    out[f"{side}_cur_{col}"] = np.nan
                    
        out["has_advanced_stats"] = 1 if has_stats else 0

        # Medias moveis lagged
        STYLE_FEATS = [
            "style_crosses_l5", "style_crosses_l10",
            "style_ppda_l5", "style_ppda_l10",
            "style_fouls_suff_ratio_l5", "style_fouls_suff_ratio_l10"
        ]
        for side, team in [("home", ht), ("away", at)]:
            if team not in team_rolling:
                for col in SB_COLS:
                    for w in [3, 5]:
                        out[f"{side}_{col}_l{w}"]         = np.nan
                        out[f"{side}_{col}_against_l{w}"] = np.nan
                for sf in STYLE_FEATS:
                    out[f"{side}_{sf}"] = np.nan
                continue

            tr = team_rolling[team]
            matched_d = pd.to_datetime(matched_ds) if matched_ds is not None else d
            match_rows = tr[tr["date"] == matched_d]
            if len(match_rows) == 0:
                for col in SB_COLS:
                    for w in [3, 5]:
                        out[f"{side}_{col}_l{w}"]         = np.nan
                        out[f"{side}_{col}_against_l{w}"] = np.nan
                for sf in STYLE_FEATS:
                    out[f"{side}_{sf}"] = np.nan
            else:
                mr = match_rows.iloc[0]
                for col in SB_COLS:
                    for w in [3, 5]:
                        out[f"{side}_{col}_l{w}"]         = mr.get(f"{col}_l{w}", np.nan)
                        out[f"{side}_{col}_against_l{w}"] = mr.get(f"{col}_against_l{w}", np.nan)
                for sf in STYLE_FEATS:
                    out[f"{side}_{sf}"] = mr.get(sf, np.nan)

        result_rows.append(out)

    return pd.DataFrame(result_rows).set_index("idx")


def compare_with_original(df_new, original_path):
    """
    Compara features base (Elo, forma, h2h) entre novo e original CSV.
    Usa merge em vez de reindex para evitar ValueError com chaves duplicadas.
    """
    if not original_path.exists():
        print(f"\n[INFO] CSV original nao encontrado. Sem comparacao.")
        return

    print("\n" + "=" * 80)
    print("COMPARACAO COM CSV ORIGINAL")
    print("=" * 80)

    df_old = pd.read_csv(original_path, parse_dates=["date"])
    KEY_COLS = ["date", "home_team", "away_team"]

    for df_, label in [(df_new, "novo"), (df_old, "original")]:
        dupes = df_.duplicated(subset=KEY_COLS).sum()
        if dupes:
            print(f"   [INFO] CSV {label}: {dupes} duplicatas -- mantendo 1a ocorrencia.")

    df_n = df_new.drop_duplicates(subset=KEY_COLS, keep="first").copy()
    df_o = df_old.drop_duplicates(subset=KEY_COLS, keep="first").copy()

    print(f"Jogos no novo CSV   : {len(df_n)}")
    print(f"Jogos no original   : {len(df_o)}")

    BASE_FEATS = [
        "home_elo_pre", "away_elo_pre", "elo_diff", "elo_home_winprob",
        "home_gf_l3",  "home_ga_l3",  "home_ppg_l3",
        "home_gf_l5",  "home_ga_l5",  "home_ppg_l5",
        "home_gf_l10", "home_ga_l10", "home_ppg_l10",
        "away_gf_l5",  "away_ga_l5",  "away_ppg_l5",
        "h2h_played",  "h2h_home_winrate", "h2h_home_gd_mean",
        "home_win_streak", "home_days_rest", "away_days_rest",
    ]

    cols_n = KEY_COLS + [f for f in BASE_FEATS if f in df_n.columns]
    cols_o = KEY_COLS + [f for f in BASE_FEATS if f in df_o.columns]

    merged = df_n[cols_n].merge(df_o[cols_o], on=KEY_COLS, how="inner",
                                suffixes=("_new", "_old"))
    n_common = len(merged)
    print(f"Jogos em comum      : {n_common}")

    if n_common == 0:
        print("[AVISO] Nenhum jogo em comum.")
        return

    hdr = "  {:<33} {:>6} {:>10} {:>10} {:>9}  Status".format(
          "Feature", "N", "Max Diff", "Mean Diff", "Corr")
    print("\n" + hdr)
    print("  " + "-" * 77)

    all_ok = True
    for feat in BASE_FEATS:
        cn, co = f"{feat}_new", f"{feat}_old"
        if cn not in merged.columns or co not in merged.columns:
            continue
        s_n, s_o = merged[cn], merged[co]
        mask = s_n.notna() & s_o.notna()
        n_pairs = int(mask.sum())
        if n_pairs < 2:
            print(f"  {feat:<33} {n_pairs:>6}  (dados insuf.)")
            continue
        diff = (s_n - s_o)[mask].abs()
        corr = float(s_n[mask].corr(s_o[mask]))
        threshold = 100 if "elo" in feat else (2 if feat == "h2h_played" else 0.5)
        diverge = diff.max() > threshold
        if diverge:
            all_ok = False
        status = "DIVERGE" if diverge else "OK"
        print("  {:<33} {:>6} {:>10.3f} {:>10.4f} {:>9.5f}  {}".format(
              feat, n_pairs, diff.max(), diff.mean(), corr, status))

    print()
    if all_ok:
        print("[OK] Todas as features base dentro dos limiares aceitaveis.")
    else:
        print("[ATENCAO] Divergencias detectadas -- veja linhas DIVERGE.")
        print("  Elo  : diferenca esperada se K-factors diferirem do original.")
        print("  Forma: diferenca indica logica de janela diferente.")

    if "home_elo_pre_new" in merged.columns and "home_elo_pre_old" in merged.columns:
        merged["_elo_abs"] = (merged["home_elo_pre_new"] - merged["home_elo_pre_old"]).abs()
        top5 = merged.nlargest(5, "_elo_abs")[
            ["date", "home_team", "away_team",
             "home_elo_pre_new", "home_elo_pre_old", "_elo_abs"]]
        if not top5.empty and top5["_elo_abs"].max() > 1:
            print("\nTop-5 maior divergencia em home_elo_pre:")
            print(top5.to_string(index=False))


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("BUILD_FINAL_DATASET (API-Football)")
    print("=" * 65)

    # 1. Carregar dados base
    print("\n[1/7] Carregando base martj42...")
    df, shootouts = load_base_data()
    print(f"   {len(df)} partidas | {len(shootouts)} shootouts")

    # 2. Context features
    print("\n[2/7] Calculando features de contexto e alvos...")
    ti_list = df["tournament"].apply(classify_tournament)
    df["tournament_weight"] = [t["weight"]         for t in ti_list]
    df["is_friendly"]       = [t["is_friendly"]     for t in ti_list]
    df["is_qualification"]  = [t["is_qualification"] for t in ti_list]
    df["is_major_final"]    = [t["is_major_final"]   for t in ti_list]
    df["is_competitive"]    = [t["is_competitive"]   for t in ti_list]
    df["real_home_advantage"] = (1 - df["neutral"].fillna(0).astype(int))
    df["year"]   = df["date"].dt.year
    df["month"]  = df["date"].dt.month
    df["decade"] = (df["year"] // 10) * 10

    df["goal_diff"]  = df["home_score"] - df["away_score"]
    df["total_goals"]= df["home_score"] + df["away_score"]
    df["result"]     = df["goal_diff"].apply(lambda x: "H" if x > 0 else ("A" if x < 0 else "D"))
    df["home_win"]   = (df["goal_diff"] > 0).astype(int)
    df["away_win"]   = (df["goal_diff"] < 0).astype(int)
    df["draw"]       = (df["goal_diff"] == 0).astype(int)
    df["btts"]       = ((df["home_score"] > 0) & (df["away_score"] > 0)).astype(int)
    df["over_2_5"]   = (df["total_goals"] >= 3).astype(int)

    # 3. Elo
    print("\n[3/7] Calculando Elo...")
    home_elos, away_elos = compute_elo(df)
    df["home_elo_pre"] = home_elos
    df["away_elo_pre"] = away_elos
    df["elo_diff"]     = df["home_elo_pre"] - df["away_elo_pre"]
    neutral_arr = df["neutral"].fillna(0).astype(bool).values
    h_arr = np.where(neutral_arr, 0.0, HOME_ADV_ELO)
    df["elo_home_winprob"] = 1.0 / (1.0 + 10.0 ** (
        (df["away_elo_pre"].values - (df["home_elo_pre"].values + h_arr)) / 400.0
    ))

    # 4. Gamelog + features de forma
    print("\n[4/7] Construindo gamelog e features de forma...")
    gamelog = build_gamelog(df, shootouts)
    form_df = compute_form_features(gamelog)
    print(f"   {len(form_df)} linhas no gamelog de forma")

    # Separar home e away: filtrar form_df pelo papel (match_idx coincide
    # com a linha de df onde o time jogou como home ou away)
    feat_cols = [c for c in form_df.columns if c not in ["team", "match_idx"]]

    # Home: para cada partida, a linha do time que jogou em casa
    home_form = (form_df
                 .merge(df[["match_id", "home_team"]],
                        left_on=["match_idx", "team"],
                        right_on=["match_id", "home_team"],
                        how="inner")
                 [feat_cols + ["match_id"]])
    home_form = home_form.rename(columns={c: f"home_{c}" for c in feat_cols})

    # Away: para cada partida, a linha do time que jogou como visitante
    away_form = (form_df
                 .merge(df[["match_id", "away_team"]],
                        left_on=["match_idx", "team"],
                        right_on=["match_id", "away_team"],
                        how="inner")
                 [feat_cols + ["match_id"]])
    away_form = away_form.rename(columns={c: f"away_{c}" for c in feat_cols})

    df = df.merge(home_form, on="match_id", how="left")
    df = df.merge(away_form, on="match_id", how="left")

    # 5. H2H
    print("\n[5/7] Calculando features H2H...")
    h2h_played, h2h_home_wr, h2h_home_gd, days_h2h = compute_h2h(df)
    df["h2h_played"]          = h2h_played
    df["h2h_home_winrate"]    = h2h_home_wr
    df["h2h_home_gd_mean"]    = h2h_home_gd
    df["days_since_last_h2h"] = days_h2h

    # 6. Diff features
    print("\n[6/7] Calculando diff features...")
    DIFF_BASES = [
        "matches_played_before", "days_rest",
    ] + [f"{m}_l{w}" for m in ["gf","ga","gd","ppg","winrate","drawrate",
                                 "lossrate","csrate","ftsrate","bttsrate","pensfor"]
           for w in WINDOWS] + [
        "win_streak", "unbeaten_streak", "winless_streak",
        "scoring_streak", "shootout_winrate_pre"
    ]

    for b in DIFF_BASES:
        hc = f"home_{b}"
        ac = f"away_{b}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{b}"] = df[hc] - df[ac]

    # 7. SB features
    print("\n[7/7] Calculando features SB (apifootball)...")
    sb_df = compute_sb_features(STATS_CSV, df)

    if sb_df is not None:
        df = df.join(sb_df, how="left")
        n_adv = int(df.get("has_advanced_stats", pd.Series(0)).fillna(0).sum())
        print(f"   Partidas com stats avancadas: {n_adv}")
    else:
        df["has_advanced_stats"] = 0

    # Calcular diff para colunas SB
    SB_FEAT_COLS = [
        f"{col}_{sfx}" for col in SB_COLS
        for sfx in ["l3", "l5", "against_l3", "against_l5"]
    ]
    for col in SB_FEAT_COLS:
        hc = f"home_{col}"
        ac = f"away_{col}"
        if hc in df.columns and ac in df.columns:
            df[f"diff_{col}"] = df[hc] - df[ac]

    # 1. Crie a feature binaria has_boxscore_signal
    df["has_boxscore_signal"] = df["has_advanced_stats"].fillna(0).astype(int)

    # 2. Imputacao Indicativa para as novas features de estilo
    STYLE_FEATS_FULL = [
        "home_style_crosses_l5", "home_style_crosses_l10",
        "away_style_crosses_l5", "away_style_crosses_l10",
        "home_style_ppda_l5", "home_style_ppda_l10",
        "away_style_ppda_l5", "away_style_ppda_l10",
        "home_style_fouls_suff_ratio_l5", "home_style_fouls_suff_ratio_l10",
        "away_style_fouls_suff_ratio_l5", "away_style_fouls_suff_ratio_l10"
    ]

    # Pre-calcula elo_bin para imputacao baseada em Elo
    df["home_elo_bin"] = (df["home_elo_pre"] // 100) * 100
    df["away_elo_bin"] = (df["away_elo_pre"] // 100) * 100

    print("\n>> Executando imputacao indicativa para features de estilo...")
    for feat in STYLE_FEATS_FULL:
        if feat not in df.columns:
            df[feat] = np.nan
        
        # a) Mediana por campeonato (tournament no df)
        comp_medians = df.groupby("tournament")[feat].transform("median")
        df[feat] = df[feat].fillna(comp_medians)
        
        # b) Mediana por Elo bin correspondente
        side = "home" if feat.startswith("home_") else "away"
        elo_bin_col = f"{side}_elo_bin"
        elo_medians = df.groupby(elo_bin_col)[feat].transform("median")
        df[feat] = df[feat].fillna(elo_medians)
        
        # c) Mediana global
        global_median = df[feat].median()
        if pd.isna(global_median):
            global_median = 0.0
        df[feat] = df[feat].fillna(global_median)

    # Remove colunas auxiliares de elo_bin
    df = df.drop(columns=["home_elo_bin", "away_elo_bin"])

    # Calcular diff para as features de estilo bruto (para o pipeline)
    for base_feat in ["style_crosses_l5", "style_crosses_l10",
                      "style_ppda_l5", "style_ppda_l10",
                      "style_fouls_suff_ratio_l5", "style_fouls_suff_ratio_l10"]:
        df[f"diff_{base_feat}"] = df[f"home_{base_feat}"] - df[f"away_{base_feat}"]

    # Renomear cur_sb_* para corresponder ao CSV original
    # home_cur_sb_shots, home_cur_sb_shots_on_target, etc.
    # (ja foram criados com esse padrao em compute_sb_features)

    # Filtrar por CUTOFF_YEAR
    print(f"\n>> Filtrando para ano >= {CUTOFF_YEAR}...")
    df_out = df[df["year"] >= CUTOFF_YEAR].copy().reset_index(drop=True)
    print(f"   {len(df_out)} linhas apos filtro ({len(df)} total)")

    # Features de PACE (ambiente de gols) — somas leakage-safe das rates l10 já
    # calculadas. Edge pequeno mas estável no BTTS (8/9 janelas walk-forward) e
    # ajuda gols totais; ver reports/btts_relatorio.md §7.
    if {"home_gf_l10", "away_gf_l10"}.issubset(df_out.columns):
        df_out["pace_gf"] = df_out["home_gf_l10"] + df_out["away_gf_l10"]
    if {"home_ga_l10", "away_ga_l10"}.issubset(df_out.columns):
        df_out["pace_ga"] = df_out["home_ga_l10"] + df_out["away_ga_l10"]
    if {"pace_gf", "pace_ga"}.issubset(df_out.columns):
        df_out["pace_total"] = df_out["pace_gf"] + df_out["pace_ga"]
    if {"home_bttsrate_l10", "away_bttsrate_l10"}.issubset(df_out.columns):
        df_out["btts_sum"] = df_out["home_bttsrate_l10"] + df_out["away_bttsrate_l10"]

    # Salvar no Banco de Dados
    try:
        from app.db.connection import engine, truncate_and_append
        print(f"\n>> Salvando na tabela 'features_enriched' no banco de dados...")
        truncate_and_append(df_out, "features_enriched", engine)
        print(f"   Salvo com sucesso: {len(df_out)} linhas | {len(df_out.columns)} colunas")
    except Exception as e:
        print(f"\n[ERRO] Falha ao salvar no banco de dados: {e}")
        df_out.to_csv(OUTPUT_CSV, index=False)
        print(f"\n>> Fallback local CSV salvo: {OUTPUT_CSV}")
        print(f"   {len(df_out)} linhas | {len(df_out.columns)} colunas")

    # Comparar com original
    compare_with_original(df_out.copy(), ORIGINAL_CSV)

    print(f"\n[CONCLUIDO] {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
