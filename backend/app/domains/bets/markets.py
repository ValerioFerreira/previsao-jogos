"""Lógica pura da 'Aposta Escolhida' (sem BD): extrai as seleções disponíveis do snapshot
da análise, calcula a odd combinada e faz a AUTO-SELEÇÃO de uma aposta com odd próxima do
teto (2,00) quando o usuário não escolhe.

Cada seleção pertence a um `group` mutuamente exclusivo (não se combina over+under da mesma
linha, nem dois resultados). A odd combinada é o produto das odds das seleções.
"""
from __future__ import annotations

MAX_AUTO_LEGS = 4  # nº máximo de seleções numa aposta auto-selecionada


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


def combined_odd(selections: list[dict], cap_precision: int = 3) -> float:
    prod = 1.0
    for s in selections:
        prod *= float(s["odd"])
    return round(prod, cap_precision)


def auto_select(candidates: dict[str, dict], cap: float) -> list[dict]:
    """Escolhe a combinação (grupos distintos, até MAX_AUTO_LEGS) com odd combinada
    MÁXIMA sem ultrapassar o teto — ou seja, a mais próxima de `cap` (2,00) por baixo."""
    items = sorted(
        [c for c in candidates.values() if 1.0 < c["odd"] <= cap],
        key=lambda c: (-c["odd"], c["market_key"]),
    )
    best = {"prod": 0.0, "sel": []}

    def dfs(start: int, used: set, prod: float, chosen: list):
        if chosen and prod > best["prod"]:
            best["prod"] = prod
            best["sel"] = list(chosen)
        if len(chosen) >= MAX_AUTO_LEGS:
            return
        for j in range(start, len(items)):
            c = items[j]
            if c["group"] in used:
                continue
            np_ = prod * c["odd"]
            if np_ <= cap + 1e-9:
                chosen.append(c); used.add(c["group"])
                dfs(j + 1, used, np_, chosen)
                chosen.pop(); used.discard(c["group"])

    dfs(0, set(), 1.0, [])
    if not best["sel"]:
        allc = [c for c in candidates.values() if c["odd"]]
        return [min(allc, key=lambda c: c["odd"])] if allc else []
    return best["sel"]


def resolve_selections(candidates: dict[str, dict], market_keys: list[str]) -> list[dict]:
    """Valida as market_keys escolhidas pelo usuário -> seleções; sem grupos repetidos."""
    from fastapi import HTTPException, status
    chosen, groups = [], set()
    for mk in market_keys:
        c = candidates.get(mk)
        if c is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Mercado inválido: {mk}")
        if c["group"] in groups:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                detail="Não é possível combinar dois resultados do mesmo mercado.")
        groups.add(c["group"]); chosen.append(c)
    return chosen
