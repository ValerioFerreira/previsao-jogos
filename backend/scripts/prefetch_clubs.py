#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/prefetch_clubs.py
=========================
PREFETCH do detalhe completo (statistics/events/lineups/players) dos jogos dos CLUBES —
a próxima adição ao sistema. Só roda com a cota OCIOSA (as seleções já saturaram; sobra
~70k/dia). Grava numa tabela SEPARADA `club_match_detail_cache` (com league_id) para NÃO
contaminar os modelos de seleção, que varrem apenas `match_detail_cache`.

Ordem de PRIORIDADE (Brasil primeiro, depois Europa) — cobre uma liga inteira antes de ir
para a próxima, do mais recente ao mais antigo. Cache-first (pula o que já tem), guarda de
cota (para na margem) e resumível — o backfill se completa ao longo dos dias.

Uso: python scripts/prefetch_clubs.py [--max 60000] [--margin 200] [--from 2026] [--to 2015]
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.services.fixture_fetch import _get
from scripts import quota_tracker

def _get_throttled(path, **params):
    """_get() com throttle GLOBAL de 440/min compartilhado entre threads (quota_tracker.throttle)
    -- ao contrário de um time.sleep fixo por chamada, isso permite paralelizar downloads
    (várias chamadas em voo ao mesmo tempo) sem estourar o limite por-minuto da api-football."""
    quota_tracker.throttle()
    result = _get(path, **params)
    quota_tracker.note_call()
    return result

