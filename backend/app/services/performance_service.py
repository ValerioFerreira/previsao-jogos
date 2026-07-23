"""
app/services/performance_service.py
=====================================
Serve as métricas de desempenho do modelo (vitrine /desempenho) a partir dos
JSON PRECOMPUTADOS em `data/reports/performance/` — gerados offline por
`scripts/adhoc_metrics_{hitrates,model_vs_naive}.py`. Padrão precompute (igual
`aggregates`): nada de rodar backtest no request; só lê e serve, com cache em
memória.

Os JSON são regenerados quando o backtest roda; se algum faltar, o endpoint
degrada pro que existir (nunca quebra a página).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# backend/app/services/performance_service.py -> backend/
_ROOT = Path(__file__).resolve().parents[2]
_PERF_DIR = _ROOT / "data" / "reports" / "performance"


def _read(name: str) -> dict | None:
    path = _PERF_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


@lru_cache(maxsize=1)
def get_performance_overview() -> dict:
    """Visão geral: headline de calibração (walk-forward) + taxas de acerto por
    liga + comparativo modelo-vs-aposta-ingênua. Tudo já precomputado."""
    overview = _read("overview.json") or {}
    hitrates = _read("hitrates.json") or {}
    naive = _read("model_vs_naive.json") or {}
    fair_odds = _read("fair_odds.json") or {}
    return {
        "overview": overview,
        "hitrates": hitrates,
        "model_vs_naive": naive,
        "fair_odds": fair_odds,
        "disponivel": bool(overview or hitrates or naive or fair_odds),
    }


@lru_cache(maxsize=32)
def get_performance_league(league: str) -> dict:
    """Detalhe de uma liga (taxas de acerto + estratégias vs ingênuas)."""
    hitrates = _read("hitrates.json") or {}
    naive = _read("model_vs_naive.json") or {}
    hr = (hitrates.get("ligas") or {}).get(league)
    nv = (naive.get("ligas") or {}).get(league)
    if hr is None and nv is None:
        return {"league": league, "encontrado": False}
    return {"league": league, "encontrado": True, "hitrates": hr, "model_vs_naive": nv}
