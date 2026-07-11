#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_wc_data.py
===========================
PREFETCH abrangente dos dados de partidas da Copa do Mundo, do MAIS RECENTE ao mais
antigo, gravando o detalhe completo (statistics/events/lineups/players — tudo numa só
chamada GET /fixtures?id=) no cache do Neon (match_detail_cache). Assim qualquer forma
de dado que o usuário peça na página Estatísticas já está no banco, sem consumir cota.

- Cobre: (1) todas as partidas da própria Copa (league=1); (2) as últimas N partidas de
  cada seleção participante (form/estatística de jogos fora da Copa também).
- Respeita o LIMITE DIÁRIO da API: para quando `x-ratelimit-requests-remaining` < MARGEM
  ou quando atinge MAX_POR_EXECUCAO. Idempotente/resumível (pula o que já está no cache).

Uso: python scripts/prefetch_wc_data.py [--max 3000] [--margin 50] [--recent 10]
Agendável diariamente (Task Scheduler).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.services.fixture_fetch import BASE, _key, cache_get, cache_put
from app.services.predictor_service import _norm

WC_LEAGUE, SEASON = 1, 2026
FINISHED = {"FT", "AET", "PEN"}


def get(path, **params):
    """GET que devolve (response, remaining_int_or_None)."""
    r = httpx.get(BASE + path, headers={"x-apisports-key": _key()}, params=params, timeout=30)
    r.raise_for_status()
    # Throttle: 450 req/min = 7.5 req/seg = 0.15s entre requests.
    time.sleep(0.15)
    rem = r.headers.get("x-ratelimit-requests-remaining")
    try:
        rem = int(rem) if rem is not None else None
    except ValueError:
        rem = None
    return r.json().get("response", []), rem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3000, help="máx. de chamadas de detalhe por execução")
    ap.add_argument("--margin", type=int, default=50, help="parar quando restarem < margem chamadas na cota")
    ap.add_argument("--floor", type=int, default=2010, help="temporada mais antiga a varrer por seleção (o detalhe da API rareia antes de ~2010)")
    ap.add_argument("--all-nations", action="store_true", help="além das seleções da Copa, varre TODAS as seleções com id em team_ids (usa a cota ociosa; cache-first)")
    a = ap.parse_args()

    state = {"calls": 0, "novos": 0, "jacache": 0, "falhas": 0, "rem": None, "parou": None}

    def budget_ok():
        if state["calls"] >= a.max:
            state["parou"] = "MAX_POR_EXECUCAO"; return False
        if state["rem"] is not None and state["rem"] <= a.margin:
            state["parou"] = "LIMITE_DIARIO"; return False
        return True

    def cache_fixture(fid, d10, h, a2):
        """Detalhe completo de uma fixture -> cache (se ainda não estiver)."""
        if not (fid and d10 and h and a2):
            return
        key = f"{d10}|{_norm(h)}|{_norm(a2)}"
        if cache_get(key) is not None:
            state["jacache"] += 1
            return
        if not budget_ok():
            return
        try:
            resp, rem = get("/fixtures", id=fid)
            state["calls"] += 1
            if rem is not None:
                state["rem"] = rem
            if resp:
                cache_put(key, fid, resp[0])           # Neon (on-demand match-detail)
                try:
                    from app.services import raw_cache
                    raw_cache.local_put(key, fid, resp[0])   # espelho local (rebuild/precompute)
                except Exception:
                    pass
                state["novos"] += 1
            else:
                state["falhas"] += 1
        except Exception as e:
            state["falhas"] += 1
            print(f"  [AVISO] fixture {fid}: {e}", flush=True)

    # 1) Todas as partidas da Copa, do mais recente ao mais antigo
    fixtures, rem = get("/fixtures", league=WC_LEAGUE, season=SEASON)
    state["rem"] = rem
    fixtures.sort(key=lambda f: ((f.get("fixture") or {}).get("date") or ""), reverse=True)
    teams = {}
    print(f"Copa {SEASON}: {len(fixtures)} fixtures | cota restante ~{rem}", flush=True)
    for f in fixtures:
        fx = f.get("fixture") or {}; tt = f.get("teams") or {}
        for side in ("home", "away"):
            t = tt.get(side) or {}
            if t.get("id"):
                teams[t["id"]] = t.get("name")
        if ((fx.get("status") or {}).get("short")) in FINISHED:
            cache_fixture(fx.get("id"), (fx.get("date") or "")[:10],
                          (tt.get("home") or {}).get("name"), (tt.get("away") or {}).get("name"))
        if not budget_ok():
            break

    # 1b) --all-nations: expande o conjunto para TODAS as seleções com id (não só as da
    #     Copa). Cache-first + guarda de cota fazem a cobertura crescer dia a dia usando a
    #     cota ociosa (75k/dia). Ordena as da Copa primeiro (já semeadas).
    if a.all_nations:
        try:
            from app.db.connection import engine
            from sqlalchemy import text as _t
            with engine.connect() as c:
                for name, tid in c.execute(_t("SELECT team_name, team_id FROM team_ids")).fetchall():
                    if tid is not None:
                        teams.setdefault(int(tid), name)
            print(f"All-nations: conjunto expandido para {len(teams)} seleções", flush=True)
        except Exception as e:
            print(f"[AVISO] all-nations seed: {e}", flush=True)

    # 2) HISTÓRICO COMPLETO de cada seleção: varre temporada a temporada, do mais
    #    recente ao mais antigo (SEASON -> --floor), cacheando o detalhe de cada jogo.
    #    Cache-first (pula o que já tem) e para no limite diário -> retoma no dia seguinte.
    if budget_ok():
        top_season = max(SEASON, __import__("datetime").date.today().year)
        seasons = list(range(top_season, a.floor - 1, -1))
        print(f"Seleções: {len(teams)} | histórico completo temporadas {top_season}->{a.floor}...", flush=True)
        for tid in teams:
            if not budget_ok():
                break
            for season in seasons:
                if not budget_ok():
                    break
                try:
                    fxs, rem = get("/fixtures", team=tid, season=season)
                    state["calls"] += 1
                    if rem is not None:
                        state["rem"] = rem
                except Exception as e:
                    print(f"  [AVISO] {tid}/{season}: {e}", flush=True); continue
                for f in fxs:
                    if not budget_ok():
                        break
                    fx = f.get("fixture") or {}; tt = f.get("teams") or {}
                    if ((fx.get("status") or {}).get("short")) in FINISHED:
                        cache_fixture(fx.get("id"), (fx.get("date") or "")[:10],
                                      (tt.get("home") or {}).get("name"), (tt.get("away") or {}).get("name"))

    print(f">> Prefetch: {state['novos']} novos | {state['jacache']} já em cache | "
          f"{state['falhas']} falhas | {state['calls']} chamadas | cota ~{state['rem']} "
          f"| parou por: {state['parou'] or 'FIM (tudo coberto)'}", flush=True)


if __name__ == "__main__":
    main()
