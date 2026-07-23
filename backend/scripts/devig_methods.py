#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/devig_methods.py
==========================
H3 (bateria 2026-07-21) — De-vig 3-vias no mercado 1x2. Tres metodos puros (sem
dependencia de rede/banco), testados com exemplos manuais antes de aplicar a
odds reais (ver `battery_h2_h3.py` e `data/reports/h3_devig/`).

Contexto (ver DOCUMENTACAO_CENTRAL.md §19 / value_betting.py): hoje so existe
`devig_two_way` (mercados de 2 vias, ex. over/under). Em 1x2 a margem da casa e
maior e ASSIMETRICA entre favorito/zebra (favoritos tem margem proporcionalmente
maior) -- de-vig proporcional ingenuo super-estima o favorito. Power e Shin
corrigem isso.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq


def proportional_devig(odds: list[float]) -> list[float]:
    """Baseline: normaliza as probabilidades implicitas para somar 1.
    Nao corrige a assimetria de margem entre favorito/zebra."""
    implied = [1.0 / o for o in odds]
    s = sum(implied)
    return [i / s for i in implied]


def power_devig(odds: list[float], tol: float = 1e-10) -> list[float]:
    """Metodo multiplicativo/potencia: acha k tal que sum((1/o_i)^k) == 1.
    k>1 encolhe TODAS as probabilidades, mas encolhe proporcionalmente mais quem
    tem probabilidade implicita maior (favorito) -- corrige parte da assimetria."""
    implied = np.array([1.0 / o for o in odds])

    def f(k):
        return np.sum(implied ** k) - 1.0

    # overround sempre da sum(implied)>1 -> precisa k>1, f(1) = overround > 0,
    # f(k) decresce em k (k maior encolhe mais) -> procurar k>1 onde f(k)=0.
    k = brentq(f, 1.0, 50.0, xtol=tol)
    p = implied ** k
    return list(p / p.sum())


def shin_devig(odds: list[float], tol: float = 1e-12) -> list[float]:
    """Metodo de Shin (1992/93) — modelo de "insider trading": uma fracao z dos
    apostadores tem informacao privilegiada; a casa poe margem para se proteger
    disso. Resolve z (0<z<1) tal que:
        p_i = ( sqrt(z^2 + 4*(1-z)*z*pi_i^2/S) - z ) / (2*(1-z))
    onde pi_i = 1/o_i (prob. implicita bruta), S = sum(pi_i). Convencao padrao:
    resolve via a equacao equivalente sum(p_i)=1 com p_i em funcao de z."""
    pi = np.array([1.0 / o for o in odds])
    S = pi.sum()

    def f(z):
        # forma fechada padrao (Shin 1992/93): pi_i^2/S, NAO (pi_i/S)^2 -- usar a
        # prob. implicita crua dividida por UM fator de S (bug historico corrigido
        # 2026-07-22, ver backend/data/reports/adhoc_valuebet_w1/critica.md: a
        # versao normalizada duas vezes fazia brentq nunca achar raiz e cair
        # sempre no fallback power_devig, silenciosamente).
        inside = z ** 2 + 4.0 * (1.0 - z) * (pi ** 2) / S
        p = (np.sqrt(np.maximum(inside, 0.0)) - z) / (2.0 * (1.0 - z))
        return p.sum() - 1.0

    overround = S - 1.0
    if overround <= 1e-9:
        # sem margem real -- Shin degenera no proporcional
        return proportional_devig(odds)

    try:
        z = brentq(f, 1e-9, 0.4, xtol=tol)
    except ValueError:
        # margem grande demais para a forma fechada padrao (raro) -- cai no power
        return power_devig(odds)

    inside = z ** 2 + 4.0 * (1.0 - z) * (pi ** 2) / S
    p = (np.sqrt(np.maximum(inside, 0.0)) - z) / (2.0 * (1.0 - z))
    p = np.clip(p, 1e-9, None)
    return list(p / p.sum())


METHODS = {
    "proporcional": proportional_devig,
    "power": power_devig,
    "shin": shin_devig,
}


# ─────────────────────────── testes unitarios ────────────────────────────────
def _approx(a, b, tol=1e-4):
    return abs(a - b) < tol


