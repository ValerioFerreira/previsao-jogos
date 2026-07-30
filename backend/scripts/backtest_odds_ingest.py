#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_odds_ingest.py
================================
Etapa 3 do modulo de backtest local: le TODOS os arquivos de `/data-test`
(22 CSVs football-data.co.uk, temporada 2025/26 + `new_leagues_data.xlsx`,
16 competicoes extras com historico 2012-2026, so 1X2 de fechamento) e produz
um unico parquet normalizado (long format), sem assumir layout -- as colunas
de odds sao detectadas por PADRAO DE SUFIXO (nao por lista fixa de casas), a
liga por um mapa de configuracao (`backtest_league_map.json`, editavel sem
tocar codigo), e o nome do time por alias conhecido + fallback fuzzy contra
os nomes REAIS do nosso proprio dataset (nao contra uma lista generica).

Uso: python scripts/backtest_odds_ingest.py [--year 2025]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_TEST = ROOT.parent / "data-test"
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.battery_dataset import load_clubs_df  # noqa: E402

LEAGUE_MAP = json.load(open(Path(__file__).with_name("backtest_league_map.json"), encoding="utf-8"))

OUT_ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_LOG = ROOT / "data" / "reports" / "backtest_team_matching.log"

# Colunas de identificacao/estatistica de jogo (schema documentado em data-test/notes.txt),
# NAO sao odds -- excluidas antes de aplicar a regex de deteccao de mercado. Isto e o
# schema fixo do PROVEDOR (football-data.co.uk), nao uma lista de casas de apostas.
NON_ODDS_COLS = {
    "Div", "Date", "Time", "HomeTeam", "AwayTeam", "Attendance", "Referee",
    "FTHG", "HG", "FTAG", "AG", "FTR", "Res", "HTHG", "HTAG", "HTR",
    "HS", "AS", "HST", "AST", "HHW", "AHW", "HC", "AC", "HF", "AF",
    "HFKC", "AFKC", "HO", "AO", "HY", "AY", "HR", "AR", "HBP", "ABP",
}
# Contadores de casas (nao sao odds/linhas, so metadado do agregador Betbrain).
COUNT_COLS = {"Bb1X2", "BbOU", "BbAH"}


def detect_market(col: str):
    """Classifica uma coluna de odds por padrao de SUFIXO (nao lista fixa de casas).
    Retorna dict {market, side?, book, closing} ou None se nao for coluna de odds."""
    if col in NON_ODDS_COLS or col in COUNT_COLS:
        return None
    m = re.match(r"^(.*?)(C?)AHH$", col)
    if m:
        return {"market": "handicap", "side": "H", "book": m.group(1), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)AHA$", col)
    if m:
        return {"market": "handicap", "side": "A", "book": m.group(1), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)AHh$", col)
    if m:
        return {"market": "handicap_line", "book": (m.group(1) or "market"), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)AH$", col)
    if m and m.group(1):
        return {"market": "handicap_line", "book": m.group(1), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)>2\.5$", col)
    if m:
        return {"market": "ou25", "side": "over", "book": m.group(1), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)<2\.5$", col)
    if m:
        return {"market": "ou25", "side": "under", "book": m.group(1), "closing": bool(m.group(2))}
    m = re.match(r"^(.*?)(C?)([HDA])$", col)
    if m and m.group(1):
        return {"market": "1x2", "side": m.group(3), "book": m.group(1), "closing": bool(m.group(2))}
    return None


