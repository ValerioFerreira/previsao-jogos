#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/corner_interactions.py
==========================
Features de interacao de MANDO para o modelo de escanteios (item 2). O modelo
super-creditava ~0.2 escanteios ao mandante nominal em campo neutro (residuo real,
~2.4 sigma) porque as flags `neutral`/`real_home_advantage` sozinhas nao bastavam
para o GBR zerar a assimetria. Estas interacoes (ativas so quando ha mando real,
rha = 1 - neutral) deixam o modelo aprender o premio de escanteio condicionado ao
mando — reduzindo o residuo em neutro.

Deterministicas a partir de colunas existentes (sem mexer no build_final_dataset).
Usadas IDENTICAMENTE no treino (train_corners_nb.py) e na inferencia (predictor.py).
"""
CORNER_INTERACTIONS = ["rha_x_elo_winprob", "rha_x_corner_diff"]


def add_corner_interactions(df):
    df = df.copy()
    rha = (1 - df["neutral"].fillna(0)).astype(float)        # real_home_advantage
    df["rha_x_elo_winprob"] = rha * df["elo_home_winprob"].fillna(0.5)
    df["rha_x_corner_diff"] = rha * (
        df["home_sb_corners_l5"].fillna(0) - df["away_sb_corners_l5"].fillna(0))
    return df
