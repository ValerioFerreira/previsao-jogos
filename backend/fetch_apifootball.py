#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_apifootball.py
====================
Coleta estatísticas avançadas da Copa do Mundo 2022 e 2026 via API-Football.

Uso:
    python fetch_apifootball.py

Requer variável de ambiente APIFOOTBALL_KEY.

Restrições de cota (plano gratuito):
  - 100 req/dia no total
  - Esta execução: máx 90 req (MAX_REQS_EXEC) — folga de 10 para segurança
  - Ritmo: máx 10 req/min → 6 s de pausa entre chamadas (SLEEP_BETWEEN)

Cache:
  - Cada fixture: cache_apifootball/<fixture_id>.json
  - Progresso:    cache_apifootball/progress.json
  - Retomada:     fixtures já cacheados nunca são rebaixados

Saída:
  apifootball_match_team_stats.csv
  Colunas: date, team, opponent, is_home, competition, season,
           sb_shots, sb_shots_on_target, sb_corners, sb_offsides,
           sb_yellow, sb_red, sb_cards, sb_fouls, sb_possession
"""

import os
import json
import time
import sys
from pathlib import Path

import requests
import pandas as pd

# Constantes
BASE_URL      = "https://v3.football.api-sports.io"
CACHE_DIR     = Path("cache_apifootball")
PROGRESS_FILE = CACHE_DIR / "progress.json"
OUTPUT_CSV    = "apifootball_match_team_stats.csv"

MAX_REQS_EXEC = 90
RATE_PER_MIN  = 10
SLEEP_BETWEEN = 60.0 / RATE_PER_MIN  # 6 s entre chamadas

SEASONS = [2022, 2026]
LEAGUE  = 1  # FIFA World Cup na API-Football

# Normalização de nomes (API-Football -> martj42/international_results)
TEAM_NAME_MAP = {
    "Korea Republic":           "South Korea",
    "IR Iran":                  "Iran",
    "China PR":                 "China",
    "Kyrgyz Republic":          "Kyrgyzstan",
    "North Macedonia":          "North Macedonia",
    "FYR Macedonia":            "North Macedonia",
    "Cote d'Ivoire":            "Ivory Coast",
    "Congo DR":                 "DR Congo",
    "USA":                      "United States",
    "Trinidad & Tobago":        "Trinidad and Tobago",
    "Antigua & Barbuda":        "Antigua and Barbuda",
    "St Kitts & Nevis":         "Saint Kitts and Nevis",
    "St. Kitts and Nevis":      "Saint Kitts and Nevis",
    "St Vincent & Grenadines":  "Saint Vincent and the Grenadines",
    "St. Vincent / Grenadines": "Saint Vincent and the Grenadines",
    "Czechia":                  "Czech Republic",
    "Czech Republic":           "Czech Republic",
    "Türkiye":                  "Turkey",
    "Turkey":                   "Turkey",
    "Bosnia-Herzegovina":       "Bosnia and Herzegovina",
    "Bosnia & Herzegovina":     "Bosnia and Herzegovina",
    "Cape Verde Islands":       "Cape Verde",
    "Cape Verde":               "Cape Verde",
    "Republic of Ireland":      "Republic of Ireland",
    "Rep. of Ireland":          "Republic of Ireland",
    "Rep. Of Ireland":          "Republic of Ireland",
    "Sao Tome and Principe":    "São Tomé and Príncipe",
    "São Tomé and Príncipe":    "São Tomé and Príncipe",
    "St. Lucia":                "Saint Lucia",
    "French Guyana":            "French Guiana",
    "US Virgin Islands":        "United States Virgin Islands",
    "andorra":                  "Andorra",
    "Chinese Taipei":           "Taiwan",
    "Mação":                    "Macau",
}

# Mapeamento tipo de estatistica -> coluna do pipeline
STAT_MAP = {
    "Total Shots":     "sb_shots",
    "Shots on Goal":   "sb_shots_on_target",
    "Corner Kicks":    "sb_corners",
    "Offsides":        "sb_offsides",
    "Yellow Cards":    "sb_yellow",
    "Red Cards":       "sb_red",
    "Fouls":           "sb_fouls",
    "Ball Possession": "sb_possession",
}

OUTPUT_COLS = [
    "date", "team", "opponent", "is_home", "competition", "season",
    "sb_shots", "sb_shots_on_target", "sb_corners", "sb_offsides",
    "sb_yellow", "sb_red", "sb_cards", "sb_fouls", "sb_possession",
]


def _norm_value(value):
    """Converte None->0 e '78%'->78.0 (Ball Possession)."""
    if value is None:
        return 0
    if isinstance(value, str) and value.endswith("%"):
        try:
            return float(value[:-1])
        except ValueError:
            return 0
    return value


def normalize_team(name):
    return TEAM_NAME_MAP.get(name, name)


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"fetched_fixture_ids": [], "total_reqs_all_time": 0}


def save_progress(progress):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def cache_path(fixture_id):
    return CACHE_DIR / f"{fixture_id}.json"


def load_from_cache(fixture_id):
    p = cache_path(fixture_id)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_to_cache(fixture_id, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path(fixture_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def make_request(session, endpoint, params):
    """Faz GET e retorna JSON ou None em caso de erro."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"   [ERRO] {url} params={params}: {e}")
        return None