def build_team_candidates():
    """Nomes de time REAIS do nosso dataset, agrupados por (country, tournament) --
    usados como universo do fallback fuzzy (muito mais preciso que uma lista generica)."""
    df = load_clubs_df(min_matches=0)
    cand = {}
    for (country, tournament), g in df.groupby(["country", "tournament"]):
        names = set(g["home_team"]) | set(g["away_team"])
        cand.setdefault((country, tournament), set()).update(names)
    return cand


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def norm_team_name(raw: str, country: str, tournament: str, candidates: dict,
                    aliases: dict, log: list) -> str | None:
    """Ordem: exato -> alias explicito -> SUBSTRING bidirecional, sem acento (nome
    curto/apelido dentro do nome oficial ou vice-versa, ex. 'Dortmund' em 'Borussia
    Dortmund', 'Rangers' em 'Rangers (Premiership)', 'FC Koln' em '1. FC Köln') ->
    fuzzy por caracteres (so como ultimo recurso, ver nota abaixo).

    O ratio de similaridade de caracteres (difflib) por si so erra nos dois sentidos:
    apelidos curtos de nomes longos pontuam BAIXO (ex. 'Dortmund' vs 'Borussia Dortmund'
    = 0.62, abaixo de qualquer corte razoavel) e nomes curtos NAO relacionados podem
    pontuar ALTO por acaso (ex. 'Paris SG' vs 'Paris FC' = 0.75, mais alto que o
    correto 'Paris Saint Germain' = 0.59 -- achado real desta sessao, ver
    backtest_league_map.json::team_aliases). Por isso substring entra ANTES do fuzzy:
    resolve a maioria dos apelidos sem o risco do fuzzy, e o fuzzy so cobre o que sobra."""
    raw = raw.strip()
    alias = aliases.get(raw)
    if alias:
        log.append((country, tournament, raw, alias, "alias"))
        return alias
    pool = candidates.get((country, tournament), set())
    if raw in pool:
        return raw
    if len(raw) >= 3:
        raw_n = _strip_accents(raw)
        subs = [c for c in pool if raw_n in _strip_accents(c) or _strip_accents(c) in raw_n]
        if subs:
            best = min(subs, key=lambda c: abs(len(c) - len(raw)))
            log.append((country, tournament, raw, best, "substring"))
            return best
    if pool:
        close = difflib.get_close_matches(raw, list(pool), n=1, cutoff=0.72)
        if close:
            log.append((country, tournament, raw, close[0], "fuzzy"))
            return close[0]
    log.append((country, tournament, raw, None, "falha"))
    return None


def _csv_paths(include_historical: bool):
    """(caminho, temporada) de cada CSV do football-data.

    `data-test/*.csv` e a temporada corrente (sem pasta). `data-test/historical/<AABB>/<DIV>.csv`
    sao as 16 temporadas baixadas em 2026-07-30 por `scripts/fetch_historical_odds.py` -- mesmo
    provedor, mesmo schema, mesmo `div` no nome do arquivo, entao o `backtest_league_map.json`
    vale sem alteracao. Antes desta mudanca o glob era so o plano e as 305 temporadas historicas
    ficavam invisiveis para o backtest (ver DOCUMENTACAO_CENTRAL.md secao 28.3).
    """
    out = [(p, "atual") for p in sorted(DATA_TEST.glob("*.csv"))]
    if include_historical:
        out += [(p, p.parent.name) for p in sorted(DATA_TEST.glob("historical/*/*.csv"))]
    return out


def ingest_csvs(candidates, aliases, log, include_historical: bool = True):
    rows = []
    for path, season in _csv_paths(include_historical):
        div = path.stem
        cfg = LEAGUE_MAP["csv_div"].get(div)
        if cfg is None:
            print(f"  [aviso] Div '{div}' sem entrada em backtest_league_map.json -- pulando")
            continue
        country, tournament = cfg["country"], cfg["tournament"]
        # Temporadas antigas trazem bytes que nao sao cp1252 valido; latin-1 nunca falha e
        # cobre o mesmo repertorio para os nomes de time deste provedor.
        try:
            df = pd.read_csv(path, encoding="cp1252", low_memory=False, on_bad_lines="skip")
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="latin-1", low_memory=False, on_bad_lines="skip")
        if "Date" not in df.columns or "HomeTeam" not in df.columns:
            print(f"  [aviso] {season}/{div}: sem colunas Date/HomeTeam -- pulando")
            continue
        df = df[df["HomeTeam"].notna()]
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

        markets = {}
        for col in df.columns:
            info = detect_market(col)
            if info:
                markets.setdefault(col, info)

        for _, r in df.iterrows():
            if pd.isna(r["Date"]):
                continue
            home_norm = norm_team_name(str(r["HomeTeam"]), country, tournament, candidates, aliases, log)
            away_norm = norm_team_name(str(r["AwayTeam"]), country, tournament, candidates, aliases, log)
            base = dict(source="csv", div=div, season=season, country=country, tournament=tournament,
                        date=r["Date"], home_team_raw=r["HomeTeam"], away_team_raw=r["AwayTeam"],
                        home_team_norm=home_norm, away_team_norm=away_norm, covered=cfg["covered"])
            for col, info in markets.items():
                val = pd.to_numeric(r.get(col), errors="coerce")
                if pd.isna(val):
                    continue
                row = dict(base)
                row.update(market=info["market"], side=info.get("side"), book=info["book"],
                           closing=info["closing"], value=float(val))
                rows.append(row)
        print(f"  {div} ({country}/{tournament}): {len(df)} jogos, {len(markets)} colunas de odds detectadas")
    return rows


