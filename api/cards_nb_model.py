#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/cards_nb_model.py
=====================
Modelo de contagem de CARTOES — NB independente (mandante, visitante, total).

Mesma mecanica da CornersNB (lambda via GBR + r por MLE; total por convolucao).
Diferenca empirica importante (ver comparacao_cartoes.md): em cartoes o r colapsa
em valores altos (~Poisson) — NAO ha sobredispersao real depois de modelar o lambda
(cartoes se comportam como gols, nao como escanteios). O ganho sobre a quantilica
vem de usar uma distribuicao de contagem propria, nao da NB exploitando dispersao.

E uma subclasse so para identidade/nomenclatura distinta no joblib.
"""
try:
    from corners_nb_model import CornersNB
except ImportError:
    from api.corners_nb_model import CornersNB


class CardsNB(CornersNB):
    """NB independente para cartoes. Grade padrao menor (cartoes sao contagem baixa)."""

    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05,
                 max_corners=15, random_state=42, feats=None):
        super().__init__(n_estimators=n_estimators, max_depth=max_depth,
                         learning_rate=learning_rate, max_corners=max_corners,
                         random_state=random_state, feats=feats)
