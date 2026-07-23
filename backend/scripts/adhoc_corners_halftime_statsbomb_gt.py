#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_statsbomb_gt.py
=================================================
Gabarito real de escanteios 1T/2T pra pesquisa de escanteios por tempo (ver
plano "Modelo de escanteios 1o/2o tempo"). footballdata.io e API-Football
NAO tem escanteio por tempo em lugar nenhum (confirmado no schema real de
ambos) -- pivo pro StatsBomb open data (github.com/hudl/open-data, ex-
StatsBomb, dados publicos/gratuitos, sem limite de chamada), que tem eventos
minuto-a-minuto com `pass.type.name == "Corner"` pra cada escanteio cobrado.

Cobertura StatsBomb usada aqui (competition_id, varios season_id): La Liga
(2010/11-2020/21, 11 temporadas), Champions League (2010/11-2018/19),
Bundesliga 2015/16, Ligue 1 (2015/16, 2021/22, 2022/23), Premier League
2015/16, Serie A 2015/16 -- todas dentro da janela 2010-2026 do nosso
dataset de clubes (club_features_enriched.parquet).

Pipeline:
  1. Baixa matches.json de cada competition/season (poucos arquivos, leve).
  2. Linka com nosso dataset por (home/away normalizado + data exata).
  3. Baixa events.json SO dos matches linkados, conta escanteios cobrados
     (pass.type.name=="Corner") por period (1=1T, 2=2T) pra cada lado.
  4. Salva gabarito em data/external/corners_halftime_ground_truth.parquet:
     fixture_id (nosso), statsbomb_match_id, home_corners_1t/2t,
     away_corners_1t/2t, home_corners_total/away_corners_total (cross-check
     vs. nosso home_cur_sb_corners/away_cur_sb_corners).

Uso: python scripts/adhoc_corners_halftime_statsbomb_gt.py [--limit N]
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "external"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RAW_BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data"

# (competition_id, season_id, nome do torneio como aparece no nosso dataset)
TARGET_COMPETITIONS = [
    (11, 90, "La Liga"), (11, 42, "La Liga"), (11, 4, "La Liga"), (11, 1, "La Liga"),
    (11, 2, "La Liga"), (11, 27, "La Liga"), (11, 26, "La Liga"), (11, 25, "La Liga"),
    (11, 24, "La Liga"), (11, 23, "La Liga"), (11, 22, "La Liga"),
    (16, 4, "Champions League"), (16, 1, "Champions League"), (16, 2, "Champions League"),
    (16, 27, "Champions League"), (16, 26, "Champions League"), (16, 25, "Champions League"),
    (16, 24, "Champions League"), (16, 23, "Champions League"), (16, 22, "Champions League"),
    (16, 21, "Champions League"),
    (9, 27, "Bundesliga"), (9, 281, "Bundesliga"),
    (7, 235, "Ligue 1"), (7, 108, "Ligue 1"), (7, 27, "Ligue 1"),
    (2, 27, "Premier League"), (2, 44, "Premier League"),
    (12, 27, "Serie A"),
    (44, 107, "Major League Soccer"),
    (1238, 108, "Indian Super League"),
]

# nome StatsBomb -> nome do torneio no nosso club_features_enriched.parquet
TOURNAMENT_MAP = {
    "La Liga": "La Liga",
    "Champions League": "Europa League",  # placeholder, corrigido abaixo
    "Bundesliga": "Bundesliga",
    "Ligue 1": "Ligue 1",
    "Premier League": "Premier League",
    "Serie A": "Serie A Italia",
}
# Champions League no nosso dataset provavelmente se chama "Champions League" --
# corrigido em runtime (ver _resolve_tournament_names)


def _norm_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = name.lower()
    name = re.sub(r"\bcf\b|\bfc\b|\bafc\b|\bsc\b|\bac\b|\bud\b|\bcd\b|\bclub de futbol\b", "", name)
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name


def _resolve_tournament_names(our_tournaments: set[str]) -> None:
    if "Champions League" in our_tournaments:
        TOURNAMENT_MAP["Champions League"] = "Champions League"
    elif "UEFA Champions League" in our_tournaments:
        TOURNAMENT_MAP["Champions League"] = "UEFA Champions League"


def fetch_json(path: str) -> dict | list | None:
    import json as _json
    url = f"{RAW_BASE}/{path}"
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        return None
    # r.json() deixa o requests adivinhar o encoding (as vezes erra -> mojibake
    # em nomes acentuados tipo "Atl�tico"/"Saint-�tienne") -- forcar utf-8.
    return _json.loads(r.content.decode("utf-8"))