def ingest_xlsx(candidates, aliases, log, year: int):
    xlsx_path = DATA_TEST / "new_leagues_data.xlsx"
    if not xlsx_path.exists():
        return []
    sheets = pd.read_excel(xlsx_path, sheet_name=None)
    rows = []
    tournament_aliases = LEAGUE_MAP.get("tournament_aliases", {})
    for sheet, df in sheets.items():
        cfg = LEAGUE_MAP["xlsx_sheet"].get(sheet)
        if cfg is None:
            print(f"  [aviso] aba '{sheet}' sem entrada em backtest_league_map.json -- pulando")
            continue
        country = cfg["country"]
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        df = df[df["Date"].dt.year == year]
        if df.empty:
            continue
        markets = {}
        for col in df.columns:
            info = detect_market(col)
            if info:
                markets.setdefault(col, info)

        alias_map = tournament_aliases.get(country, {})
        for _, r in df.iterrows():
            raw_tourn = str(r["League"]).strip()
            tournament = alias_map.get(raw_tourn, raw_tourn)
            home_norm = norm_team_name(str(r["Home"]), country, tournament, candidates, aliases, log)
            away_norm = norm_team_name(str(r["Away"]), country, tournament, candidates, aliases, log)
            base = dict(source="xlsx", div=sheet, country=country, tournament=tournament,
                        date=r["Date"], home_team_raw=r["Home"], away_team_raw=r["Away"],
                        home_team_norm=home_norm, away_team_norm=away_norm, covered=cfg["covered"])
            for col, info in markets.items():
                val = pd.to_numeric(r.get(col), errors="coerce")
                if pd.isna(val):
                    continue
                row = dict(base)
                row.update(market=info["market"], side=info.get("side"), book=info["book"],
                           closing=info["closing"], value=float(val))
                rows.append(row)
        print(f"  {sheet} ({country}, ano {year}): {len(df)} jogos, {len(markets)} colunas de odds")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2025,
                    help="Filtro de ano p/ o xlsx (historico 2012-2026); os CSVs entram inteiros.")
    ap.add_argument("--no-historical", action="store_true",
                    help="ignora data-test/historical/ e le so a temporada corrente")
    a = ap.parse_args()

    print("=" * 80)
    print(" INGESTAO DE ODDS -- data-test (CSVs + xlsx)")
    print("=" * 80)
    aliases = LEAGUE_MAP.get("team_aliases", {})
    log = []

    print(">> Carregando nomes de time reais do nosso dataset (universo do fuzzy match)...")
    candidates = build_team_candidates()

    n_hist = len(list(DATA_TEST.glob("historical/*/*.csv")))
    print(f">> Lendo CSVs: temporada corrente"
          f"{'' if a.no_historical else f' + {n_hist} arquivos historicos'}...")
    rows_csv = ingest_csvs(candidates, aliases, log, include_historical=not a.no_historical)

    print(f">> Lendo new_leagues_data.xlsx (filtrado para ano {a.year})...")
    rows_xlsx = ingest_xlsx(candidates, aliases, log, a.year)

    rows = rows_csv + rows_xlsx
    out = pd.DataFrame(rows)
    OUT_ODDS.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_ODDS, index=False)
    print(f"\n>> {len(out)} linhas de odds normalizadas -> {OUT_ODDS}")

    log_df = pd.DataFrame(log, columns=["country", "tournament", "raw", "matched", "method"])
    log_df = log_df.drop_duplicates()
    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write("# Log de normalizacao de nomes de time (data-test -> nosso dataset)\n\n")
        for method in ("alias", "fuzzy", "falha"):
            sub = log_df[log_df["method"] == method]
            f.write(f"## {method} ({len(sub)} decisoes)\n")
            for _, r in sub.iterrows():
                f.write(f"- [{r['country']}/{r['tournament']}] '{r['raw']}' -> {r['matched']}\n")
            f.write("\n")
    n_falha = (log_df["method"] == "falha").sum()
    print(f">> Log de normalizacao de times -> {OUT_LOG} ({n_falha} falhas de match, ver arquivo)")


if __name__ == "__main__":
    main()