# (league_id, nome) na ordem de prioridade: Brasil -> Europa -> [expansão 2026-07-15].
LEAGUES = [
    (71, "Brasileirao Serie A"),
    (72, "Brasileirao Serie B"),
    (73, "Copa do Brasil"),
    (39, "Premier League"),
    (140, "La Liga"),
    (135, "Serie A (Italia)"),
    (78, "Bundesliga"),
    (61, "Ligue 1"),
    (2, "Champions League"),
    (3, "Europa League"),
    (848, "Conference League"),
    (13, "Copa Libertadores"),
    (11, "Copa Sul-Americana"),
    # --- Expansão 2026-07-15: assinatura API-Football expira 2026-07-19 -- usar a cota
    # restante p/ diversificar geografia/estilo da pesquisa de clubes (branch `clubs`).
    # IDs confirmados via /leagues; box-score (stats) só cobre 2021+ nestas ligas.
    (88, "Eredivisie"),
    (94, "Primeira Liga"),
    (144, "Jupiler Pro League"),
    (179, "Premiership (Escocia)"),
    (203, "Super Lig"),
    (128, "Liga Profesional Argentina"),
    (262, "Liga MX"),
    (253, "Major League Soccer"),
    (307, "Pro League (Arabia Saudita)"),
    (40, "Championship (Inglaterra)"),
    (17, "AFC Champions League Elite"),
    (12, "CAF Champions League"),
    (16, "CONCACAF Champions League"),
    # --- Expansão 2026-07-18: assinatura expira 2026-07-19T01:21 UTC (última janela) --
    # IDs confirmados agora via /leagues (nomes/anos/cobertura de stats). Ordem = fama/
    # relevância editorial, para que se a cota acabar no meio, as ligas mais valiosas já
    # tenham sido cobertas primeiro.
    # Tier 1 -- grandes ligas asiáticas + 2as divisões dos "big five" europeus.
    (98, "J1 League (Japao)"),
    (169, "Chinese Super League"),
    (79, "2. Bundesliga (Alemanha)"),
    (141, "Segunda Division (Espanha)"),
    (62, "Ligue 2 (Franca)"),
    (136, "Serie B (Italia)"),
    (235, "Premier League (Russia)"),
    (292, "K League 1 (Coreia do Sul)"),
    # Tier 2 -- ligas europeias tradicionais de primeira divisao.
    (333, "Premier League (Ucrania)"),
    (207, "Super League (Suica)"),
    (218, "Bundesliga (Austria)"),
    (119, "Superliga (Dinamarca)"),
    (197, "Super League 1 (Grecia)"),
    (106, "Ekstraklasa (Polonia)"),
    (210, "HNL (Croacia)"),
    (103, "Eliteserien (Noruega)"),
    (113, "Allsvenskan (Suecia)"),
    (345, "Czech Liga (Chequia)"),
    # Tier 3 -- ligas sul-americanas de tradicao ainda nao cobertas.
    (268, "Primera Division Apertura (Uruguai)"),
    (270, "Primera Division Clausura (Uruguai)"),
    (239, "Primera A (Colombia)"),
    (265, "Primera Division (Chile)"),
    (242, "Liga Pro (Equador)"),
    (281, "Primera Division (Peru)"),
    (250, "Division Profesional Apertura (Paraguai)"),
    (252, "Division Profesional Clausura (Paraguai)"),
    (299, "Primera Division (Venezuela)"),
    (344, "Primera Division (Bolivia)"),
    # Tier 4 -- outras ligas notaveis.
    (188, "A-League (Australia)"),
    (233, "Premier League (Egito)"),
    (288, "Premier Soccer League (Africa do Sul)"),
    (383, "Ligat Ha'al (Israel)"),
    (305, "Stars League (Catar)"),
    (301, "Pro League (Emirados Arabes)"),
    # --- Expansão 2026-07-19: cota diária (Ultra, 75k) sobrando após backfill dos 60
    # ligas anteriores completar ("FIM tudo coberto"). Prioriza copas domésticas dos
    # "big five" europeus (fama alta, ainda não cobertas — só Copa do Brasil tinha
    # copa doméstica) + 2 ligas de mercado grande na Ásia. IDs confirmados via /leagues.
    (45, "FA Cup (Inglaterra)"),
    (181, "FA Cup (Escocia)"),
    (143, "Copa del Rey"),
    (81, "DFB Pokal"),
    (137, "Coppa Italia"),
    (66, "Coupe de France"),
    (323, "Indian Super League"),
    (296, "Thai League 1"),
    # --- Expansão 2026-07-21: cota do dia sobrando após os 68 confirmarem "tudo
    # coberto" (só gaps residuais). Prioriza 2as divisoes/copas domesticas dos
    # paises ja cobertos (mais provavel ter box-score decente, mesmo padrao
    # editorial dos tiers anteriores) + 1 liga sul-americana ainda ausente.
    # IDs confirmados via /leagues nesta sessao.
    (130, "Copa Argentina"),
    (129, "Primera Nacional (Argentina)"),
    (96, "Taca de Portugal"),
    (95, "Segunda Liga (Portugal)"),
    (80, "3. Liga (Alemanha)"),
    (75, "Serie C (Brasil)"),
    (304, "Liga Panamena de Futbol"),
    # --- Expansao 2026-07-22 (virada de cota UTC dentro da mesma sessao -- 75k
    # frescos): mais 8 competicoes de mercados ainda nao cobertos (Leste
    # Europeu, Africa, America Central, Sudeste Asiatico). IDs confirmados via
    # /leagues nesta sessao.
    (271, "NB I (Hungria)"),
    (570, "Premier League (Gana)"),
    (200, "Botola Pro (Marrocos)"),
    (162, "Primera Division (Costa Rica)"),
    (338, "Primera Division (Guatemala)"),
    (244, "Veikkausliiga (Finlandia)"),
    (172, "First League (Bulgaria)"),
    (274, "Liga 1 (Indonesia)"),
]
# ---------------------------------------------------------------------------------
# EXPANSAO 2026-07-30 -- competicoes de CLUBE masculino ainda nao coletadas, filtradas
# por cobertura real da API (`GET /leagues`): so entram temporadas com
# `coverage.fixtures.statistics_fixtures` E `coverage.fixtures.lineups`, que e o minimo
# que as nossas features exigem. Excluidas de proposito: competicoes de SELECAO (pertencem
# ao pipeline `prefetch_wc_data.py`), futebol feminino e categorias de base -- dinamicas
# diferentes, contaminariam o modelo masculino de clube.
#
# LISTA SEPARADA DE PROPOSITO. `LEAGUES` continua sendo o alvo de producao (odds forward,
# backfill de historico, `tournament_weights` do artefato). Coletar != treinar: estas
# entram no espelho local agora porque a assinatura da API vence em 2026-08-19 e odd/dado
# nao coletado e perda permanente; a decisao de inclui-las no treino passa pelo gate SS6.
#
# Ative com `--include-expansion`.
LEAGUES_EXPANSION_20260730 = [
    (41, "League One (England)"),                       # 11 temp 2015-2025, League
    (48, "League Cup (England)"),                       # 11 temp 2015-2025, Cup
    (219, "2. Liga (Austria)"),                         # 11 temp 2015-2025, League
    (283, "Liga I (Romania)"),                          # 11 temp 2016-2026, League
    (529, "Super Cup (Germany)"),                       # 11 temp 2015-2025, Cup
    (204, "1. Lig (Turkey)"),                           # 10 temp 2016-2025, League
    (206, "Turkiye Kupas (Turkey)"),                    # 10 temp 2016-2025, Cup
    (528, "Community Shield (England)"),                # 10 temp 2015-2025, Cup
    (556, "Super Cup (Spain)"),                         # 10 temp 2016-2025, Cup
    (42, "League Two (England)"),                       # 9 temp 2017-2025, League
    (547, "Super Cup (Italy)"),                         # 9 temp 2016-2025, Cup
    (286, "Super Liga (Serbia)"),                       # 8 temp 2019-2026, League
    (318, "1. Division (Cyprus)"),                      # 8 temp 2018-2025, League
    (20, "CAF Confederation Cup"),                      # 7 temp 2019-2025, Cup
    (46, "EFL Trophy (England)"),                       # 7 temp 2019-2025, Cup
    (89, "Eerste Divisie (Netherlands)"),               # 7 temp 2016-2025, League
    (90, "KNVB Beker (Netherlands)"),                   # 7 temp 2019-2025, Cup
    (114, "Superettan (Sweden)"),                       # 7 temp 2020-2026, League
    (332, "Super Liga (Slovakia)"),                     # 7 temp 2019-2025, League
    (475, "Paulista - A1 (Brazil)"),                    # 7 temp 2020-2026, League
    (15, "FIFA Club World Cup"),                        # 6 temp 2019-2025, Cup
    (97, "Taca da Liga (Portugal)"),                    # 6 temp 2019-2024, Cup
    (108, "Cup (Poland)"),                              # 6 temp 2019-2024, Cup
    (116, "Premier League (Belarus)"),                  # 6 temp 2020-2026, League
    (236, "First League (Russia)"),                     # 6 temp 2021-2026, League
    (237, "Cup (Russia)"),                              # 6 temp 2020-2025, Cup
    (526, "Trophee des Champions (France)"),            # 6 temp 2020-2025, Cup
    (543, "Super Cup (Netherlands)"),                   # 6 temp 2019-2024, Cup
    (551, "Super Cup (Turkey)"),                        # 6 temp 2020-2025, Cup
    (373, "1. SNL (Slovenia)"),                         # 5 temp 2019-2023, League
    (479, "Canadian Premier League (Canada)"),          # 5 temp 2020-2026, League
    (65, "Coupe de la Ligue (France)"),                 # 4 temp 2015-2019, Cup
    (212, "Cup (Croatia)"),                             # 4 temp 2019-2024, Cup
    (357, "Premier Division (Ireland)"),                # 4 temp 2023-2026, League
    (145, "Challenger Pro League (Belgium)"),           # 3 temp 2023-2025, League
    (185, "League Cup (Scotland)"),                     # 3 temp 2023-2026, Cup
    (504, "King's Cup (Saudi-Arabia)"),                 # 3 temp 2023-2025, Cup
    (714, "Cup (Egypt)"),                               # 3 temp 2022-2024, Cup
    (772, "Leagues Cup"),                               # 3 temp 2023-2025, Cup
    (389, "Premier League (Kazakhstan)"),               # 2 temp 2022-2023, League
    (624, "Carioca - 1 (Brazil)"),                      # 2 temp 2025-2026, League
    (1032, "Copa de la Liga Profesional (Argentina)"),  # 2 temp 2023-2024, League
    (134, "Torneo Federal A (Argentina)"),              # 1 temp 2026-2026, League
    (199, "Cup (Greece)"),                              # 1 temp 2025-2025, Cup
    (255, "USL Championship (USA)"),                    # 1 temp 2020-2020, League
    (256, "USL League Two (USA)"),                      # 1 temp 2026-2026, League
    (261, "National Division (Luxembourg)"),            # 1 temp 2025-2025, League
    (293, "K League 2 (South-Korea)"),                  # 1 temp 2020-2020, League
    (302, "League Cup (United-Arab-Emirates)"),         # 1 temp 2025-2025, Cup
    (327, "Erovnuli Liga (Georgia)"),                   # 1 temp 2026-2026, League
    (363, "Premier League (Ethiopia)"),                 # 1 temp 2025-2025, League
    (371, "First League (Macedonia)"),                  # 1 temp 2025-2025, League
    (404, "Campionato (San-Marino)"),                   # 1 temp 2025-2025, League
    (406, "Professional League (Oman)"),                # 1 temp 2025-2025, League
    (421, "Division di Honor (Aruba)"),                 # 1 temp 2025-2025, League
    (435, "Primera Division RFEF - Group 1 (Spain)"),   # 1 temp 2025-2025, League
    (436, "Primera Division RFEF - Group 2 (Spain)"),   # 1 temp 2025-2025, League
    (487, "First Amateur Division (Belgium)"),          # 1 temp 2025-2025, League
    (492, "Tweede Divisie (Netherlands)"),              # 1 temp 2025-2025, League
    (500, "FA Cup (Malaysia)"),                         # 1 temp 2025-2025, Cup
    (567, "Ligi kuu Bara (Tanzania)"),                  # 1 temp 2025-2025, League
    (588, "National League (Myanmar)"),                 # 1 temp 2025-2025, League
    (622, "Pernambucano - 1 (Brazil)"),                 # 1 temp 2025-2025, League
    (768, "Arab Club Champions Cup"),                   # 1 temp 2023-2023, Cup
    (813, "Elite Two (Cameroon)"),                      # 1 temp 2026-2026, League
    (1104, "Liga 3 (Georgia)"),                         # 1 temp 2026-2026, League
    (1232, "Copa De La Liga (Peru)"),                   # 1 temp 2026-2026, Cup
]

