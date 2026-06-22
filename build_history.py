#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_history.py
================
Consolida os arquivos de partidas salvos em cache (.json.gz) em:
  - data/built/historico_completo.json (JSON completo com bloco players)
  - data/built/matches.parquet (tabela estruturada de estatísticas avançadas)

Uso:
    python build_history.py
"""

import os
import json
import gzip
import pandas as pd
from pathlib import Path

# Constantes de Arquitetura
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
FIXTURES_DIR = RAW_DIR / "fixtures"
BUILT_DIR = DATA_DIR / "built"
OUTPUT_JSON = BUILT_DIR / "historico_completo.json"
OUTPUT_PARQUET = BUILT_DIR / "matches.parquet"

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

# Mapeamento de tipo de estatística -> coluna no DataFrame
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
}

def normalize_team(name):
    return TEAM_NAME_MAP.get(name, name)

def _norm_value(value):
    if value is None:
        return None
    if isinstance(value, str) and value.endswith("%"):
        try:
            return float(value[:-1])
        except ValueError:
            return None
    return value

def parse_match(match_data):
    """
    Extrai estatísticas tabulares da partida.
    Retorna uma lista de 2 dicionários (um para cada seleção).
    """
    rows = []
    
    # Metadados
    fixture_meta = match_data.get("fixture", {})
    league_meta = match_data.get("league", {})
    teams_meta = match_data.get("teams", {})
    
    date_str = fixture_meta.get("date", "")[:10]
    competition = league_meta.get("name", "")
    season = league_meta.get("season")
    
    home_name = normalize_team(teams_meta.get("home", {}).get("name", ""))
    away_name = normalize_team(teams_meta.get("away", {}).get("name", ""))
    
    home_score = match_data.get("goals", {}).get("home", None)
    away_score = match_data.get("goals", {}).get("away", None)
    
    statistics = match_data.get("statistics", [])
    if len(statistics) < 2:
        return rows
        
    for team_entry in statistics:
        raw_name = team_entry.get("team", {}).get("name", "")
        team_name = normalize_team(raw_name)
        is_home = int(team_name == home_name)
        opponent = away_name if is_home else home_name
        
        # Parse das estatísticas detalhadas
        stats = {
            s["type"]: _norm_value(s["value"])
            for s in team_entry.get("statistics", [])
            if s.get("type") is not None
        }
        
        row = {
            "date":        date_str,
            "team":        team_name,
            "opponent":    opponent,
            "is_home":     is_home,
            "competition": competition,
            "season":      season,
            "goals_scored": home_score if is_home else away_score,
            "goals_conceded": away_score if is_home else home_score,
        }
        
        for api_type, col in STAT_MAP.items():
            v = stats.get(api_type, None)
            row[col] = float(v) if v is not None else None
            
        y_val = row["sb_yellow"]
        r_val = row["sb_red"]
        if y_val is None and r_val is None:
            row["sb_cards"] = None
        else:
            y_val_clean = float(y_val) if y_val is not None else 0.0
            r_val_clean = float(r_val) if r_val is not None else 0.0
            row["sb_yellow"] = y_val_clean
            row["sb_red"] = r_val_clean
            row["sb_cards"] = y_val_clean + r_val_clean
            
        rows.append(row)
        
    return rows

def main():
    print("================================================================================")
    print("CONSOLIDAÇÃO HISTÓRICA (build_history.py)")
    print("================================================================================")
    
    BUILT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Encontrar todos os json.gz
    gz_files = list(FIXTURES_DIR.glob("**/*.json.gz"))
    print(f"Total de arquivos crus (.json.gz) encontrados: {len(gz_files)}")
    
    if not gz_files:
        print("[AVISO] Nenhum arquivo cru encontrado para consolidação. Execute o coletor primeiro.")
        return
        
    complete_history = []
    tabular_rows = []
    
    for i, path in enumerate(gz_files, start=1):
        if i % 100 == 0 or i == len(gz_files):
            print(f"   Processando: {i}/{len(gz_files)}...")
            
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                match_data = json.load(f)
                
            # Adicionar ao JSON histórico completo (preserva bloco players)
            complete_history.append(match_data)
            
            # Extrair linhas para o DataFrame tabular
            rows = parse_match(match_data)
            tabular_rows.extend(rows)
            
        except Exception as e:
            print(f"   [ERRO] Falha ao ler {path}: {e}")
            
    # 1. Salvar JSON Consolidado
    print(f"\n>> Gravando {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(complete_history, f, ensure_ascii=False)
    print(f"   Salvo: {len(complete_history)} partidas consolidadas no histórico completo.")
    
    # 2. Salvar Parquet Tabular
    if tabular_rows:
        df = pd.DataFrame(tabular_rows)
        print(f">> Gravando {OUTPUT_PARQUET} ({len(df)} linhas, {len(df.columns)} colunas)...")
        try:
            df.to_parquet(OUTPUT_PARQUET, index=False, engine="pyarrow")
            print("   Salvo com sucesso!")
        except ImportError:
            print("\n[ERRO] Pacote 'pyarrow' não instalado. Não foi possível gerar o arquivo matches.parquet.")
            print("       Instale o pyarrow rodando:")
            print("       api\\.venv\\Scripts\\pip.exe install pyarrow")
            print("\n       Salvando fallback temporário em data/built/matches.csv...")
            df.to_csv(BUILT_DIR / "matches.csv", index=False)
            print("       Salvo em data/built/matches.csv")
    else:
        print("[INFO] Nenhuma linha tabular pôde ser extraída (estatísticas vazias).")
        
    print("\n[CONCLUÍDO] Consolidação finalizada.")

if __name__ == "__main__":
    main()
