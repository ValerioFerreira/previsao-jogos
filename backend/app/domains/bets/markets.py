"""Lógica pura da 'Aposta Escolhida' (sem BD): extrai as seleções disponíveis do snapshot
da análise, calcula a odd combinada com o motor Same Game Parlay (SGP) e faz a
AUTO-SELEÇÃO de uma aposta com odd próxima do teto (2,00) quando o usuário não escolhe.

O motor SGP integra:
1. Matriz de Distribuição Conjunta de Placares Dixon-Coles P(H=h, A=a) para Resultado 1X2,
   Ambas Marcam (BTTS) e Linhas de Gols Over/Under — calculando probabilidade exata, tratando
   redundâncias e detectando conflitos/incompatibilidades.
2. Cópula Gaussiana Multivariada Calibrada para mercados de contagem (Escanteios, Cartões, Chutes).
"""
from __future__ import annotations

import random
from typing import Any
from fastapi import HTTPException, status

MAX_AUTO_LEGS = 4  # nº máximo de seleções numa aposta auto-selecionada


def base_market(group: str) -> str:
    """Mercado-base de um `group` (ex.: 'escanteios_total:8.5' -> 'escanteios',
    'gols_ou2.5' -> 'gols'). Mapeia qualquer variação para a categoria canônica."""
    g = group.split(":")[0]
    if g.startswith("gols"):
        return "gols"
    if g.startswith("escanteios"):
        return "escanteios"
    if g.startswith("cartoes"):
        return "cartoes"
    if g.startswith("chutes_a_gol"):
        return "chutes_a_gol"
    if g.startswith("chutes"):
        return "chutes"
    if g.startswith("btts"):
        return "btts"
    if g.startswith("resultado"):
        return "resultado"
    return g


def _odd(prob_pct: float | None) -> float | None:
    if not prob_pct or prob_pct <= 0:
        return None
    return round(100.0 / prob_pct, 2)


def extract_candidates(snapshot: dict, home_team: str, away_team: str) -> dict[str, dict]:
    """market_key -> {group, market_key, label, selection, odd}."""
    out: dict[str, dict] = {}

    def add(group, key, label, selection, odd):
        if odd and odd > 1.0:
            out[key] = {"group": group, "market_key": key, "label": label,
                        "selection": selection, "odd": float(odd)}

    # Resultado (1X2)
    probs = (snapshot.get("vencedor") or {}).get("probabilidades") or {}
    add("resultado", "resultado.home", f"Vitória {home_team}", "home", _odd(probs.get(home_team)))
    add("resultado", "resultado.draw", "Empate", "draw", _odd(probs.get("Empate")))
    add("resultado", "resultado.away", f"Vitória {away_team}", "away", _odd(probs.get(away_team)))

    # Ambas marcam
    btts = snapshot.get("ambas_marcam") or {}
    if btts:
        ps = btts.get("prob_sim")
        add("btts", "btts.sim", "Ambas marcam: Sim", "sim", _odd(ps))
        add("btts", "btts.nao", "Ambas marcam: Não", "nao", _odd(100 - ps) if ps is not None else None)

    # Over/Under 2.5 gols
    ou = snapshot.get("over_2_5") or {}
    if ou:
        ps = ou.get("prob_sim")
        add("gols_ou2.5", "gols.ou2.5.over", "Mais de 2,5 gols", "over", _odd(ps))
        add("gols_ou2.5", "gols.ou2.5.under", "Menos de 2,5 gols", "under", _odd(100 - ps) if ps is not None else None)

    # Mercados de contagem (total) — O/U por linha, com odd justa (calibrada)
    count_markets = [
        ("escanteios", (snapshot.get("escanteios") or {}).get("total"), "Escanteios"),
        ("cartoes", (snapshot.get("cartoes") or {}).get("total"), "Cartões"),
        ("chutes", snapshot.get("chutes"), "Finalizações"),
        ("chutes_a_gol", (snapshot.get("chutes_a_gol") or {}).get("total"), "Finalizações a gol"),
    ]
    for mkt, block, nome in count_markets:
        linhas = (block or {}).get("linhas") or {}
        for line, sides in linhas.items():
            for side in ("over", "under"):
                s = sides.get(side) or {}
                label = f"{nome} {'Mais' if side == 'over' else 'Menos'} de {line}"
                add(f"{mkt}_total:{line}", f"{mkt}.total.{line}.{side}", label, side, s.get("odd_justa"))
    return out