FINISHED = {"FT", "AET", "PEN"}
TABLE = "club_match_detail_cache"


def ensure_table():
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            "key TEXT PRIMARY KEY, fixture_id BIGINT, league_id INT, season INT, raw TEXT, "
            "cached_at TIMESTAMPTZ DEFAULT now())"
        ))


def cached_ids() -> set:
    from app.db.connection import engine
    with engine.connect() as c:
        rows = c.execute(text(f"SELECT fixture_id FROM {TABLE}")).fetchall()
    return {r[0] for r in rows if r[0] is not None}


_write_lock = threading.Lock()
_write_buffer: list[tuple] = []
_BUFFER_FLUSH_SIZE = 40  # lote -- 1 round-trip a cada N fixtures em vez de 1 por fixture


def put(fixture_id, league_id, season, raw):
    """Bufferiza em memória (thread-safe) em vez de gravar no Neon/sqlite a cada
    chamada -- o round-trip síncrono por fixture era o gargalo real do backfill
    (~1s/chamada vs ~0.14s do throttle de API), não a cota. flush_writes() drena o
    buffer em lote; chamar sempre ao final de um lote de downloads e no fim do
    processo (perda máxima em caso de crash: <_BUFFER_FLUSH_SIZE fixtures, re-baixadas
    no próximo resume -- cache-first, sem risco de inconsistência)."""
    key = f"club|{league_id}|{fixture_id}"
    with _write_lock:
        _write_buffer.append((key, fixture_id, league_id, season, raw))
        should_flush = len(_write_buffer) >= _BUFFER_FLUSH_SIZE
    if should_flush:
        flush_writes()