def run_tests():
    results = []

    # 1) Odds SIMETRICAS (sem favorito, margem uniforme) -- os 3 metodos devem
    #    concordar entre si e com a probabilidade "obvia" por simetria.
    odds_sym = [3.0, 3.0, 3.0]  # overround: 3*(1/3)=1.0 exato, margem zero
    for name, fn in METHODS.items():
        p = fn(odds_sym)
        ok = all(_approx(x, 1 / 3, 1e-6) for x in p)
        results.append((f"simetrico/{name}", ok, p))

    odds_sym_margem = [2.85, 2.85, 2.85]  # margem uniforme, ainda simetrico
    ref = None
    for name, fn in METHODS.items():
        p = fn(odds_sym_margem)
        if ref is None:
            ref = p
        ok = all(_approx(x, ref[i], 1e-3) for i, x in enumerate(p))
        results.append((f"simetrico_com_margem/{name}_concorda_com_primeiro", ok, p))

    # 2) Odds ENVIESADAS (favorito forte) -- favorite-longshot bias documentado na
    #    literatura (Shin 1992/93, Vlastakis et al.): o overround do book NAO se
    #    distribui uniformemente -- proporcionalmente ha MAIS margem no lado
    #    zebra que no favorito. De-vig proporcional (ingenuo) HERDA esse vies e
    #    SUB-estima o favorito / SUPER-estima a zebra. Power/Shin corrigem na
    #    direcao oposta: sobem a prob. do favorito e descem a da zebra vs o
    #    proporcional puro.
    odds_skew = [1.30, 4.80, 9.00]  # favorito claro no primeiro lado
    p_prop = proportional_devig(odds_skew)
    p_power = power_devig(odds_skew)
    p_shin = shin_devig(odds_skew)
    ok_power = p_power[0] > p_prop[0] and p_power[-1] < p_prop[-1]
    ok_shin = p_shin[0] > p_prop[0] and p_shin[-1] < p_prop[-1]
    results.append(("enviesado/power_sobe_favorito_desce_zebra_vs_proporcional", ok_power,
                     {"prop": p_prop, "power": p_power}))
    results.append(("enviesado/shin_sobe_favorito_desce_zebra_vs_proporcional", ok_shin,
                     {"prop": p_prop, "shin": p_shin}))

    # 2b) Regressao: shin tem que ser um metodo GENUINAMENTE DIFERENTE de power,
    #     nao um fallback disfarçado. Bug historico (corrigido 2026-07-22, ver
    #     backend/data/reports/adhoc_valuebet_w1/critica.md): formula errada
    #     (pi/S)^2 em vez de pi^2/S fazia brentq nunca achar raiz -> shin_devig
    #     caia sempre no `except: return power_devig(odds)` silenciosamente, e
    #     os testes acima "passavam" porque so checam DIRECAO (sobe favorito/
    #     desce zebra), que power tambem satisfaz. Este teste pega isso.
    ok_shin_not_power = not _approx(p_shin[0], p_power[0], 1e-6)
    results.append(("enviesado/shin_e_genuinamente_diferente_de_power", ok_shin_not_power,
                     {"shin": p_shin, "power": p_power}))

    # 3) Todos os metodos devem somar 1
    for name, fn in METHODS.items():
        p = fn(odds_skew)
        results.append((f"soma_1/{name}", _approx(sum(p), 1.0, 1e-6), sum(p)))

    # 4) Sem margem (odds "justas", sum(1/o)=1) -- todos devem coincidir com o
    #    proporcional (nada para corrigir).
    p_target = np.array([0.5, 0.3, 0.2])
    fair_odds = list(1.0 / p_target)
    for name, fn in METHODS.items():
        p = fn(fair_odds)
        ok = all(_approx(x, p_target[i], 1e-3) for i, x in enumerate(p))
        results.append((f"sem_margem/{name}_recupera_prob_exata", ok, p))

    return results


if __name__ == "__main__":
    print("=== Testes unitarios devig_methods.py ===")
    all_ok = True
    for name, ok, detail in run_tests():
        status = "OK" if ok else "FALHOU"
        if not ok:
            all_ok = False
        print(f"[{status}] {name} -> {detail}")
    print("\n" + ("TODOS OS TESTES PASSARAM" if all_ok else "ALGUM TESTE FALHOU"))
