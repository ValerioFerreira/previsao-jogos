from __future__ import annotations

import math
from typing import Any


Z80 = 1.2815515655446004


def clamp_probability(value: float) -> float:
    return min(0.999, max(0.001, value))


def fair_odd(probability: float) -> float:
    return round(1.0 / clamp_probability(probability), 2)


# --- Correção de viés por mercado + faixa de odd justa ±5% (PLANO 4 / Fase B) ---
# A correção (Platt logit-linear por mercado, aprendida contra odds reais de-vigadas)
# é passada como dict {mercado: {"a","b"}}; ausente => identidade. Viés é pequeno
# (modelo já bem calibrado) — recalibra a odd justa exibida sem inventar edge.
FAIXA_PCT = 0.05


def apply_bias(probability: float, market_key: str | None, correction: dict | None) -> float:
    p = clamp_probability(probability)
    if not correction or not market_key or market_key not in correction:
        return p
    c = correction[market_key]
    a, b = c.get("a", 1.0), c.get("b", 0.0)
    if a == 1.0 and b == 0.0:
        return p
    z = math.log(p / (1.0 - p))
    return clamp_probability(1.0 / (1.0 + math.exp(-(a * z + b))))


def fair_band(odd_justa: float) -> dict[str, float]:
    """Faixa de odd justa a 95%/100%/105% da odd corrigida (min=0,95·odd, max=1,05·odd)."""
    return {"min": round(odd_justa * (1.0 - FAIXA_PCT), 2),
            "max": round(odd_justa * (1.0 + FAIXA_PCT), 2)}


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


def binary_market_odds(prob_yes_percent: float, n_train: int,
                       correction: dict | None = None, market_key: str | None = None) -> dict[str, Any]:
    p_yes = clamp_probability(prob_yes_percent / 100.0)
    p_no = 1.0 - p_yes
    confidence_reference = max(p_yes, p_no)
    yes_low, yes_high = classifier_probability_interval(p_yes, n_train, confidence_reference)
    no_low, no_high = classifier_probability_interval(p_no, n_train, confidence_reference)
    p_yes_c = apply_bias(p_yes, market_key, correction)
    p_no_c = apply_bias(p_no, market_key, correction)
    odd_yes, odd_no = fair_odd(p_yes_c), fair_odd(p_no_c)
    return {
        "sim": {
            "probabilidade": round(p_yes * 100, 1),
            "odd_justa": odd_yes,
            "faixa_odd_justa": fair_band(odd_yes),
            "intervalo_probabilidade_80": [round(yes_low * 100, 1), round(yes_high * 100, 1)],
        },
        "nao": {
            "probabilidade": round(p_no * 100, 1),
            "odd_justa": odd_no,
            "faixa_odd_justa": fair_band(odd_no),
            "intervalo_probabilidade_80": [round(no_low * 100, 1), round(no_high * 100, 1)],
        },
    }


def winner_market_odds(probabilidades: dict[str, float], n_train: int,
                       correction: dict | None = None) -> dict[str, Any]:
    confidence_reference = max((value / 100.0 for value in probabilidades.values()), default=0.34)
    markets: dict[str, Any] = {}
    for label, percent in probabilidades.items():
        p = clamp_probability(percent / 100.0)
        low, high = classifier_probability_interval(p, n_train, confidence_reference)
        odd = fair_odd(apply_bias(p, "1x2", correction))
        markets[label] = {
            "probabilidade": round(p * 100, 1),
            "odd_justa": odd,
            "faixa_odd_justa": fair_band(odd),
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
            "faixa_odd_justa": fair_band(fair_odd(p_over)),
            "intervalo_probabilidade_80": [
                round(min(p_over_low, p_over_high) * 100, 1),
                round(max(p_over_low, p_over_high) * 100, 1),
            ],
        },
        "under": {
            "probabilidade": round(p_under * 100, 1),
            "odd_justa": fair_odd(p_under),
            "faixa_odd_justa": fair_band(fair_odd(p_under)),
            "intervalo_probabilidade_80": [
                round(min(p_under_low, p_under_high) * 100, 1),
                round(max(p_under_low, p_under_high) * 100, 1),
            ],
        },
    }


def corners_line_market(market: dict[str, Any]) -> dict[str, Any]:
    """Bloco de odds de escanteios a partir da CDF real da NB (não da Normal).

    A grade completa de linhas (e a PMF) vive em prediction["escanteios"]; aqui
    expomos uma linha representativa (a mais próxima da estimativa) no formato que
    a página já consome. A probabilidade da NB para uma linha fixa é pontual, então
    a faixa colapsa no próprio valor (a incerteza já está na distribuição inteira).
    """
    linhas = market.get("linhas") or {}
    if not linhas:
        return {"disponivel": False,
                "motivo": "Distribuição de escanteios indisponível."}
    estimate = float(market["estimativa"])
    rep = min((float(k) for k in linhas), key=lambda L: abs(L - estimate))
    key = next(k for k in linhas if float(k) == rep)
    side_over, side_under = linhas[key]["over"], linhas[key]["under"]

    def fmt(side: dict[str, Any]) -> dict[str, Any]:
        return {
            "probabilidade": side["prob"],
            "odd_justa": side["odd_justa"],
            "faixa_odd_justa": fair_band(side["odd_justa"]),
            "intervalo_probabilidade_80": [side["prob"], side["prob"]],
        }

    return {
        "disponivel": True,
        "linha": rep,
        "metodo": "CDF real da Binomial Negativa (substitui a aproximação Normal).",
        "over": fmt(side_over),
        "under": fmt(side_under),
    }


def enrich_with_odds(prediction: dict[str, Any], n_train: dict[str, int],
                     correction: dict | None = None) -> dict[str, Any]:
    home_team, away_team = [name for name in prediction["vencedor"]["probabilidades"] if name != "Empate"]
    return {
        "vencedor": winner_market_odds(prediction["vencedor"]["probabilidades"], n_train.get("result", 1), correction),
        "ambas_marcam": binary_market_odds(prediction["ambas_marcam"]["prob_sim"], n_train.get("btts", 1), correction, "btts"),
        "over_under_2_5": binary_market_odds(prediction["over_2_5"]["prob_sim"], n_train.get("over25", 1), correction, "ou25"),
        "linhas_numericas": {
            "gols": numeric_line_market(prediction["gols"], "total_goals"),
            "chutes": corners_line_market(prediction["chutes"]),
            "escanteios": {
                home_team: corners_line_market(prediction["escanteios"][home_team]),
                away_team: corners_line_market(prediction["escanteios"][away_team]),
                "total": corners_line_market(prediction["escanteios"]["total"]),
            },
            "cartoes": {
                home_team: corners_line_market(prediction["cartoes"][home_team]),
                away_team: corners_line_market(prediction["cartoes"][away_team]),
                "total": corners_line_market(prediction["cartoes"]["total"]),
            },
        },
        "nota": (
            "Odd justa = 1/probabilidade, sem margem da casa. Use como referencia analitica; "
            "nenhuma previsao garante resultado."
        ),
    }