def load_our_dataset() -> pd.DataFrame:
    df = pd.read_parquet(
        ROOT / "data" / "built" / "club_features_enriched.parquet",
        columns=["fixture_id", "date", "tournament", "home_team", "away_team",
                 "home_cur_sb_corners", "away_cur_sb_corners"],
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["home_norm"] = df["home_team"].str.split("#").str[0].map(_norm_name)
    df["away_norm"] = df["away_team"].str.split("#").str[0].map(_norm_name)
    return df


def link_matches(our_df: pd.DataFrame, limit: int) -> list[dict]:
    _resolve_tournament_names(set(our_df["tournament"].unique()))
    linked = []
    seen_fixtures = set()
    for comp_id, season_id, sb_name in TARGET_COMPETITIONS:
        if len(linked) >= limit:
            break
        our_name = TOURNAMENT_MAP.get(sb_name, sb_name)
        sub = our_df[our_df["tournament"] == our_name]
        if sub.empty:
            continue
        matches = fetch_json(f"matches/{comp_id}/{season_id}.json")
        if not matches:
            continue
        # index nosso dataset por (home_norm, away_norm, date) pra lookup O(1)
        idx = {}
        by_date = {}
        for _, row in sub.iterrows():
            idx.setdefault((row["home_norm"], row["away_norm"], row["date"]), row)
            by_date.setdefault(row["date"], []).append(row)

        def _find_row(home_norm, away_norm, mdate):
            row = idx.get((home_norm, away_norm, mdate))
            if row is not None:
                return row
            # fallback: nomes curtos da API-Football ("West Brom", "Leicester",
            # "Swansea") vs nomes oficiais completos do StatsBomb ("West
            # Bromwich Albion", "Leicester City", "Swansea City") -- containment
            # dentro da MESMA data (poucos jogos/dia por torneio, risco de
            # colisao baixo).
            candidates = by_date.get(mdate, [])
            for cand in candidates:
                h_ok = cand["home_norm"] == home_norm or cand["home_norm"] in home_norm or home_norm in cand["home_norm"]
                a_ok = cand["away_norm"] == away_norm or cand["away_norm"] in away_norm or away_norm in cand["away_norm"]
                if h_ok and a_ok:
                    return cand
            return None

        for m in matches:
            if len(linked) >= limit:
                break
            try:
                home_norm = _norm_name(m["home_team"]["home_team_name"])
                away_norm = _norm_name(m["away_team"]["away_team_name"])
                mdate = pd.to_datetime(m["match_date"]).date()
            except (KeyError, TypeError):
                continue
            row = _find_row(home_norm, away_norm, mdate)
            if row is None:
                continue
            if row["fixture_id"] in seen_fixtures:
                continue
            seen_fixtures.add(row["fixture_id"])
            linked.append({
                "fixture_id": row["fixture_id"],
                "statsbomb_match_id": m["match_id"],
                "tournament": our_name,
                "date": str(mdate),
                "home_team": m["home_team"]["home_team_name"],
                "away_team": m["away_team"]["away_team_name"],
                "our_home_corners_total": row["home_cur_sb_corners"],
                "our_away_corners_total": row["away_cur_sb_corners"],
            })
    return linked


def fetch_corner_counts(match_id: int) -> dict | None:
    events = fetch_json(f"events/{match_id}.json")
    if not events:
        return None
    counts: dict[tuple[str, int], int] = {}
    for ev in events:
        if ev.get("type", {}).get("name") == "Pass" and ev.get("pass", {}).get("type", {}).get("name") == "Corner":
            team = ev.get("team", {}).get("name", "?")
            period = ev.get("period", 1)
            key = (team, 1 if period <= 1 else 2)
            counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1200)
    args = parser.parse_args()

    out_path = OUT_DIR / "corners_halftime_ground_truth.parquet"
    existing = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame(columns=["fixture_id"])
    done_fixtures = set(existing["fixture_id"]) if len(existing) else set()
    print(f"Ja processados anteriormente: {len(done_fixtures)}")

    print("Carregando nosso dataset...")
    our_df = load_our_dataset()

    print("Linkando partidas StatsBomb <-> nosso dataset...")
    linked = link_matches(our_df, args.limit)
    linked = [l for l in linked if l["fixture_id"] not in done_fixtures]
    print(f"Linkados novos (nao processados ainda): {len(linked)}")

    if not linked:
        print("Nada novo pra processar -- gabarito ja cobre tudo que da pra linkar com esse limit.")
        return

    rows = []
    for i, link in enumerate(linked):
        counts = fetch_corner_counts(link["statsbomb_match_id"])
        if counts is None:
            continue
        home, away = link["home_team"], link["away_team"]
        row = dict(link)
        row["home_corners_1t"] = counts.get((home, 1), 0)
        row["home_corners_2t"] = counts.get((home, 2), 0)
        row["away_corners_1t"] = counts.get((away, 1), 0)
        row["away_corners_2t"] = counts.get((away, 2), 0)
        row["gt_home_total"] = row["home_corners_1t"] + row["home_corners_2t"]
        row["gt_away_total"] = row["away_corners_1t"] + row["away_corners_2t"]
        rows.append(row)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(linked)} eventos processados")

    new_out = pd.DataFrame(rows)
    out = pd.concat([existing, new_out], ignore_index=True) if len(existing) else new_out
    out.to_parquet(out_path, index=False)
    print(f"\nSalvo: {out_path} ({len(out)} linhas totais, {len(new_out)} novas)")

    # sanity check: total do StatsBomb vs. total ja registrado no nosso dataset
    if len(out) > 0:
        out["home_diff"] = (out["gt_home_total"] - out["our_home_corners_total"]).abs()
        out["away_diff"] = (out["gt_away_total"] - out["our_away_corners_total"]).abs()
        print(f"Diferenca media |StatsBomb - nosso| escanteio total: home={out['home_diff'].mean():.2f}, away={out['away_diff'].mean():.2f}")
        print(f"Fracao com diff<=1: home={(out['home_diff']<=1).mean():.1%}, away={(out['away_diff']<=1).mean():.1%}")


if __name__ == "__main__":
    main()
