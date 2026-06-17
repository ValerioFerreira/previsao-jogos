from __future__ import annotations

import math
from typing import Any


Z80 = 1.2815515655446004


def clamp_probability(value: float) -> float:
    return min(0.999, max(0.001, value))


def fair_odd(probability: float) -> float:
    return round(1.0 / clamp_probability(probability), 2)


def odds_range(probability_low: float, probability_high: float) -> dict[str, float]:
    low = clamp_probability(min(probability_low, probability_high))
    high = clamp_probability(max(probability_low, probability_high))
    return {
        "min": fair_odd(high),
        "max": fair_odd(low),
    }


def classifier_probability_interval(
    probability: float,
    n_train: int,
    confidence_reference: float,
) -> tuple[float, float]:
    """Conservative 80% interval for model probability display.

    The predictor does not expose calibrated probability quantiles for
    classifiers. This interval keeps the model probability intact and uses the
    training size plus prediction strength only to size an analytical band.
    """
    p = clamp_probability(probability)
    strength = max(0.05, min(1.0, confidence_reference))
    effective_n = max(40.0, float(n_train) * strength)
    se = math.sqrt((p * (1.0 - p)) / effective_n)
    half_width = max(0.015, Z80 * se)
    return clamp_probability(p - half_width), clamp_probability(p + half_width)


def binary_market_odds(prob_yes_percent: float, n_train: int) -> dict[str, Any]:
    p_yes = clamp_probability(prob_yes_percent / 100.0)
    p_no = 1.0 - p_yes
    confidence_reference = max(p_yes, p_no)
    yes_low, yes_high = classifier_probability_interval(p_yes, n_train, confidence_reference)
    no_low, no_high = classifier_probability_interval(p_no, n_train, confidence_reference)
    return {
        "sim": {
            "probabilidade": round(p_yes * 100, 1),
            "odd_justa": fair_odd(p_yes),
            "faixa_odd_justa": odds_range(yes_low, yes_high),
            "intervalo_probabilidade_80": [round(yes_low * 100, 1), round(yes_high * 100, 1)],
        },
        "nao": {
            "probabilidade": round(p_no * 100, 1),
            "odd_justa": fair_odd(p_no),
            "faixa_odd_justa": odds_range(no_low, no_high),
            "intervalo_probabilidade_80": [round(no_low * 100, 1), round(no_high * 100, 1)],
        },
    }


def winner_market_odds(probabilidades: dict[str, float], n_train: int) -> dict[str, Any]:
    confidence_reference = max((value / 100.0 for value in probabilidades.values()), default=0.34)
    markets: dict[str, Any] = {}
    for label, percent in probabilidades.items():
        p = clamp_probability(percent / 100.0)
        low, high = classifier_probability_interval(p, n_train, confidence_reference)
        markets[label] = {
            "probabilidade": round(p * 100, 1),
            "odd_justa": fair_odd(p),
            "faixa_odd_justa": odds_range(low, high),
            "intervalo_probabilidade_80": [round(low * 100, 1), round(high * 100, 1)],
        }
    return markets


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def survival_probability(line: float, mean: float, sigma: float) -> float:
    if sigma <= 1e-9:
        return 0.5 if mean == line else (0.999 if mean > line else 0.001)
    return clamp_probability(1.0 - normal_cdf((line - mean) / sigma))


def numeric_line_market(metric: dict[str, Any], label: str) -> dict[str, Any]:
    estimate = float(metric["estimativa"])
    lo, hi = (float(metric["intervalo"][0]), float(metric["intervalo"][1]))
    width = hi - lo
    if width <= 0.05:
        return {
            "disponivel": False,
            "motivo": "Intervalo quantilico insuficiente para estimar uma odd honesta.",
        }

    sigma = max(0.05, width / (2.0 * Z80))
    line = max(0.5, math.floor(estimate) + 0.5)
    if label in {"total_shots", "home_corners", "away_corners"}:
        line = max(0.5, round(estimate * 2.0) / 2.0)

    p_over = survival_probability(line, estimate, sigma)
    p_under = 1.0 - p_over
    p_over_low = survival_probability(line, lo, sigma)
    p_over_high = survival_probability(line, hi, sigma)
    p_under_low = 1.0 - max(p_over_low, p_over_high)
    p_under_high = 1.0 - min(p_over_low, p_over_high)

    return {
        "disponivel": True,
        "linha": round(line, 1),
        "metodo": "Normal aproximada a partir dos quantis 10/50/90 ja produzidos pelo modelo.",
        "over": {
            "probabilidade": round(p_over * 100, 1),
            "odd_justa": fair_odd(p_over),
            "faixa_odd_justa": odds_range(p_over_low, p_over_high),
            "intervalo_probabilidade_80": [
                round(min(p_over_low, p_over_high) * 100, 1),
                round(max(p_over_low, p_over_high) * 100, 1),
            ],
        },
        "under": {
            "probabilidade": round(p_under * 100, 1),
            "odd_justa": fair_odd(p_under),
            "faixa_odd_justa": odds_range(p_under_low, p_under_high),
            "intervalo_probabilidade_80": [
                round(min(p_under_low, p_under_high) * 100, 1),
                round(max(p_under_low, p_under_high) * 100, 1),
            ],
        },
    }


def enrich_with_odds(prediction: dict[str, Any], n_train: dict[str, int]) -> dict[str, Any]:
    home_team, away_team = [name for name in prediction["vencedor"]["probabilidades"] if name != "Empate"]
    return {
        "vencedor": winner_market_odds(prediction["vencedor"]["probabilidades"], n_train.get("result", 1)),
        "ambas_marcam": binary_market_odds(prediction["ambas_marcam"]["prob_sim"], n_train.get("btts", 1)),
        "over_under_2_5": binary_market_odds(prediction["over_2_5"]["prob_sim"], n_train.get("over25", 1)),
        "linhas_numericas": {
            "gols": numeric_line_market(prediction["gols"], "total_goals"),
            "chutes": numeric_line_market(prediction["chutes"], "total_shots"),
            "escanteios": {
                home_team: numeric_line_market(prediction["escanteios"][home_team], "home_corners"),
                away_team: numeric_line_market(prediction["escanteios"][away_team], "away_corners"),
            },
        },
        "nota": (
            "Odd justa = 1/probabilidade, sem margem da casa. Use como referencia analitica; "
            "nenhuma previsao garante resultado."
        ),
    }

