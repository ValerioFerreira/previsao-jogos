#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/anomaly_detector.py
=======================
Motor de detecção de anomalias (destaques automáticos) baseado em Z-Score OOS.
Calcula média e desvio-padrão históricos (últimos ~20 jogos de nível semelhante)
e avalia janelas curtas de 1 a 5 jogos para identificar comportamento fora da curva.
"""
import numpy as np
import pandas as pd
from pathlib import Path


def get_competition_weight(comp: str) -> float:
    """Retorna o peso estimado do torneio a partir do nome da competição."""
    comp_l = comp.lower()
    if "world cup" in comp_l and "qualification" not in comp_l and "play-off" not in comp_l:
        return 1.0
    if "qualification" in comp_l or "elimina" in comp_l:
        return 0.6
    if "nations league" in comp_l:
        return 0.7
    if "friendly" in comp_l or "amistoso" in comp_l:
        return 0.2
    # Copas Continentais
    if any(x in comp_l for x in ["copa america", "euro", "gold cup", "nations", "asian cup", "confederations"]):
        return 0.85
    return 0.40  # Default


def detect_anomalies(parquet_path: Path, team_name: str, target_competition: str = "World Cup") -> list[dict]:
    """
    Carrega as partidas de matches.parquet, filtra pelos últimos ~20 jogos de nível similar
    (Amistoso vs Competitivo), calcula Z-Scores para janelas de 1 a 5 jogos e retorna
    até 3 anomalias estatisticamente significativas (|Z| > 1.96).
    """
    if not parquet_path.exists():
        return []

    # 1. Carregar base matches.parquet
    df = pd.read_parquet(parquet_path)
    
    # Filtrar jogos do time
    df_team = df[df["team"] == team_name].copy()
    if len(df_team) == 0:
        return []
        
    # Ordenar por data decrescente
    df_team = df_team.sort_values(by="date", ascending=False).reset_index(drop=True)
    
    # 2. Mapear nível de relevância do torneio atual
    target_weight = get_competition_weight(target_competition)
    is_target_competitive = target_weight > 0.2
    
    # Classificar as partidas históricas em Amistoso ou Competitivo
    df_team["weight"] = df_team["competition"].apply(get_competition_weight)
    df_team["is_competitive"] = df_team["weight"] > 0.2
    
    # Filtrar partidas da mesma classe (Amistosos vs Competitivos)
    df_filtered = df_team[df_team["is_competitive"] == is_target_competitive].copy()
    
    # Se tivermos poucos jogos daquela classe, usamos todas as partidas disponíveis como fallback
    if len(df_filtered) < 5:
        df_filtered = df_team.copy()
        
    # Obter os últimos ~20 jogos (mais recentes no topo)
    df_base = df_filtered.head(20).copy()
    N_base = len(df_base)
    
    if N_base < 3:
        # Sem dados históricos mínimos para calcular média/desvio confiáveis
        return []

    # Inverter a ordem para cronológica para fins de cálculos se necessário, mas manter mais recentes acessíveis
    # As estatísticas de interesse
    stats_cols = {
        "points": lambda r: 3 if r["goals_scored"] > r["goals_conceded"] else (1 if r["goals_scored"] == r["goals_conceded"] else 0),
        "goals_scored": lambda r: r["goals_scored"],
        "goals_conceded": lambda r: r["goals_conceded"],
        "sb_shots": lambda r: r["sb_shots"],
        "sb_shots_on_target": lambda r: r["sb_shots_on_target"],
        "sb_corners": lambda r: r["sb_corners"],
        "sb_cards": lambda r: r["sb_cards"]
    }
    
    # Criar DataFrame com as séries numéricas
    series_data = {}
    for col_name, func in stats_cols.items():
        series_data[col_name] = df_base.apply(func, axis=1).values
        
    # 3. Calcular Média e Desvio-Padrão na base histórica inteira (~20 jogos)
    # 4. Varrer janelas curtas J (1 a 5 jogos mais recentes) para encontrar a maior anomalia
    anomalies_list = []
    
    for key, values in series_data.items():
        mu = float(np.mean(values))
        sigma = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        sigma = max(sigma, 1e-4) # Evitar divisão por zero
        
        best_z = 0.0
        best_j = 1
        best_avg = 0.0
        best_sum = 0.0
        
        # Avaliar janelas de 1 a 5
        max_j_possible = min(5, N_base)
        for J in range(1, max_j_possible + 1):
            window_vals = values[:J]  # mais recentes (posições 0 a J-1)
            X_J = float(np.mean(window_vals))
            
            # Z-score clássico da média de amostra curta: Z = (X_J - mu) / (sigma / sqrt(J))
            Z = (X_J - mu) / (sigma / np.sqrt(J))
            
            if np.abs(Z) > np.abs(best_z):
                best_z = Z
                best_j = J
                best_avg = X_J
                best_sum = float(np.sum(window_vals))
                
        # Guardar o pico da estatística
        anomalies_list.append({
            "stat": key,
            "z": best_z,
            "j": best_j,
            "avg": best_avg,
            "sum": best_sum,
            "media": mu,
            "sigma": sigma
        })
        
    # 5. Filtrar por significância (|Z| > 1.96) e ordenar por magnitude absoluta do desvio
    significant = [a for a in anomalies_list if np.abs(a["z"]) > 1.96]
    significant = sorted(significant, key=lambda a: np.abs(a["z"]), reverse=True)
    
    # 6. Selecionar no máximo 3 estatísticas distintas (já garantido que cada item é uma estatística única)
    selected_anomalies = significant[:3]
    
    # 7. Formatar as mensagens textuais
    # Moldes de texto explicativos
    templates = {
        "points": {
            "above": "Conquistou {sum:.0f} pontos nos últimos {j} jogos (média de {avg:.1f}), bem acima da sua média histórica recente de {media:.1f}.",
            "below": "Conquistou apenas {sum:.0f} pontos nos últimos {j} jogos (média de {avg:.1f}), abaixo da sua média histórica recente de {media:.1f}."
        },
        "goals_scored": {
            "above": "Marcou {sum:.0f} gols nos últimos {j} jogos (média de {avg:.1f}), superando sua média histórica de {media:.1f}.",
            "below": "Marcou apenas {sum:.0f} gols nos últimos {j} jogos (média de {avg:.1f}), bem abaixo do padrão habitual de {media:.1f}."
        },
        "goals_conceded": {
            "above": "Sofreu {sum:.0f} gols nos últimos {j} jogos (média de {avg:.1f}), demonstrando fragilidade em relação à média de {media:.1f}.",
            "below": "Sofreu apenas {sum:.0f} gols nos últimos {j} jogos (média de {avg:.1f}), mostrando consistência defensiva acima da média de {media:.1f}."
        },
        "sb_shots": {
            "above": "Finalizou {sum:.0f} vezes nos últimos {j} jogos (média de {avg:.1f}), com volume ofensivo superior à média de {media:.1f}.",
            "below": "Finalizou apenas {sum:.0f} vezes nos últimos {j} jogos (média de {avg:.1f}), abaixo do ímpeto ofensivo normal de {media:.1f}."
        },
        "sb_shots_on_target": {
            "above": "Acertou {sum:.0f} chutes a gol nos últimos {j} jogos (média de {avg:.1f}), com precisão superior à média de {media:.1f}.",
            "below": "Acertou apenas {sum:.0f} chutes a gol nos últimos {j} jogos (média de {avg:.1f}), demonstrando baixa eficácia em relação à média de {media:.1f}."
        },
        "sb_corners": {
            "above": "Cobrou {sum:.0f} escanteios nos últimos {j} jogos (média de {avg:.1f}), volume bem superior à média normal de {media:.1f}.",
            "below": "Cobrou apenas {sum:.0f} escanteios nos últimos {j} jogos (média de {avg:.1f}), abaixo da sua média típica de {media:.1f}."
        },
        "sb_cards": {
            "above": "Recebeu {sum:.0f} cartões nos últimos {j} jogos (média de {avg:.1f}), em uma sequência mais indisciplinada que a média de {media:.1f}.",
            "below": "Recebeu apenas {sum:.0f} cartões nos últimos {j} jogos (média de {avg:.1f}), mantendo alta disciplina em relação à média de {media:.1f}."
        }
    }
    
    results = []
    for a in selected_anomalies:
        stat_name = a["stat"]
        direction = "above" if a["z"] > 0 else "below"
        
        # Preencher o template correspondente
        template = templates[stat_name][direction]
        message = template.format(
            sum=a["sum"],
            j=a["j"],
            avg=a["avg"],
            media=a["media"],
            sigma=a["sigma"]
        )
        
        results.append({
            "stat": stat_name,
            "z_score": float(a["z"]),
            "window_size": int(a["j"]),
            "message": message,
            "type": "alert" if direction == "above" and stat_name in ["goals_conceded", "sb_cards"] or direction == "below" and stat_name in ["points", "goals_scored", "sb_shots", "sb_shots_on_target", "sb_corners"] else "positive"
        })
        
    return results
