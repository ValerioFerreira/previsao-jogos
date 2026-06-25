import json

def get_average_matches(league_id, name):
    name_lower = name.lower()
    if league_id == 1: # World Cup
        return 64
    if league_id == 10: # Friendlies
        return 600
    if "qualification" in name_lower or "qualifying" in name_lower:
        return 120
    if "nations league" in name_lower:
        if "uefa" in name_lower:
            return 140
        return 80
    if league_id in [4, 6, 7, 9, 22]: # Euro, Africa Cup, Asian Cup, Copa America, Gold Cup
        return 32 if league_id == 9 else 51
    if "cup" in name_lower:
        return 20
    return 30

def main():
    with open("data/raw/discovered_leagues_raw.json", "r", encoding="utf-8") as f:
        leagues = json.load(f)
        
    explicit_ids = {
        1: "World Cup",
        29: "World Cup - Qualification Africa",
        30: "World Cup - Qualification Asia",
        31: "World Cup - Qualification CONCACAF",
        32: "World Cup - Qualification Europe",
        33: "World Cup - Qualification Oceania",
        34: "World Cup - Qualification South America",
        37: "World Cup - Qualification Intercontinental Play-offs",
        4: "Euro Championship",
        960: "Euro Championship - Qualification",
        9: "Copa America",
        6: "Africa Cup of Nations",
        36: "Africa Cup of Nations - Qualification",
        7: "Asian Cup",
        35: "Asian Cup - Qualification",
        22: "CONCACAF Gold Cup",
        858: "CONCACAF Gold Cup - Qualification",
        5: "UEFA Nations League",
        536: "CONCACAF Nations League",
        21: "Confederations Cup",
        913: "CONMEBOL - UEFA Finalissima",
        860: "Arab Cup",
        25: "Gulf Cup of Nations",
        1008: "CAFA Nations Cup",
        10: "Friendlies",
        1222: "FIFA Series"
    }

    exclude_keywords = [
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
    
    discovered_selection_leagues = []
    
    for item in leagues:
        l = item["league"]
        c = item["country"]
        l_name = l["name"]
        
        # We only want World country
        if c["name"].lower() != "world":
            continue
            
        if l["id"] in [19, 1163]:
            continue
            
        # Check exclusion keywords
        l_name_lower = l_name.lower()
        excluded = False
        for kw in exclude_keywords:
            if kw in l_name_lower:
                excluded = True
                break
        if excluded:
            continue
            
        # Filter seasons >= 2016
        seasons_ge_2016 = [s for s in item["seasons"] if s["year"] >= 2016]
        if not seasons_ge_2016:
            continue
            
        discovered_selection_leagues.append({
            "id": l["id"],
            "name": l_name,
            "type": l["type"],
            "seasons": sorted([s["year"] for s in seasons_ge_2016])
        })
        
    print("================================================================================")
    print("FASE 1: DESCOBERTA E FILTRAGEM DE LIGAS (World country, Masculinas Adultas)")
    print("================================================================================")
    print(f"Total de ligas descobertas: {len(discovered_selection_leagues)}\n")
    
    discovered_ids = {item["id"] for item in discovered_selection_leagues}
    
    total_estimated_reqs = 0
    
    print("Lista de Competições Descobertas e Estimativa:")
    print("| ID | Nome da Competição | Temporadas (2016+) | Est. Partidas/Seas | Est. Reqs |")
    print("|---|---|---|---|---|")
    for item in sorted(discovered_selection_leagues, key=lambda x: x["name"]):
        n_seasons = len(item["seasons"])
        avg_matches = get_average_matches(item["id"], item["name"])
        reqs_for_league = n_seasons * (1 + avg_matches)
        total_estimated_reqs += reqs_for_league
        
        seasons_str = ", ".join(map(str, item["seasons"]))
        print(f"| {item['id']:4d} | {item['name']:<50} | {seasons_str:<30} | {avg_matches:3d} | {reqs_for_league:4d} |")
        
    print("\n--------------------------------------------------------------------------------")
    print("COMPETIÇÕES EXPLÍCITAS DO CONTEXTO:")
    print("--------------------------------------------------------------------------------")
    print("Verificando se todas as competições explícitas foram descobertas:")
    not_discovered = []
    for exp_id, exp_name in explicit_ids.items():
        if exp_id in discovered_ids:
            print(f"  [OK] ID {exp_id:4d} : {exp_name}")
        else:
            not_discovered.append((exp_id, exp_name))
            print(f"  [MISSING] ID {exp_id:4d} : {exp_name}")
            
    if not_discovered:
        print("\nATENÇÃO: As seguintes competições explícitas do contexto NÃO foram descobertas pelos filtros:")
        for exp_id, exp_name in not_discovered:
            found_raw = False
            for item in leagues:
                if item["league"]["id"] == exp_id:
                    print(f"    Encontrado no raw, mas excluído! Nome: {item['league']['name']}, Country: {item['country']['name']}, Seasons: {[s['year'] for s in item['seasons']]}")
                    found_raw = True
                    break
            if not found_raw:
                print(f"    ID {exp_id} ({exp_name}) NÃO existe no arquivo raw de ligas!")
                
    print(f"\nESTIMATIVA TOTAL DE REQUISIÇÕES: {total_estimated_reqs} requests.")

if __name__ == "__main__":
    main()