def parse_statistics(stat_data, fixture_meta):
    """
    Converte resposta de /fixtures/statistics em 2 linhas (uma por time).
    Retorna lista de dicts no formato OUTPUT_COLS.
    """
    rows = []
    teams_data = stat_data.get("response", [])
    if len(teams_data) < 2:
        return rows

    date        = fixture_meta["date"][:10]
    competition = fixture_meta["league_name"]
    season      = fixture_meta["season"]
    home_name   = normalize_team(fixture_meta["home_team"])
    away_name   = normalize_team(fixture_meta["away_team"])

    for team_entry in teams_data:
        raw_name  = team_entry["team"]["name"]
        team_name = normalize_team(raw_name)
        is_home   = int(team_name == home_name)
        opponent  = away_name if is_home else home_name

        stats = {
            s["type"]: _norm_value(s["value"])
            for s in team_entry.get("statistics", [])
        }

        row = {
            "date":        date,
            "team":        team_name,
            "opponent":    opponent,
            "is_home":     is_home,
            "competition": competition,
            "season":      season,
        }
        for api_type, col in STAT_MAP.items():
            v = stats.get(api_type, 0)
            row[col] = float(v) if v is not None else 0.0

        row["sb_cards"] = row["sb_yellow"] + row["sb_red"]
        rows.append(row)

    return rows


