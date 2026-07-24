"""
app/services/odds_bookmaker_service.py
=======================================
Serve as odds por casa de apostas ("Verificador de Bets") a partir das tabelas
`odds_bookmaker_latest` (scope="selecao") / `club_odds_bookmaker_latest`
(scope="clube") no Neon -- alimentadas pelos coletores forward
(scripts/collect_odds_forward.py e scripts/collect_club_odds_forward.py, rodam a
cada ~3h) via scripts/fetch_odds.py::parse_fixture_odds_by_bookmaker.

NÃO recalcula odd justa aqui -- isso já existe em /predict (prediction.odds,
campo faixa_odd_justa por outcome); este serviço só devolve, por mercado/outcome,
a lista casa+odd JÁ ORDENADA decrescente por odd. O cruzamento com a odd justa do
modelo é feito no frontend (100% client-side).
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.db.connection import engine

TABLES = {
    "selecao": "odds_bookmaker_latest",
    "clube": "club_odds_bookmaker_latest",
}


def get_bookmaker_odds(fixture_id: int, scope: str = "selecao") -> dict[str, Any]:
    """Lê a tabela Neon correta pelo fixture_id. Fora da janela de retenção (1-14
    dias antes do jogo) ou ainda não coletado (ciclo de 3h não passou) => 'disponivel':
    False, nunca erro -- é um estado esperado, não uma falha."""
    table = TABLES.get(scope, TABLES["selecao"])
    try:
        df = pd.read_sql(
            text(f'SELECT odds_by_bookmaker, updated_at FROM "{table}" WHERE fixture_id = :fid'),
            con=engine, params={"fid": str(fixture_id)},
        )
    except Exception as e:  # tabela pode ainda não existir (ex.: 1ª execução do coletor)
        print(f"[ERRO DB] {table}: {e}")
        return {"disponivel": False}

    if df.empty:
        return {"disponivel": False}

    row = df.iloc[0]
    raw = row.get("odds_by_bookmaker")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (TypeError, ValueError):
        return {"disponivel": False}

    if not parsed:
        return {"disponivel": False}

    mercados: dict[str, Any] = {}
    for mercado, outcomes in parsed.items():
        mercados[mercado] = {
            outcome: sorted(entries, key=lambda e: e.get("odd", 0), reverse=True)
            for outcome, entries in outcomes.items()
        }

    return {
        "disponivel": True,
        "fixture_id": fixture_id,
        "atualizado_em": row.get("updated_at"),
        "mercados": mercados,
    }