# --- Cópula gaussiana para apostas COMBINADAS (EXP7/13/14, validado) ---------------
_COPULA_VARS = {"gols": 0, "chutes": 1, "chutes_a_gol": 2, "escanteios": 3}
_SIGMA = [
    [1.00, 0.22, 0.22, 0.05],
    [0.22, 1.00, 0.55, 0.30],
    [0.22, 0.55, 1.00, 0.18],
    [0.05, 0.30, 0.18, 1.00],
]


def _copula_joint_prob(items: list[tuple[int, float, str]]) -> float | None:
    if len(items) < 2:
        return None
    try:
        import numpy as np
        from scipy.stats import norm, multivariate_normal
    except Exception:
        return None
    idx = [it[0] for it in items]
    S = np.array([[_SIGMA[i][j] for j in idx] for i in idx], dtype=float)
    c, flip = [], []
    for _, p, sel in items:
        p = min(0.999, max(1e-4, float(p)))
        if sel == "over":
            c.append(-norm.ppf(1.0 - p))
            flip.append(-1.0)
        else:
            c.append(norm.ppf(p))
            flip.append(1.0)
    f = np.array(flip)
    Sp = S * np.outer(f, f)
    np.fill_diagonal(Sp, 1.0)
    try:
        jp = float(multivariate_normal(mean=np.zeros(len(idx)), cov=Sp, allow_singular=True).cdf(np.array(c)))
    except Exception:
        return None
    if not (jp == jp) or jp <= 0:
        return None
    return jp


def _evaluate_score_condition(market_key: str, h: int, a: int) -> bool:
    """Avalia se o placar exato (h, a) satisfaz a seleção de mercado especificada."""
    if market_key == "resultado.home":
        return h > a
    if market_key == "resultado.draw":
        return h == a
    if market_key == "resultado.away":
        return h < a
    if market_key == "btts.sim":
        return h >= 1 and a >= 1
    if market_key == "btts.nao":
        return h == 0 or a == 0
    if market_key.startswith("gols."):
        side = "over" if market_key.endswith(".over") else ("under" if market_key.endswith(".under") else None)
        if side:
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", market_key)
            if m:
                line = float(m.group(1))
                return (h + a) > line if side == "over" else (h + a) < line
    return True