def flush_writes():
    global _write_buffer
    with _write_lock:
        if not _write_buffer:
            return
        batch = _write_buffer
        _write_buffer = []
    from app.db.connection import engine
    with engine.begin() as c:
        c.execute(text(
            f"INSERT INTO {TABLE} (key, fixture_id, league_id, season, raw, cached_at) "
            "VALUES (:k,:f,:l,:s,:r, now()) ON CONFLICT (key) DO UPDATE SET raw=EXCLUDED.raw, cached_at=now()"
        ), [{"k": k, "f": f, "l": l, "s": s, "r": json.dumps(r, ensure_ascii=False)} for k, f, l, s, r in batch])
    _local_put_batch(batch)


def _local_put_batch(batch):
    """Espelho local de clubes (data/club_raw_cache.sqlite) — os jobs pesados leem
    do disco em vez de puxar blobs do Neon (ARCHITECTURE.md §3.1). Silencioso em falha."""
    try:
        import sqlite3
        path = Path(__file__).resolve().parents[1] / "data" / "club_raw_cache.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS raw (key TEXT PRIMARY KEY, fixture_id INTEGER, "
            "league_id INTEGER, season INTEGER, raw TEXT)")
        conn.executemany(
            "INSERT OR REPLACE INTO raw(key, fixture_id, league_id, season, raw) VALUES (?,?,?,?,?)",
            [(k, f, l, s, json.dumps(r, ensure_ascii=False)) for k, f, l, s, r in batch])
        conn.commit()
        conn.close()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=60000)
    ap.add_argument("--margin", type=int, default=200)
    ap.add_argument("--from", dest="ffrom", type=int, default=2026)
    ap.add_argument("--to", dest="fto", type=int, default=2015)
    ap.add_argument("--include-expansion", action="store_true",
                    help="acrescenta LEAGUES_EXPANSION_20260730 (67 competicoes novas) ao alvo")
    ap.add_argument("--only-expansion", action="store_true",
                    help="coleta SOMENTE a lista de expansao (as 83 de producao ja estao saturadas)")
    a = ap.parse_args()

    targets = list(LEAGUES)
    if a.only_expansion:
        targets = list(LEAGUES_EXPANSION_20260730)
    elif a.include_expansion:
        targets = targets + list(LEAGUES_EXPANSION_20260730)

    ensure_table()
    have = cached_ids()
    state = {"calls": 0, "novos": 0, "jacache": len(have), "falhas": 0, "rem": None, "parou": None}

    def budget_ok():
        if state["calls"] >= a.max:
            state["parou"] = "MAX"; return False
        if quota_tracker.remaining() <= a.margin:
            state["parou"] = "LIMITE_DIARIO"; return False
        return True

    print(f"Clubs prefetch | ja em cache: {len(have)} fixtures | {len(targets)} ligas alvo", flush=True)
    for league_id, nome in targets:
        if not budget_ok():
            break
        print(f"== Liga {nome} ({league_id}) ==", flush=True)
        for season in range(a.ffrom, a.fto - 1, -1):
            if not budget_ok():
                break
            try:
                fxs, rem = _get_throttled("/fixtures", league=league_id, season=season)
                state["calls"] += 1
                if rem is not None:
                    state["rem"] = int(rem)
            except Exception as e:
                print(f"  [AVISO] {nome}/{season}: {e}", flush=True); continue
            finished = [f for f in fxs if ((f.get("fixture") or {}).get("status") or {}).get("short") in FINISHED]
            todo = [f for f in finished if (f.get("fixture") or {}).get("id") not in have]
            print(f"  {season}: {len(finished)} encerrados, {len(todo)} a baixar | cota ~{state['rem']}", flush=True)
            for f in todo:
                if not budget_ok():
                    break
                fid = (f.get("fixture") or {}).get("id")
                if not fid:
                    continue
                try:
                    resp, rem = _get_throttled("/fixtures", id=fid)
                    state["calls"] += 1
                    if rem is not None:
                        state["rem"] = int(rem)
                    if resp:
                        put(fid, league_id, season, resp[0]); have.add(fid); state["novos"] += 1
                    else:
                        state["falhas"] += 1
                except Exception as e:
                    state["falhas"] += 1
                    print(f"    [AVISO] fixture {fid}: {e}", flush=True)

    flush_writes()
    print(f">> Clubs: {state['novos']} novos | {state['falhas']} falhas | {state['calls']} chamadas | "
          f"cota ~{quota_tracker.remaining()} | parou por: {state['parou'] or 'FIM (tudo coberto)'}", flush=True)


if __name__ == "__main__":
    main()
