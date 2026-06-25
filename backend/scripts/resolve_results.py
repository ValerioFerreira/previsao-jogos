#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/resolve_results.py
==========================
Script de resolução assíncrona para o histórico de acertos do modelo.
Compara previsões salvas no predictions_log.jsonl com os resultados reais em matches.parquet,
calcula as estatísticas de acerto e gera data/state/model_accuracy.json para exibição na UI.
"""
import os
import json
from pathlib import Path
import pandas as pd
import numpy as np


def main():
    print("=" * 80)
    print(" RESOLUÇÃO DE RESULTADOS — Histórico de Acerto do Modelo")
    print("=" * 80)

    repo_root = Path(__file__).resolve().parents[1]
    log_file = repo_root / "data" / "state" / "predictions_log.jsonl"
    parquet_file = repo_root / "data" / "built" / "matches.parquet"
    out_file = repo_root / "data" / "state" / "model_accuracy.json"

    if not log_file.exists():
        print(f"Log de previsões não encontrado em: {log_file}")
        # Criar arquivo de estatísticas vazio padrão
        stats_empty = {
            "total_evaluated": 0,
            "markets": {
                "vencedor": {"total": 0, "acertos": 0, "taxa": 0.0},
                "over_2_5": {"total": 0, "acertos": 0, "taxa": 0.0},
                "ambas_marcam": {"total": 0, "acertos": 0, "taxa": 0.0}
            }
        }
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(stats_empty, f, indent=2)
        return

    if not parquet_file.exists():
        print(f"Arquivo parquet de partidas não encontrado em: {parquet_file}")
        return

    # 1. Carregar matches.parquet
    print("Carregando banco de partidas...")
    df_matches = pd.read_parquet(parquet_file)
    
    # As partidas no parquet são duplicadas por time/opponent. Vamos deduplicar obtendo registros unificados.
    # Criamos um conjunto de partidas com chaves (date, home_team, away_team) e o resultado real
    real_results = {}
    for _, row in df_matches.iterrows():
        date_str = str(row["date"])
        team = str(row["team"])
        opponent = str(row["opponent"])
        is_home = row["is_home"] == 1
        
        # Identificar home/away para unificar
        if is_home:
            home = team
            away = opponent
            home_goals = int(row["goals_scored"])
            away_goals = int(row["goals_conceded"])
        else:
            home = opponent
            away = team
            home_goals = int(row["goals_conceded"])
            away_goals = int(row["goals_scored"])
            
        key = (date_str, home, away)
        # Salva o resultado consolidado
        real_results[key] = {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "winner": home if home_goals > away_goals else (away if away_goals > home_goals else "Empate"),
            "over_2_5": (home_goals + away_goals) > 2.5,
            "btts": home_goals > 0 and away_goals > 0
        }

    # 2. Ler predictions_log.jsonl
    print("Processando log de previsões...")
    evaluated = 0
    markets_count = {
        "vencedor": {"total": 0, "acertos": 0},
        "over_2_5": {"total": 0, "acertos": 0},
        "ambas_marcam": {"total": 0, "acertos": 0}
    }

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                home_team = entry.get("home_team")
                away_team = entry.get("away_team")
                pred = entry.get("prediction")
                
                if not (home_team and away_team and pred):
                    continue
                
                # Procurar o resultado no banco real
                # Como a previsão pode ser para uma data futura que já passou, procuramos partidas correspondentes
                match_result = None
                for (d_str, h, a), res in real_results.items():
                    # Ignorar previsões de amistoso se jogado em outra data, mas geralmente buscamos por nomes das seleções
                    # Para simplificar, pareamos pelo confronto (home, away) onde o resultado real existe
                    if h == home_team and a == away_team:
                        match_result = res
                        break
                
                if not match_result:
                    continue  # Partida prevista ainda não ocorreu ou não está no parquet
                
                evaluated += 1
                
                # --- A. Validar Vencedor ---
                p_venc = pred.get("vencedor", {})
                winner_pred = p_venc.get("vencedor")
                actual_winner = match_result["winner"]
                if winner_pred and actual_winner:
                    markets_count["vencedor"]["total"] += 1
                    if winner_pred == actual_winner:
                        markets_count["vencedor"]["acertos"] += 1
                        
                # --- B. Validar Over 2.5 ---
                p_over = pred.get("over_2_5", {})
                over_pred_str = p_over.get("resposta") # "Mais de 2,5" ou "Menos de 2,5"
                actual_over = match_result["over_2_5"]
                if over_pred_str:
                    is_over_pred = "Mais" in over_pred_str
                    markets_count["over_2_5"]["total"] += 1
                    if is_over_pred == actual_over:
                        markets_count["over_2_5"]["acertos"] += 1
                        
                # --- C. Validar BTTS ---
                p_btts = pred.get("ambas_marcam", {})
                btts_pred_str = p_btts.get("resposta") # "Sim" ou "Não"
                actual_btts = match_result["btts"]
                if btts_pred_str:
                    is_btts_pred = "Sim" in btts_pred_str
                    markets_count["ambas_marcam"]["total"] += 1
                    if is_btts_pred == actual_btts:
                        markets_count["ambas_marcam"]["acertos"] += 1
                        
            except Exception as e:
                print(f"Erro ao ler linha do log: {e}")

    # 3. Calcular taxas
    stats = {
        "total_evaluated": evaluated,
        "markets": {}
    }
    for m, vals in markets_count.items():
        tot = vals["total"]
        ac = vals["acertos"]
        rate = float(ac / tot) if tot > 0 else 0.0
        stats["markets"][m] = {
            "total": tot,
            "acertos": ac,
            "taxa": round(rate * 100, 1)
        }

    # 4. Salvar compilado estatístico
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
        
    print(f"\n>> Resolução concluída!")
    print(f"   Partidas avaliadas: {evaluated}")
    print(f"   Taxa Vencedor     : {stats['markets']['vencedor']['taxa']}% ({stats['markets']['vencedor']['acertos']}/{stats['markets']['vencedor']['total']})")
    print(f"   Taxa Over 2.5     : {stats['markets']['over_2_5']['taxa']}% ({stats['markets']['over_2_5']['acertos']}/{stats['markets']['over_2_5']['total']})")
    print(f"   Taxa Ambas Marcam : {stats['markets']['ambas_marcam']['taxa']}% ({stats['markets']['ambas_marcam']['acertos']}/{stats['markets']['ambas_marcam']['total']})")
    print(f"   Salvo em: {out_file}")


if __name__ == "__main__":
    main()
