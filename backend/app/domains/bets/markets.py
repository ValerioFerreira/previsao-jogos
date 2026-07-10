"""Lógica pura da 'Aposta Escolhida' (sem BD): extrai as seleções disponíveis do snapshot
da análise, calcula a odd combinada e faz a AUTO-SELEÇÃO de uma aposta com odd próxima do
teto (2,00) quando o usuário não escolhe.

Cada seleção pertence a um `group` mutuamente exclusivo (não se combina over+under da mesma
linha, nem dois resultados). A odd combinada é o produto das odds das seleções.
"""
from __future__ import annotations

MAX_AUTO_LEGS = 4  # nº máximo de seleções numa aposta auto-selecionada


def base_market(group: str) -> str:
    """Mercado-base de um `group` (ex.: 'escanteios_total:8.5' -> 'escanteios',
    'gols_ou2.5' -> 'gols'). Duas seleções do MESMO mercado-base são interdependentes
    (correlacionadas/implicadas — ex.: Menos de 1,5 e Menos de 2,5 gols; Mais de 8,5 e
    Mais de 9,5 escanteios) e NÃO podem entrar juntas numa aposta, como nas casas."""
    g = group.split(":")[0]
    for suf in ("_total", "_ou2.5"):
        if g.endswith(suf):
            g = g[: -len(suf)]
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
# As contagens ofensivas partilham um fator latente ("intensidade territorial"): combos
# de OVERs correlacionados são MAIS prováveis do que a independência assume, então a odd
# combinada justa é MENOR. Σ = correlações residuais VALIDADAS, encolhidas (conservador).
# Ordem: [gols, finalizacoes, a_gol, escanteios].
_COPULA_VARS = {"gols": 0, "chutes": 1, "chutes_a_gol": 2, "escanteios": 3}
_SIGMA = [
    [1.00, 0.22, 0.22, 0.05],
    [0.22, 1.00, 0.55, 0.30],
    [0.22, 0.55, 1.00, 0.18],
    [0.05, 0.30, 0.18, 1.00],
]


def _copula_joint_prob(items: list[tuple[int, float, str]]) -> float | None:
    """P(∩ eventos) de seleções ofensivas via cópula gaussiana. `items` = lista de
    (idx_var, prob, selection 'over'|'under'). Retorna None se não aplicável."""
    if len(items) < 2:
        return None
    try:
        import numpy as np
        from scipy.stats import norm, multivariate_normal
    except Exception:
        return None
    idx = [it[0] for it in items]
    # sub-matriz Σ das variáveis envolvidas
    S = np.array([[_SIGMA[i][j] for j in idx] for i in idx], dtype=float)
    # transforma cada evento em W_i < c_i (flip = -1 p/ over: P(Z>a)=P(-Z<-a))
    c, flip = [], []
    for _, p, sel in items:
        p = min(0.999, max(1e-4, float(p)))
        if sel == "over":
            c.append(-norm.ppf(1.0 - p)); flip.append(-1.0)
        else:
            c.append(norm.ppf(p)); flip.append(1.0)
    f = np.array(flip)
    Sp = S * np.outer(f, f)                      # correlação de W (sinais ajustados)
    np.fill_diagonal(Sp, 1.0)
    try:
        jp = float(multivariate_normal(mean=np.zeros(len(idx)), cov=Sp, allow_singular=True).cdf(np.array(c)))
    except Exception:
        return None
    if not (jp == jp) or jp <= 0:               # NaN/degenerado -> cai na independência
        return None
    return jp


def combined_odd(selections: list[dict], cap_precision: int = 3) -> float:
    """Odd combinada. Aplica a cópula gaussiana às seleções ofensivas correlacionadas
    (gols/finalizações/a-gol/escanteios); os demais mercados multiplicam por independência.
    Sem seleção ofensiva combinável, é o produto simples (retrocompatível)."""
    off, other_prob = [], 1.0
    for s in selections:
        b = base_market(s["group"])
        p = 1.0 / float(s["odd"]) if float(s["odd"]) > 0 else 1e-4
        if b in _COPULA_VARS:
            off.append((_COPULA_VARS[b], p, s.get("selection", "over")))
        else:
            other_prob *= p
    if len(off) >= 2:
        jp = _copula_joint_prob(off)
        if jp is not None:
            joint = jp * other_prob
            if joint > 0:
                return round(1.0 / joint, cap_precision)
    # fallback: independência (produto das odds)
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
            b = base_market(c["group"])
            if b in used:  # um por mercado-base (evita combinar linhas interdependentes)
                continue
            np_ = prod * c["odd"]
            if np_ <= cap + 1e-9:
                chosen.append(c); used.add(b)
                dfs(j + 1, used, np_, chosen)
                chosen.pop(); used.discard(b)

    dfs(0, set(), 1.0, [])
    if not best["sel"]:
        allc = [c for c in candidates.values() if c["odd"]]
        return [min(allc, key=lambda c: c["odd"])] if allc else []
    return best["sel"]


def resolve_selections(candidates: dict[str, dict], market_keys: list[str]) -> list[dict]:
    """Valida as market_keys escolhidas -> seleções; recusa seleções INTERDEPENDENTES
    (duas do mesmo mercado-base), como fazem as casas de aposta."""
    from fastapi import HTTPException, status
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
