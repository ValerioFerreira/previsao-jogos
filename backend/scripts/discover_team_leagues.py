#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/discover_team_leagues.py
=================================
Fecha uma lacuna real de cobertura (pedido do dono, 2026-08-01): `LEAGUES` +
`LEAGUES_EXPANSION_20260730` (`scripts/prefetch_clubs.py`) juntas listam só ~150
competições -- pode existir competição em que um time que já conhecemos (os 5589
`team_ids` de `model_artifacts_clubes/meta.json`) jogou e que NUNCA listamos, então
nenhuma coleta por liga (`prefetch_clubs*.py`) vai pegar esses jogos.

Usa `GET /leagues?team={id}` -- 1 chamada por time devolve TODAS as ligas/temporadas
que aquele time já disputou (bem mais barato que listar fixtures por time). Custo
total: ~5589 chamadas, uma fração pequena da cota diária (75000).

Ordem de processamento: Brasil -> Europa -> Sul-Americano -> Resto (mesma prioridade
de `LEAGUES_ALL_ORDERED`). Classifica cada time pela liga MAIS FREQUENTE em que ele
aparece no espelho local (`data/club_raw_cache.sqlite`, coluna `league_id` já
presente por fixture) -- é um proxy barato (não perfeito: um time pode ter mudado de
liga ao longo dos anos) mas suficiente pra priorização, não é uma classificação que
entra em modelo. Time sem nenhuma fixture no cache local cai no grupo "sem_dado"
(processado por último, ordem alfabética) -- não é crítico acertar a região desses.

Resumível: progresso salvo incrementalmente em `data/state/team_leagues_discovered.json`
(dict `{team_id: [league_id, ...]}`) -- um time já presente na próxima execução é
pulado. Ao final de cada execução (parada por `--max`, por cota, ou por ter processado
todos os times), regenera `data/reports/discover_team_leagues_gaps.json` comparando
TODO o conjunto de league_ids já descobertos (não só os desta execução) contra os ids
já cobertos por `LEAGUES_ALL_ORDERED` -- lista as ligas nunca vistas antes, com quantos
times já conhecidos jogaram nelas e um time de exemplo.

Uso:
    python scripts/discover_team_leagues.py [--max 5589] [--margin 2000]

Smoke test pequeno (não gasta cota de propósito):
    python scripts/discover_team_leagues.py --max 20 --margin 60000
