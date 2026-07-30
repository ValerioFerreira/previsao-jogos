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
- Respeita o LIMITE DIÁRIO da API via `scripts/quota_tracker.py` (cota real lida do
  `GET /status`), não pelo header `x-ratelimit-requests-remaining` — esse header é
  POR MINUTO, e compará-lo contra uma margem fazia o script parar cedo por engano.
- Idempotente/resumível (pula o que já está no cache).

## Otimizações de 2026-07-30 (§28 do doc-mestre)

Este script estourava o `ExecutionTimeLimit` da tarefa agendada e era morto no meio,
impedindo os passos seguintes do `prefetch_wc.cmd` de rodarem por 16 dias. Duas causas,
ambas corrigidas aqui:

1. **Um round-trip ao Neon por fixture candidata** (`cache_get`). Agora as chaves do
   espelho local são carregadas de uma vez em memória (`raw_cache.local_keys()`) e o
   teste "já tenho?" é feito em RAM; o Neon só é consultado para o que falta.
2. **Re-listagem cega de 249 seleções × 17 temporadas todo dia** (~4.200 chamadas),
   mesmo com o histórico saturado. Agora um estado em `data/state/wc_seasons_done.json`
   marca os pares (seleção, temporada) já exauridos e os pula. Temporadas do ano
   corrente e do anterior nunca são marcadas como exauridas (ainda recebem jogos).

Uso:
  python scripts/prefetch_wc_data.py --all-nations --floor 2024   # diário (rápido)
  python scripts/prefetch_wc_data.py --all-nations --floor 2010   # varredura completa
  python scripts/prefetch_wc_data.py --ignore-state               # ignora o estado
"""
import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from app.services.fixture_fetch import BASE, _key, cache_get, cache_put
from app.services.predictor_service import _norm
from app.services import raw_cache
from scripts import quota_tracker

WC_LEAGUE, SEASON = 1, 2026
FINISHED = {"FT", "AET", "PEN"}
STATE_PATH = ROOT / "data" / "state" / "wc_seasons_done.json"


def load_seasons_done() -> set[str]:
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seasons_done(done: set[str]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[AVISO] nao consegui gravar {STATE_PATH.name}: {e}", flush=True)


def get(path, **params):
    """GET que devolve (response, remaining_int_or_None)."""
    quota_tracker.throttle()
    r = httpx.get(BASE + path, headers={"x-apisports-key": _key()}, params=params, timeout=30)
    r.raise_for_status()
    quota_tracker.note_call()
    return r.json().get("response", []), quota_tracker.remaining()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3000, help="máx. de chamadas de detalhe por execução")
    ap.add_argument("--margin", type=int, default=50, help="parar quando restarem < margem chamadas na cota")
    ap.add_argument("--floor", type=int, default=2010, help="temporada mais antiga a varrer por seleção (o detalhe da API rareia antes de ~2010)")
    ap.add_argument("--all-nations", action="store_true", help="além das seleções da Copa, varre TODAS as seleções com id em team_ids (usa a cota ociosa; cache-first)")
    ap.add_argument("--ignore-state", action="store_true", help="ignora wc_seasons_done.json e re-lista tudo")
    a = ap.parse_args()

    state = {"calls": 0, "novos": 0, "jacache": 0, "falhas": 0, "rem": quota_tracker.remaining(),
             "parou": None, "temporadas_puladas": 0}

    # Chaves já no espelho local, em memória: evita um round-trip ao Neon por fixture.
    local_keys = raw_cache.local_keys()
    print(f"Espelho local: {len(local_keys)} jogos já cacheados", flush=True)

    seasons_done = set() if a.ignore_state else load_seasons_done()
    if seasons_done:
        print(f"Estado: {len(seasons_done)} pares (selecao, temporada) já exauridos serão pulados", flush=True)

    def budget_ok():
        if state["calls"] >= a.max:
            state["parou"] = "MAX_POR_EXECUCAO"; return False
        if quota_tracker.remaining() <= a.margin:
            state["parou"] = "LIMITE_DIARIO"; return False
        return True

    def cache_fixture(fid, d10, h, a2):
        """Detalhe completo de uma fixture -> cache (se ainda não estiver)."""
        if not (fid and d10 and h and a2):
            return
        key = f"{d10}|{_norm(h)}|{_norm(a2)}"
        if key in local_keys:
            state["jacache"] += 1
            return
        if cache_get(key) is not None:
            local_keys.add(key)
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
                    raw_cache.local_put(key, fid, resp[0])   # espelho local (rebuild/precompute)
                    local_keys.add(key)
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
        this_year = _dt.date.today().year
        top_season = max(SEASON, this_year)
        seasons = list(range(top_season, a.floor - 1, -1))
        # Temporada corrente e a anterior nunca são "exauridas" — ainda entram jogos nelas.
        mutable_seasons = {this_year, this_year - 1, SEASON}
        print(f"Seleções: {len(teams)} | histórico completo temporadas {top_season}->{a.floor}...", flush=True)
        for tid in teams:
            if not budget_ok():
                break
            for season in seasons:
                if not budget_ok():
                    break
                pair = f"{tid}|{season}"
                if pair in seasons_done:
                    state["temporadas_puladas"] += 1
                    continue
                try:
                    fxs, rem = get("/fixtures", team=tid, season=season)
                    state["calls"] += 1
                    if rem is not None:
                        state["rem"] = rem
                except Exception as e:
                    print(f"  [AVISO] {tid}/{season}: {e}", flush=True); continue
                baixou_algo = False
                for f in fxs:
                    if not budget_ok():
                        break
                    fx = f.get("fixture") or {}; tt = f.get("teams") or {}
                    if ((fx.get("status") or {}).get("short")) in FINISHED:
                        antes = state["novos"]
                        cache_fixture(fx.get("id"), (fx.get("date") or "")[:10],
                                      (tt.get("home") or {}).get("name"), (tt.get("away") or {}).get("name"))
                        baixou_algo = baixou_algo or state["novos"] > antes
                # Marca o par como exaurido só se a listagem completou sem estourar o
                # orçamento, não baixou nada novo e a temporada já está fechada.
                if budget_ok() and not baixou_algo and season not in mutable_seasons:
                    seasons_done.add(pair)

    if not a.ignore_state:
        save_seasons_done(seasons_done)

    print(f">> Prefetch: {state['novos']} novos | {state['jacache']} já em cache | "
          f"{state['falhas']} falhas | {state['calls']} chamadas | "
          f"{state['temporadas_puladas']} temporadas puladas pelo estado | "
          f"cota ~{state['rem']} | parou por: {state['parou'] or 'FIM (tudo coberto)'}", flush=True)


if __name__ == "__main__":
    main()
