#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api/value_betting.py
====================
Núcleo de VALUE BETTING (Passo 4 / MELHORIAS_UX_UI item 5): compara a
probabilidade do nosso modelo (bem calibrado) com a odd da casa para apontar
"valor" — ou seja, EV positivo (a casa está pagando mais do que o risco real).

Pura lógica, sem dependência de API — o UX entra a odd da casa, o predictor dá a
probabilidade, e esta função devolve o veredito. Funciona OFFLINE.

LIMITAÇÃO REGISTRADA (api-football /odds): só há 7 dias de histórico e odds de
1-14 dias antes do jogo. Logo NÃO dá para backtestar value contra odds históricas;
só dá para coletar odds dos jogos FUTUROS e acumular ao longo do tempo. Até lá, o
value é exibido com a ressalva de que a calibração do modelo é a garantia, não um
histórico de mercado.
"""
from __future__ import annotations


def _clamp(p: float) -> float:
    return min(0.999, max(0.001, float(p)))


def implied_probability(market_odd: float) -> float:
    """Probabilidade implícita bruta da odd da casa (com margem embutida)."""
    return 1.0 / market_odd


def devig_two_way(odd_a: float, odd_b: float) -> tuple[float, float]:
    """Remove a margem da casa num mercado de 2 vias (ex.: over/under), normalizando."""
    ia, ib = 1.0 / odd_a, 1.0 / odd_b
    s = ia + ib
    return ia / s, ib / s


def evaluate_bet(model_prob_pct: float, market_odd: float,
                 market_odd_other: float | None = None) -> dict:
    """Avalia uma aposta.

    model_prob_pct: probabilidade do modelo (0-100) para o lado apostado.
    market_odd: odd decimal da casa para esse lado.
    market_odd_other: odd do lado oposto (se houver) — usada para de-vig (prob justa
                      de mercado sem margem), só informativa.

    EV por unidade apostada = p*odd - 1. EV>0 => valor (a casa paga acima do risco).
    """
    p = _clamp(model_prob_pct / 100.0)
    implied = implied_probability(market_odd)
    fair_market = implied
    if market_odd_other:
        fair_market, _ = devig_two_way(market_odd, market_odd_other)
    edge = p * market_odd - 1.0
    return {
        "prob_modelo": round(p * 100, 1),
        "odd_justa_modelo": round(1.0 / p, 2),
        "odd_casa": round(float(market_odd), 2),
        "prob_implicita_casa": round(implied * 100, 1),
        "prob_justa_mercado_sem_margem": round(fair_market * 100, 1),
        "edge_pct": round(edge * 100, 1),        # >0 = valor (EV positivo)
        "valor": edge > 0.0,
        "ressalva": ("Value baseado na calibração do modelo, não em histórico de mercado "
                     "(odds só disponíveis 1-14 dias antes; 7 dias de histórico). "
                     "Nenhuma aposta é garantia."),
    }
