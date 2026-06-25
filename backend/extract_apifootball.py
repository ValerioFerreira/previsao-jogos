import requests
import json
import time

API_KEY = "515dac49287f85774d532f095815e90c"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {
    'x-apisports-key': API_KEY
}

def make_request(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    print(f"Requesting: {url} with params {params}")
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        time.sleep(1) # Rate limit protection (usually 10/sec, but better safe)
        return response.json()
    except Exception as e:
        print(f"Error fetching {endpoint}: {e}")
        try:
            return response.json()
        except:
            return None

all_data = {}

# Passo 1: Obter Informações de Configuração e Metadados
print("Step 1...")
all_data["timezone"] = make_request("/timezone")
all_data["countries"] = make_request("/countries")
all_data["leagues_seasons"] = make_request("/leagues/seasons")

# Passo 2: Identificar uma Partida de Referência (Exemplo: Premier League)
print("Step 2...")
# First try season=2025, if no results, try 2024 (as 2024/2025 is the current real-world season)
league_id = 39
season_id = 2024

leagues_res = make_request("/leagues", {"id": league_id, "season": season_id})
if not leagues_res.get('response'):
    print("No league info for 2024. Trying 2025...")
    season_id = 2025
    leagues_res = make_request("/leagues", {"id": league_id, "season": season_id})
all_data["leagues"] = leagues_res

fixtures_res = make_request("/fixtures", {"league": league_id, "season": season_id, "last": 1})
all_data["fixtures_last_1"] = fixtures_res

fixture_id = None
home_team_id = None
away_team_id = None
venue_id = None

if fixtures_res and fixtures_res.get('response'):
    fixture_data = fixtures_res['response'][0]
    fixture_id = fixture_data['fixture']['id']
    home_team_id = fixture_data['teams']['home']['id']
    away_team_id = fixture_data['teams']['away']['id']
    venue_id = fixture_data['fixture']['venue']['id']
    print(f"Found fixture_id: {fixture_id}, home: {home_team_id}, away: {away_team_id}, venue: {venue_id}")

if fixture_id:
    # Passo 3: Extrair Dados Detalhados da Partida de Referência
    print("Step 3...")
    all_data["fixtures_statistics"] = make_request("/fixtures/statistics", {"fixture": fixture_id})
    events_res = make_request("/fixtures/events", {"fixture": fixture_id})
    all_data["fixtures_events"] = events_res
    
    lineups_res = make_request("/fixtures/lineups", {"fixture": fixture_id})
    all_data["fixtures_lineups"] = lineups_res
    
    players_res = make_request("/fixtures/players", {"fixture": fixture_id})
    all_data["fixtures_players"] = players_res
    
    # Identify some player IDs for step 4
    player_ids = set()
    if lineups_res and lineups_res.get('response'):
        for team_lineup in lineups_res['response']:
            for p in team_lineup.get('startXI', []):
                if p.get('player') and p['player'].get('id'):
                    player_ids.add(p['player']['id'])
            for p in team_lineup.get('substitutes', []):
                if p.get('player') and p['player'].get('id'):
                    player_ids.add(p['player']['id'])
                    
    # Cap players to 2 to save requests for the example (the prompt says to have at least one occurrence of each data type)
    player_ids_list = list(player_ids)[:2]
    
    # Identify a coach
    coach_id = None
    coach_name = None
    if lineups_res and lineups_res.get('response'):
        coach = lineups_res['response'][0].get('coach')
        if coach:
            coach_id = coach.get('id')
            coach_name = coach.get('name')

    # Passo 4: Extrair Dados Detalhados de Times e Jogadores Envolvidos
    print("Step 4...")
    all_data["teams_home"] = make_request("/teams", {"id": home_team_id})
    all_data["teams_away"] = make_request("/teams", {"id": away_team_id})
    
    all_data["teams_statistics_home"] = make_request("/teams/statistics", {"league": league_id, "season": season_id, "team": home_team_id})
    all_data["teams_statistics_away"] = make_request("/teams/statistics", {"league": league_id, "season": season_id, "team": away_team_id})
    
    all_data["players_squads_home"] = make_request("/players/squads", {"team": home_team_id})
    all_data["players_squads_away"] = make_request("/players/squads", {"team": away_team_id})
    
    all_data["players_details"] = []
    for pid in player_ids_list:
        all_data["players_details"].append(make_request("/players", {"id": pid, "season": season_id}))
        
    # Passo 5: Extrair Dados da Liga e Líderes
    print("Step 5...")
    all_data["standings"] = make_request("/standings", {"league": league_id, "season": season_id})
    all_data["topscorers"] = make_request("/players/topscorers", {"league": league_id, "season": season_id})
    all_data["topassists"] = make_request("/players/topassists", {"league": league_id, "season": season_id})
    all_data["topyellowcards"] = make_request("/players/topyellowcards", {"league": league_id, "season": season_id})
    all_data["topredcards"] = make_request("/players/topredcards", {"league": league_id, "season": season_id})
    
    # Passo 6: Outros Dados Relevantes
    print("Step 6...")
    all_data["injuries"] = make_request("/injuries", {"fixture": fixture_id})
    all_data["predictions"] = make_request("/predictions", {"fixture": fixture_id})
    all_data["odds"] = make_request("/odds", {"fixture": fixture_id})
    
    if home_team_id:
        all_data["coachs"] = make_request("/coachs", {"team": home_team_id})
    elif coach_name:
        all_data["coachs"] = make_request("/coachs", {"search": coach_name})
        
    if venue_id:
        all_data["venues"] = make_request("/venues", {"id": venue_id})
        
    if player_ids_list:
        all_data["trophies"] = make_request("/trophies", {"player": player_ids_list[0]})
        all_data["sidelined"] = make_request("/sidelined", {"player": player_ids_list[0]})
        
else:
    print("Failed to find a fixture to proceed with steps 3-6.")

# Output to JSON
out_file = "api_football_data_extraction.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

print(f"Data extraction complete. Saved to {out_file}")
