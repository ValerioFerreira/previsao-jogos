#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/shots_nb_model.py
=====================
Modelo de contagem de CHUTES (finalizacoes) — NB independente (mandante/visitante/
total). Mesma mecanica da CornersNB, com grade maior (chutes vao ate ~51).

Diferenca de processo: o modelo de producao e treinado com TIME DECAY (sample_weight
por dias) — chutes foi o unico alvo onde o decay reduz o vies temporal e melhora a
calibracao (ver comparacao_chutes.md). r e finito (~20): NB genuinamente usada.
"""
try:
    from corners_nb_model import CornersNB
except ImportError:
    from api.corners_nb_model import CornersNB


class ShotsNB(CornersNB):
    """NB independente para chutes. Grade padrao maior (contagem alta)."""

    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05,
                 max_corners=55, random_state=42, feats=None):
        super().__init__(n_estimators=n_estimators, max_depth=max_depth,
                         learning_rate=learning_rate, max_corners=max_corners,
                         random_state=random_state, feats=feats)