def main():
    api_key = os.environ.get("APIFOOTBALL_KEY", "").strip()
    if not api_key:
        print("[ERRO] Variavel de ambiente APIFOOTBALL_KEY nao definida.")
        print("       PowerShell: $env:APIFOOTBALL_KEY='<sua_chave>'")
        print("       Linux/macOS: export APIFOOTBALL_KEY='<sua_chave>'")
        sys.exit(1)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    progress       = load_progress()
    fetched_ids    = set(int(x) for x in progress.get("fetched_fixture_ids", []))
    reqs_this_exec = 0
    new_downloaded = 0
    from_cache     = 0
    all_stat_rows  = []

    session = requests.Session()
    session.headers.update({"x-apisports-key": api_key})

    # Passo 1: listar fixtures para cada temporada
    all_fixtures = []

    for season in SEASONS:
        if reqs_this_exec >= MAX_REQS_EXEC:
            print(f"[LIMITE] {MAX_REQS_EXEC} req atingidas — abortando listagem.")
            break

        print(f"\n>> Buscando fixtures Copa {season} (league={LEAGUE})...")
        data = make_request(session, "fixtures",
                            {"league": LEAGUE, "season": season})
        reqs_this_exec += 1
        time.sleep(SLEEP_BETWEEN)

        if not data:
            print(f"   Nao foi possivel listar fixtures de {season}.")
            continue

        total_resp = len(data.get("response", []))
        ft_list = []
        for fx in data.get("response", []):
            # So jogos finalizados — filtrar antes de gastar cota em stats
            status_short = fx["fixture"]["status"]["short"]
            if status_short != "FT":
                continue

            ft_list.append({
                "fixture_id":  fx["fixture"]["id"],
                "date":        fx["fixture"]["date"],
                "league_name": fx["league"]["name"],
                "season":      fx["league"]["season"],
                "home_team":   fx["teams"]["home"]["name"],
                "away_team":   fx["teams"]["away"]["name"],
                "home_goals":  fx["goals"]["home"],
                "away_goals":  fx["goals"]["away"],
            })

        print(f"   Total na resposta: {total_resp} | Finalizados (FT): {len(ft_list)}")
        all_fixtures.extend(ft_list)

    already_cached = sum(1 for f in all_fixtures if f["fixture_id"] in fetched_ids)
    pending        = len(all_fixtures) - already_cached
    reqs_remaining = MAX_REQS_EXEC - reqs_this_exec

    print(f"\n>> Total FT: {len(all_fixtures)} | Em cache: {already_cached} | Pendentes: {pending}")
    print(f"   Req. disponiveis para stats nesta execucao: {reqs_remaining}")

    # Passo 2: coletar estatisticas
    for fx in all_fixtures:
        fid = fx["fixture_id"]

        # Cache primeiro
        cached_data = load_from_cache(fid)
        if cached_data is not None and fid in fetched_ids:
            rows = parse_statistics(cached_data, fx)
            all_stat_rows.extend(rows)
            from_cache += 1
            continue

        if reqs_this_exec >= MAX_REQS_EXEC:
            print(f"\n[LIMITE] {MAX_REQS_EXEC} req atingidas. Parou aqui.")
            print(f"   Execute novamente para continuar ({pending - new_downloaded} pendentes).")
            break

        home_n = normalize_team(fx["home_team"])
        away_n = normalize_team(fx["away_team"])
        print(f"   [{reqs_this_exec + 1}/{MAX_REQS_EXEC}] Stats {fid}: "
              f"{home_n} x {away_n} ({fx['date'][:10]})", end=" ... ")
        sys.stdout.flush()

        stat_data = make_request(session, "fixtures/statistics", {"fixture": fid})
        reqs_this_exec += 1
        time.sleep(SLEEP_BETWEEN)

        if stat_data and stat_data.get("response"):
            save_to_cache(fid, stat_data)
            fetched_ids.add(fid)
            rows = parse_statistics(stat_data, fx)
            all_stat_rows.extend(rows)
            new_downloaded += 1
            print(f"OK ({len(rows)} linhas)")
        else:
            print("sem dados (response vazio)")

    # Passo 3: salvar CSV
    if all_stat_rows:
        df_new = pd.DataFrame(all_stat_rows, columns=OUTPUT_COLS)

        if Path(OUTPUT_CSV).exists():
            df_old = pd.read_csv(OUTPUT_CSV)
            df_combined = (
                pd.concat([df_old, df_new], ignore_index=True)
                .drop_duplicates(subset=["date", "team"])
                .sort_values(["date", "team"])
                .reset_index(drop=True)
            )
        else:
            df_combined = df_new.sort_values(["date", "team"]).reset_index(drop=True)

        df_combined.to_csv(OUTPUT_CSV, index=False)
        
        # Salvar no Banco de Dados
        try:
            from app.db.connection import engine, truncate_and_append
            print(f"\n>> Salvando na tabela 'apifootball_match_team_stats' no banco de dados...")
            truncate_and_append(df_combined, "apifootball_match_team_stats", engine)
            print(f"   Salvo com sucesso: {len(df_combined)} linhas")
        except Exception as e:
            print(f"\n[ERRO] Falha ao salvar no banco de dados: {e}")

        n_matches = len(df_combined) // 2
        print(f"\n>> CSV salvo: {OUTPUT_CSV}")
        print(f"   {len(df_combined)} linhas (~{n_matches} partidas)")
    else:
        print("\n>> Nenhuma linha nova para salvar.")

    # Salvar progresso
    progress["fetched_fixture_ids"] = sorted(int(x) for x in fetched_ids)
    progress["total_reqs_all_time"] = progress.get("total_reqs_all_time", 0) + reqs_this_exec
    save_progress(progress)

    # Relatorio final
    req_restantes_est = max(0, 100 - reqs_this_exec)
    print("\n" + "=" * 60)
    print(f"  Requisicoes nesta execucao   : {reqs_this_exec}")
    print(f"  Jogos novos baixados         : {new_downloaded}")
    print(f"  Jogos servidos do cache      : {from_cache}")
    print(f"  Req. restantes (estimativa)  : ~{req_restantes_est} de 100/dia")
    print("=" * 60)

    # Gravar timestamp de atualização com sucesso
    import datetime
    last_update_path = Path("data/state/last_update.json")
    last_update_path.parent.mkdir(parents=True, exist_ok=True)
    with open(last_update_path, "w", encoding="utf-8") as f:
        json.dump({"last_successful_run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)


if __name__ == "__main__":
    main()