def combined_odd(selections: list[dict], snapshot: dict | None = None, cap_precision: int = 2) -> float:
    """Calcula a odd combinada via motor Same Game Parlay (SGP).
    
    1. Para combinações contendo mercados de placar/gols (1X2, BTTS, Over/Under Gols):
       Se o snapshot contiver a matriz conjunta Dixon-Coles 11x11, calcula a probabilidade
       conjunta exata somando P(H=h, A=a) para todos os placares que satisfazem todas as
       condições simultaneamente. Isso trata redundâncias e detecta conflitos.
    2. Para mercados de contagem (Escanteios, Cartões, Finalizações), aplica a Cópula Gaussiana.
    """
    if not selections:
        return 1.0

    score_sels = [s for s in selections if base_market(s["group"]) in ("resultado", "btts", "gols")]
    count_sels = [s for s in selections if base_market(s["group"]) in _COPULA_VARS and base_market(s["group"]) != "gols"]
    other_sels = [s for s in selections if s not in score_sels and s not in count_sels]

    p_score = 1.0
    matrix = (snapshot.get("gols") or {}).get("matrix") if snapshot else None

    if score_sels and matrix:
        try:
            import numpy as np
            mat = np.array(matrix, dtype=float)
            if mat.ndim == 2 and mat.shape[0] > 0 and mat.shape[1] > 0:
                p_joint_sum = 0.0
                for h in range(mat.shape[0]):
                    for a in range(mat.shape[1]):
                        match_all = True
                        for s in score_sels:
                            if not _evaluate_score_condition(s["market_key"], h, a):
                                match_all = False
                                break
                        if match_all:
                            p_joint_sum += mat[h, a]
                
                if p_joint_sum <= 1e-9:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="As seleções escolhidas são mutuamente exclusivas e impossíveis de ocorrer juntas."
                    )
                p_score = p_joint_sum
        except HTTPException:
            raise
        except Exception:
            p_score = 1.0
            for s in score_sels:
                p_score *= (1.0 / float(s["odd"])) if float(s["odd"]) > 0 else 1e-4
    elif score_sels:
        p_score = 1.0
        for s in score_sels:
            p_score *= (1.0 / float(s["odd"])) if float(s["odd"]) > 0 else 1e-4

    # Cópula para seleções de contagem
    p_count = 1.0
    if len(count_sels) >= 2:
        copula_items = []
        for s in count_sels:
            b = base_market(s["group"])
            p_marg = 1.0 / float(s["odd"]) if float(s["odd"]) > 0 else 1e-4
            copula_items.append((_COPULA_VARS[b], p_marg, s.get("selection", "over")))
        jp = _copula_joint_prob(copula_items)
        if jp is not None and jp > 0:
            p_count = jp
        else:
            for s in count_sels:
                p_count *= (1.0 / float(s["odd"])) if float(s["odd"]) > 0 else 1e-4
    elif len(count_sels) == 1:
        s = count_sels[0]
        p_count = (1.0 / float(s["odd"])) if float(s["odd"]) > 0 else 1e-4

    # Outros mercados independentes
    p_others = 1.0
    for s in other_sels:
        p_others *= (1.0 / float(s["odd"])) if float(s["odd"]) > 0 else 1e-4

    p_final = p_score * p_count * p_others
    if p_final <= 0:
        return 999.0

    return round(1.0 / p_final, cap_precision)


def auto_select(candidates: dict[str, dict], cap: float, snapshot: dict | None = None) -> list[dict]:
    """Sorteia, a cada chamada, uma combinação (grupos distintos, até MAX_AUTO_LEGS)
    entre as que ficam com odd combinada mais próxima do teto (2,00) por baixo — assim
    cliques sucessivos no botão "Selecionar Automaticamente" tendem a sugerir apostas
    diferentes, sempre com odd <= cap."""
    items = sorted(
        [c for c in candidates.values() if 1.0 < c["odd"] <= cap],
        key=lambda c: (-c["odd"], c["market_key"]),
    )
    found: list[tuple[float, list[dict]]] = []

    def dfs(start: int, used: set, chosen: list):
        if chosen:
            try:
                codd = combined_odd(chosen, snapshot=snapshot)
                if codd <= cap + 1e-9:
                    found.append((codd, list(chosen)))
            except Exception:
                pass
        if len(chosen) >= MAX_AUTO_LEGS:
            return
        for j in range(start, len(items)):
            c = items[j]
            b = base_market(c["group"])
            if b in used:
                continue
            chosen.append(c); used.add(b)
            dfs(j + 1, used, chosen)
            chosen.pop(); used.discard(b)

    dfs(0, set(), [])
    if not found:
        return []

    best_codd = max(codd for codd, _ in found)
    threshold = best_codd * 0.80
    pool = [sel for codd, sel in found if codd >= threshold] or [sel for _, sel in found]
    return random.choice(pool)


def resolve_selections(candidates: dict[str, dict], market_keys: list[str]) -> list[dict]:
    """Valida as market_keys escolhidas -> seleções; recusa seleções INTERDEPENDENTES
    (duas do mesmo mercado-base), como fazem as casas de aposta."""
    chosen, bases = [], set()
    for mk in market_keys:
        c = candidates.get(mk)
        if c is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Mercado inválido: {mk}")
        b = base_market(c["group"])
        if b in bases:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Não é possível combinar seleções interdependentes do mesmo mercado "
                       "(ex.: duas linhas de gols, escanteios ou cartões).",
            )
        bases.add(b); chosen.append(c)
    return chosen

