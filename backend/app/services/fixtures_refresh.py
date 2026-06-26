"""
app/services/fixtures_refresh.py
================================
Mantém a LISTA de partidas passadas (tabela past_fixtures no Neon) sempre completa
e atual, para que TODA partida de seleção fique selecionável no seletor — mesmo
sem o detalhe completo cacheado (o detalhe é buscado sob demanda em get_match_detail).

Guarda apenas o mínimo (equipes + competição + timestamp), exatamente no formato do
build_fixture_index. Também adiciona seleções novas em team_ids (para os símbolos).

Uma chamada por dia da janela: GET /fixtures?date=D (todas as partidas do dia),
filtrando para as ligas que o modelo rastreia (lidas do fixture_index).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from app.db.connection import engine
from app.services.fixture_fetch import _get


def _tracked_leagues() -> set[int]:
    with engine.connect() as c:
        rows = c.execute(text("SELECT path FROM fixture_index")).fetchall()
    out: set[int] = set()
    for (p,) in rows:
        m = re.search(r"fixtures/(\d+)/", p or "")
        if m:
            out.add(int(m.group(1)))
    return out


def refresh_past_fixtures(days_back: int = 3) -> dict:
    """Pega as partidas disputadas dos últimos `days_back` dias (+ hoje) nas ligas
    rastreadas e insere em past_fixtures as que ainda não existem. Idempotente."""
    tracked = _tracked_leagues()
    if not tracked:
        return {"ok": False, "erro": "nenhuma liga rastreada (fixture_index vazio)"}

    with engine.connect() as c:
        existing = {r[0] for r in c.execute(text("SELECT fixture_id FROM past_fixtures")).fetchall()}
        existing_teams = {r[0] for r in c.execute(text("SELECT team_name FROM team_ids")).fetchall()}

    today = date.today()
    new_rows, new_teams, seen = [], {}, set()
    dias_consultados = 0
    for i in range(days_back + 1):
        d = (today - timedelta(days=i)).isoformat()
        try:
            resp, _ = _get("/fixtures", date=d)
            dias_consultados += 1
        except Exception as e:
            print(f"[AVISO] refresh /fixtures date={d}: {e}")
            continue
        for f in resp:
            lg = f.get("league") or {}
            if lg.get("id") not in tracked:
                continue
            if (f.get("goals") or {}).get("home") is None:
                continue  # só partidas já disputadas
            fx = f.get("fixture") or {}; t = f.get("teams") or {}
            th = t.get("home") or {}; ta = t.get("away") or {}
            hn, an = th.get("name"), ta.get("name")
            date_full = fx.get("date") or ""; d10 = date_full[:10]
            if not (d10 and hn and an):
                continue
            key = f"{d10}|{hn}|{an}"
            if key not in existing and key not in seen:
                seen.add(key)
                new_rows.append({"fixture_id": key, "home": hn, "away": an,
                                 "date": date_full, "league_name": lg.get("name")})
            for nm, tid in ((hn, th.get("id")), (an, ta.get("id"))):
                if nm and tid and nm not in existing_teams and nm not in new_teams:
                    new_teams[nm] = tid

    if new_rows:
        with engine.begin() as c:
            pd.DataFrame(new_rows).to_sql("past_fixtures", c, if_exists="append",
                                          index=False, method="multi", chunksize=500)
    if new_teams:
        with engine.begin() as c:
            pd.DataFrame([{"team_name": k, "team_id": v} for k, v in new_teams.items()]).to_sql(
                "team_ids", c, if_exists="append", index=False, method="multi")

    return {"ok": True, "dias_consultados": dias_consultados, "novos_jogos": len(new_rows),
            "novos_times": len(new_teams), "ligas_rastreadas": len(tracked)}
