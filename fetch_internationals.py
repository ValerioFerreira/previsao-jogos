#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_internationals.py
=======================
Coletor de dados históricos de seleções masculinas adultas via API-Football.

Uso:
    Fase 1 (Descoberta e Estimativa):
        python fetch_internationals.py --fase1
        
    Fase 2 (Download em massa):
        python fetch_internationals.py --fase2

Requer variável de ambiente APIFOOTBALL_KEY (carregada via .env se disponível).
"""

import os
import sys
import json
import time
import gzip
import argparse
from pathlib import Path
import requests

# Constantes de Arquitetura
BASE_URL = "https://v3.football.api-sports.io"
DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
FIXTURES_DIR = RAW_DIR / "fixtures"
LISTS_DIR = RAW_DIR / "fixtures_list"
STATE_DIR = DATA_DIR / "state"
PROGRESS_FILE = STATE_DIR / "progress.json"

# Garantir a criação das pastas
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
LISTS_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Limiares de Rate Limit e Segurança
SAFE_REMAINING_MIN = 5   # Pausar se sobrar < 5 reqs no minuto
SAFE_REMAINING_DAY = 500 # Parar a execução se sobrar <= 500 reqs no dia
MIN_SLEEP_MS = 150       # Delay anti-rajada (~6.6 reqs/segundo)

# Filtros de Torneio (Feminino/Base/Olímpico/Clubes)
EXCLUDE_KEYWORDS = [
    "women", "femenina", "u17", "u19", "u20", "u21", "u23", "youth", "under", "under-",
    "olympic", "olympics", "pre-olympic", "club", "champions league", "europa league", 
    "conference league", "libertadores", "sudamericana", "recopa", "clash", "supercup", 
    "super cup", "super shield", "pro league", "challenge league", "emirates cup", "cotif", 
    "champions cup", "confederation cup", "all-island", "carling cup", "leagues cup", 
    "campeones cup", "concacaf league", "central american cup", "premier league", 
    "rio de la plata", "tipsport", "atlantic cup", "algarve cup", "shebelieves cup", 
    "maurice revello", "kings world cup", "games", "asian games", "pan american games", 
    "african games", "olympic games", "african football league", "intercontinental cup"
]

def load_env():
    """Carrega .env se existir, sem depender de pacotes externos."""
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

def get_headers():
    """Retorna os headers de autenticação."""
    load_env()
    key = os.environ.get("APIFOOTBALL_KEY")
    if not key:
        print("[ERRO] Variável de ambiente APIFOOTBALL_KEY não encontrada!")
        print("Crie um arquivo .env na raiz do projeto contendo: APIFOOTBALL_KEY=sua_chave")
        sys.exit(1)
    return {"x-apisports-key": key}

def get_average_matches(league_id, name):
    """Estima quantidade de partidas de uma liga-temporada para cálculo de cota."""
    name_lower = name.lower()
    if league_id == 1: return 64
    if league_id == 10: return 600
    if "qualification" in name_lower or "qualifying" in name_lower: return 120
    if "nations league" in name_lower:
        return 140 if "uefa" in name_lower else 80
    if league_id in [4, 6, 7, 9, 22]: return 32 if league_id == 9 else 51
    if "cup" in name_lower: return 20
    return 30

def fetch_leagues_list():
    """Obtém a lista de todas as ligas (com cache local offline)."""
    cache_path = RAW_DIR / "discovered_leagues_raw.json"
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
            
    print(">> Buscando lista completa de ligas via API...")
    headers = get_headers()
    res = requests.get(f"{BASE_URL}/leagues", headers=headers)
    if res.status_code != 200:
        print(f"[ERRO] Falha ao consultar /leagues: {res.status_code} - {res.text}")
        sys.exit(1)
        
    leagues = res.json().get("response", [])
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(leagues, f, ensure_ascii=False, indent=2)
    print(f"   Salvo em cache: {cache_path}")
    return leagues

def discover_target_leagues(leagues_raw):
    """Filtra ligas de seleções adultas masculinas >= 2016."""
    targets = []
    for item in leagues_raw:
        l = item["league"]
        c = item["country"]
        l_name = l["name"]
        
        # Apenas país 'World'
        if c["name"].lower() != "world":
            continue
            # Excluir CHAN (ids 19 e 1163)
        if l["id"] in [19, 1163]:
            continue
            
        # Aplicar exclusões
        l_name_lower = l_name.lower()
        if any(kw in l_name_lower for kw in EXCLUDE_KEYWORDS):
            continue
            
        # Filtrar temporadas >= 2016
        seasons_ge_2016 = [s for s in item["seasons"] if s["year"] >= 2016]
        if not seasons_ge_2016:
            continue
            
        targets.append({
            "id": l["id"],
            "name": l_name,
            "seasons": sorted([s["year"] for s in seasons_ge_2016])
        })
    return sorted(targets, key=lambda x: x["name"])

class RateLimiter:
    """Controlador inteligente de ritmo e cota baseado nos headers da API."""
    def __init__(self):
        self.reqs_this_exec = 0
        self.remaining_min = 450
        self.remaining_day = 75000
        self.min_limit = 450
        self.day_limit = 75000
        self.last_req_time = 0.0
        
    def throttle(self):
        """Impõe intervalo mínimo anti-rajada."""
        now = time.time()
        elapsed = (now - self.last_req_time) * 1000
        if elapsed < MIN_SLEEP_MS:
            time.sleep((MIN_SLEEP_MS - elapsed) / 1000.0)
        self.last_req_time = time.time()
        
    def update_limits(self, headers):
        """Atualiza cotas a partir dos headers HTTP."""
        self.reqs_this_exec += 1
        
        # Cota Diária
        try:
            self.remaining_day = int(headers.get("x-ratelimit-requests-remaining", self.remaining_day))
            self.day_limit = int(headers.get("x-ratelimit-requests-limit", self.day_limit))
        except ValueError:
            pass
            
        # Cota por Minuto
        try:
            self.remaining_min = int(headers.get("X-RateLimit-Remaining", self.remaining_min))
            self.min_limit = int(headers.get("X-RateLimit-Limit", self.min_limit))
        except ValueError:
            pass
            
    def check_and_wait(self):
        """Verifica limites e aguarda/pausa se necessário."""
        # Verificar cota diária
        if self.remaining_day <= SAFE_REMAINING_DAY:
            print(f"\n[RATE-LIMIT] Limite de segurança diário atingido ({self.remaining_day} restantes). Encerrando execution.")
            return False
            
        # Verificar cota por minuto
        if self.remaining_min < SAFE_REMAINING_MIN:
            print(f"\n[RATE-LIMIT] Limite por minuto quase atingido ({self.remaining_min} restante). Pausando por 60 segundos...")
            time.sleep(60.0)
            self.remaining_min = self.min_limit # reset estimado
            
        return True

def run_fase1():
    """Fase 1: descobre ligas e calcula estimativa de requisições."""
    leagues_raw = fetch_leagues_list()
    targets = discover_target_leagues(leagues_raw)
    
    total_est = 0
    print("\n" + "=" * 80)
    print("LISTA-ALVO DE COMPETIÇÕES (FASE 1)")
    print("=" * 80)
    print("| ID | Competição | Temporadas (2016+) | Est. Partidas | Est. Reqs |")
    print("|---|---|---|---|---|")
    for item in targets:
        n_seasons = len(item["seasons"])
        avg_m = get_average_matches(item["id"], item["name"])
        reqs = n_seasons * (1 + avg_m)
        total_est += reqs
        seasons_str = ", ".join(map(str, item["seasons"]))
        print(f"| {item['id']:4d} | {item['name']:<40} | {seasons_str:<18} | {avg_m:13d} | {reqs:9d} |")
        
    print("-" * 80)
    print(f"Total de Ligas: {len(targets)}")
    print(f"Estimativa Total de Requisições: {total_est} requests (Carga Inicial Máxima).")
    print("=" * 80)

def run_fase2():
    """Fase 2: download em massa com cache, controle de retomada e rate limits."""
    headers = get_headers()
    leagues_raw = fetch_leagues_list()
    targets = discover_target_leagues(leagues_raw)
    
    # Carregar progresso
    progress = {}
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress = json.load(f)
        except Exception:
            pass
            
    limiter = RateLimiter()
    stats_downloaded = 0
    stats_cached = 0
    
    print("\n" + "=" * 80)
    print("INICIANDO FASE 2: COLETA DE DADOS HISTÓRICOS")
    print("=" * 80)
    
    # Processar da temporada mais recente para a mais antiga
    # Primeiro listamos todas as (league_id, name, season) e ordenamos descrescente por season
    jobs = []
    for item in targets:
        for s in item["seasons"]:
            jobs.append((s, item["id"], item["name"]))
    jobs.sort(key=lambda x: x[0], reverse=True)
    
    for season, league_id, name in jobs:
        job_key = f"{league_id}_{season}"
        
        # Retomada: Pular se temporada estiver fechada
        if progress.get(job_key) == "completed":
            stats_cached += 1 # aproximado
            continue
            
        print(f"\n>> Processando: {name} (ID: {league_id}) | Temp: {season}...")
        
        # 1. Obter lista de fixtures
        list_file = LISTS_DIR / f"{league_id}_{season}.json"
        fixtures_list = []
        
        if list_file.exists():
            with open(list_file, "r", encoding="utf-8") as f:
                fixtures_list = json.load(f)
        else:
            if not limiter.check_and_wait(): break
            limiter.throttle()
            
            res = requests.get(f"{BASE_URL}/fixtures", headers=headers, params={"league": league_id, "season": season})
            limiter.update_limits(res.headers)
            
            if res.status_code == 200:
                fixtures_list = res.json().get("response", [])
                with open(list_file, "w", encoding="utf-8") as f:
                    json.dump(fixtures_list, f, ensure_ascii=False, indent=2)
            elif res.status_code == 429:
                print("[RATE-LIMIT] HTTP 429 recebido. Aguardando 60 segundos...")
                time.sleep(60)
                continue
            else:
                print(f"   [AVISO] Erro ao listar fixtures ({res.status_code}): {res.text}")
                continue
                
        # 2. Filtrar finalizados e garantir apenas seleções adultas masculinas
        finished_fixtures = []
        for f in fixtures_list:
            if f.get("fixture", {}).get("status", {}).get("short") not in ["FT", "AET", "PEN"]:
                continue
            
            # Checar times para excluir feminino, base (U15-U23), olímpico ou clubes óbvios
            teams = f.get("teams", {})
            home = teams.get("home", {}).get("name", "")
            away = teams.get("away", {}).get("name", "")
            home_l = home.lower()
            away_l = away.lower()
            
            team_exclude_kws = [
                "women", "femenina", "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u22", "u23", 
                "youth", "under", "under-", "olympic", "olympics", "pre-olympic", "b team", "select xi",
                "all stars", "all-stars", "stars xi", "chapecoense"
            ]
            
            if any(kw in home_l or kw in away_l for kw in team_exclude_kws):
                continue
                
            finished_fixtures.append(f)
        print(f"   Partidas finalizadas: {len(finished_fixtures)} (total: {len(fixtures_list)})")
        
        # 3. Baixar fixtures individuais
        season_completed = True
        for f_data in finished_fixtures:
            fid = f_data["fixture"]["id"]
            
            # Caminho do cache cru
            league_path = FIXTURES_DIR / str(league_id) / str(season)
            league_path.mkdir(parents=True, exist_ok=True)
            match_file = league_path / f"{fid}.json.gz"
            
            if match_file.exists():
                stats_cached += 1
                continue
                
            # Limites e throttles
            if not limiter.check_and_wait():
                season_completed = False
                break
                
            limiter.throttle()
            
            print(f"   -> Baixando partida {fid} ({f_data['teams']['home']['name']} vs {f_data['teams']['away']['name']})...")
            m_res = requests.get(f"{BASE_URL}/fixtures", headers=headers, params={"id": fid})
            limiter.update_limits(m_res.headers)
            
            if m_res.status_code == 200:
                m_data = m_res.json().get("response", [])
                if m_data:
                    # Salvar em gzip
                    with gzip.open(match_file, "wt", encoding="utf-8") as gf:
                        json.dump(m_data[0], gf, ensure_ascii=False)
                    stats_downloaded += 1
                else:
                    print(f"      [AVISO] Resposta vazia para fixture {fid}")
            elif m_res.status_code == 429:
                print("      [RATE-LIMIT] HTTP 429 recebido. Pausando...")
                time.sleep(60)
                season_completed = False
                break
            else:
                print(f"      [AVISO] Falha ao baixar fixture {fid} ({m_res.status_code})")
                season_completed = False
                
        # Marcar progresso
        # Se for uma temporada futura ou atual (em andamento), fica ativa
        is_current = any(s["year"] == season and s.get("current", False) for item in leagues_raw for s in item["seasons"] if item["league"]["id"] == league_id)
        if season_completed and not is_current:
            progress[job_key] = "completed"
        else:
            progress[job_key] = "active"
            
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2)
            
        if limiter.remaining_day <= SAFE_REMAINING_DAY:
            break
            
    # Relatório Final
    print("\n" + "=" * 80)
    print("RELATÓRIO DE EXECUÇÃO (COLETA)")
    print("=" * 80)
    print(f"Requisições consumidas nesta execução: {limiter.reqs_this_exec}")
    print(f"Novas partidas baixadas e salvas:     {stats_downloaded}")
    print(f"Partidas encontradas no cache local:  {stats_cached}")
    print(f"Cota diária restante da conta:        {limiter.remaining_day} / {limiter.day_limit}")
    print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description="Coletor de Seleções Masculinas Adultas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fase1", action="store_true", help="Executa a Fase 1: Descoberta e Estimativa")
    group.add_argument("--fase2", action="store_true", help="Executa a Fase 2: Coleta efetiva de partidas")
    
    args = parser.parse_args()
    if args.fase1:
        run_fase1()
    elif args.fase2:
        run_fase2()

if __name__ == "__main__":
    main()