"""
import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.fixture_fetch import _get  # noqa: E402
from scripts import quota_tracker  # noqa: E402
from scripts.prefetch_clubs import LEAGUES_ALL_ORDERED, LEAGUE_ID_TO_CATEGORY  # noqa: E402

META_PATH = BACKEND_ROOT / "model_artifacts_clubes" / "meta.json"
LOCAL_CACHE = BACKEND_ROOT / "data" / "club_raw_cache.sqlite"
STATE_PATH = BACKEND_ROOT / "data" / "state" / "team_leagues_discovered.json"
GAPS_REPORT_PATH = BACKEND_ROOT / "data" / "reports" / "discover_team_leagues_gaps.json"

_CATEGORY_ORDER = {"brasil": 0, "europa": 1, "sul_americano": 2, "resto": 3, "sem_dado": 4}


def _get_throttled(path, **params):
    """Mesmo padrão de `prefetch_clubs._get_throttled` -- throttle GLOBAL de cota via
    `quota_tracker` em torno da chamada crua `_get`. Não há put/flush aqui (não é
    cache de fixture, é descoberta de liga por time) -- só a chamada e o throttle são
    reaproveitados do módulo existente."""
    quota_tracker.throttle()
    result = _get(path, **params)
    quota_tracker.note_call()
    return result


def load_team_ids() -> dict[str, int]:
    with open(META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    return meta["team_ids"]


def _team_majority_league(local_cache: Path) -> dict[int, int]:
    """team_id -> league_id mais frequente no espelho local. Uma única query
    agregada (json_extract nos ids de casa/fora, união com o `league_id` que já é
    coluna própria da tabela) -- ~28s numa base de ~385k fixtures, custo único no
    início do processo, sem chamar a API."""
    if not local_cache.exists():
        print(f"[AVISO] {local_cache} não existe -- toda a fila cai em 'sem_dado' "
              "(ordem alfabética)", flush=True)
        return {}
    conn = sqlite3.connect(str(local_cache))
    try:
        rows = conn.execute(
            """
            SELECT tid, league_id, COUNT(*) FROM (
                SELECT json_extract(raw,'$.teams.home.id') AS tid, league_id FROM raw
                UNION ALL
                SELECT json_extract(raw,'$.teams.away.id') AS tid, league_id FROM raw
            )
            WHERE tid IS NOT NULL
            GROUP BY tid, league_id
            """
        ).fetchall()
    finally:
        conn.close()
    counts: dict[int, Counter] = defaultdict(Counter)
    for tid, league_id, n in rows:
        if tid is None or league_id is None:
            continue
        counts[int(tid)][int(league_id)] += n
    return {tid: c.most_common(1)[0][0] for tid, c in counts.items()}


def build_priority_order(team_ids: dict[str, int]) -> list[tuple[int, str]]:
    """Retorna [(team_id, nome), ...] na ordem Brasil -> Europa -> SulAmericano ->
    Resto -> sem_dado (proxy: liga mais frequente do time no cache local; sem dado
    local = "sem_dado", alfabético, não é crítico acertar)."""
    majority = _team_majority_league(LOCAL_CACHE)
    entries = []
    for nome, tid in team_ids.items():
        league_id = majority.get(tid)
        cat = LEAGUE_ID_TO_CATEGORY.get(league_id, "resto") if league_id is not None else "sem_dado"
        entries.append((tid, nome, cat))
    entries.sort(key=lambda t: (_CATEGORY_ORDER[t[2]], t[1].lower()))
    return [(tid, nome) for tid, nome, _cat in entries]


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    tmp.replace(STATE_PATH)  # escrita atômica -- nunca deixa o state file truncado a meio


def write_gaps_report(state: dict, team_ids: dict[str, int]) -> None:
    """Compara TODO o conjunto de league_ids já descobertos (não só os desta
    execução) contra LEAGUES_ALL_ORDERED. Escreve a lista de ligas nunca cobertas,
    ordenada pela quantidade de times conhecidos que já jogaram nelas (desc)."""
    id_to_name = {tid: nome for nome, tid in team_ids.items()}
    known_ids = {lid for lid, _nome in LEAGUES_ALL_ORDERED}
    league_team_count: Counter = Counter()
    league_example: dict[int, str] = {}
    for tid_str, league_ids in state.items():
        tid = int(tid_str)
        nome = id_to_name.get(tid, f"team#{tid}")
        for lid in league_ids:
            lid = int(lid)
            if lid in known_ids:
                continue
            league_team_count[lid] += 1
            league_example.setdefault(lid, nome)
    gaps = [
        {"league_id": lid, "aparece_em_N_times": n, "exemplo_de_time": league_example[lid]}
        for lid, n in league_team_count.most_common()
    ]
    GAPS_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GAPS_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(gaps, f, ensure_ascii=False, indent=2)
    print(f">> Gaps report: {len(gaps)} ligas nunca cobertas -> {GAPS_REPORT_PATH}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=5589,
                     help="teto de chamadas /leagues?team= nesta execucao (default: todos os times, ~5589)")
    ap.add_argument("--margin", type=int, default=2000,
                     help="para quando a cota diaria restante cai abaixo disso")
    ap.add_argument("--save-every", type=int, default=25,
                     help="grava o state file a cada N times processados (alem do fim da execucao)")
    a = ap.parse_args()

    team_ids = load_team_ids()
    print(f"{len(team_ids)} times conhecidos (model_artifacts_clubes/meta.json)", flush=True)
    order = build_priority_order(team_ids)
    state = load_state()
    print(f"Estado anterior: {len(state)} times já descobertos | fila restante: "
          f"{sum(1 for tid, _ in order if str(tid) not in state)}", flush=True)

    calls = 0
    novos = 0
    falhas = 0
    since_save = 0
    stop_reason = None
    for tid, nome in order:
        key = str(tid)
        if key in state:
            continue
        if calls >= a.max:
            stop_reason = "MAX"
            break
        if quota_tracker.remaining() <= a.margin:
            stop_reason = "LIMITE_DIARIO"
            break
        try:
            resp, _rem = _get_throttled("/leagues", team=tid)
            calls += 1
            league_ids = sorted({
                (entry.get("league") or {}).get("id")
                for entry in resp
                if (entry.get("league") or {}).get("id") is not None
            })
            state[key] = league_ids
            novos += 1
        except Exception as e:
            calls += 1
            falhas += 1
            print(f"  [AVISO] time {nome!r} (id {tid}): {e}", flush=True)
            continue  # não marca em `state` -- tenta de novo na próxima execução
        since_save += 1
        if since_save >= a.save_every:
            save_state(state)
            since_save = 0
        if novos % 200 == 0:
            print(f"  progresso: {novos} times novos | falhas={falhas} | chamadas={calls} | "
                  f"cota ~{quota_tracker.remaining()}", flush=True)

    save_state(state)
    print(f">> Descoberta: {novos} times novos | {falhas} falhas | {calls} chamadas | "
          f"cota ~{quota_tracker.remaining()} | parou por: {stop_reason or 'FIM (todos os times processados)'}",
          flush=True)

    write_gaps_report(state, team_ids)


if __name__ == "__main__":
    main()
