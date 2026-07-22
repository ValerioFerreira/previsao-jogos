#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_match_games.py
================================
Etapa 4 do modulo de backtest local: casa cada partida de `/data-test`
(ja normalizada por backtest_odds_ingest.py) com uma partida REAL do nosso
proprio dataset (`club_features_enriched.parquet`, via
`scripts/battery_dataset.py::load_clubs_df`), por (pais+torneio, nomes
normalizados, data com tolerancia de +-1 dia -- fuso horario/registro podem
deslocar a data em 1 dia).

Gera:
  - data/built/backtest_matched.parquet (uma linha por partida casada, com o
    fixture_id do nosso lado)
  - data/reports/backtest_coverage.md (partidas encontradas/nao encontradas/
    % cobertura por liga, com o motivo de cada falha -- nao esconde nada)

Uso: python scripts/backtest_match_games.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.battery_dataset import load_clubs_df  # noqa: E402

ODDS = ROOT / "data" / "built" / "backtest_odds_normalized.parquet"
OUT_MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
OUT_COVERAGE = ROOT / "data" / "reports" / "backtest_coverage.md"

DATE_TOLERANCE_DAYS = 1


def main():
    print("=" * 80)
    print(" CASAMENTO DE PARTIDAS -- data-test x nosso dataset")
    print("=" * 80)

    odds = pd.read_parquet(ODDS)
    odds["date"] = pd.to_datetime(odds["date"])
    games = odds.drop_duplicates(
        subset=["source", "country", "tournament", "date", "home_team_raw", "away_team_raw"]
    )[["source", "div", "country", "tournament", "date", "home_team_raw", "away_team_raw",
       "home_team_norm", "away_team_norm", "covered"]].reset_index(drop=True)
    print(f"Partidas distintas em data-test: {len(games)}")

    ours = load_clubs_df(min_matches=0)
    ours["date"] = pd.to_datetime(ours["date"])
    # indice por (country, tournament, home, away) -> lista de (date, fixture_id)
    idx = {}
    cols = ours[["country", "tournament", "home_team", "away_team", "date", "fixture_id"]]
    for country, tournament, home_team, away_team, date, fixture_id in cols.itertuples(index=False, name=None):
        idx.setdefault((country, tournament, home_team, away_team), []).append((date, fixture_id))

    rows = []
    for g in games.itertuples(index=False):
        reason = None
        fixture_id = None
        day_diff = None
        if not g.covered:
            reason = "liga sem competicao equivalente coletada"
        elif pd.isna(g.home_team_norm) or pd.isna(g.away_team_norm):
            reason = "nome de time nao normalizado (falha no fuzzy/alias)"
        else:
            key = (g.country, g.tournament, g.home_team_norm, g.away_team_norm)
            candidates = idx.get(key, [])
            if not candidates:
                reason = "sem jogo correspondente no nosso dataset (nomes/torneio casaram, data nao)"
            else:
                best = min(candidates, key=lambda c: abs((c[0] - g.date).days))
                diff = abs((best[0] - g.date).days)
                if diff > DATE_TOLERANCE_DAYS:
                    reason = f"jogo mais proximo encontrado esta a {diff} dias (fora da tolerancia de {DATE_TOLERANCE_DAYS})"
                else:
                    fixture_id, day_diff = best[1], diff

        row = g._asdict()
        row["fixture_id"] = fixture_id
        row["day_diff"] = day_diff
        row["match_reason_if_failed"] = reason
        rows.append(row)

    out = pd.DataFrame(rows)
    OUT_MATCHED.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_MATCHED, index=False)

    matched = out["fixture_id"].notna()
    print(f"Casadas: {matched.sum()} / {len(out)} ({100*matched.mean():.1f}%)")

    # ---- relatorio de cobertura por liga ----
    lines = ["# Cobertura de casamento data-test x nosso dataset\n",
             f"Total de partidas distintas em `/data-test`: {len(out)}\n",
             f"Casadas com sucesso: {int(matched.sum())} ({100*matched.mean():.1f}%)\n",
             "\n## Por liga\n",
             "| Fonte | Liga | Pais | Torneio | Partidas | Casadas | % |",
             "|---|---|---|---|---|---|---|"]
    grp = out.groupby(["source", "div", "country", "tournament"], dropna=False)
    for (source, div, country, tournament), g in grp:
        n = len(g)
        m = g["fixture_id"].notna().sum()
        pct = 100 * m / n if n else 0.0
        lines.append(f"| {source} | {div} | {country} | {tournament} | {n} | {m} | {pct:.1f}% |")

    lines.append("\n## Motivos de falha (partidas nao casadas)\n")
    fail = out[~matched].copy()
    if len(fail):
        # Agrupa qualquer "fora da tolerancia de N dias" numa unica categoria (o numero
        # exato de dias varia por jogo e nao ajuda a leitura -- fica so o total).
        generic_reason = fail["match_reason_if_failed"].str.replace(
            r"^jogo mais proximo encontrado esta a \d+ dias", "fora da tolerancia de data", regex=True)
        reason_counts = generic_reason.value_counts()
        for reason, cnt in reason_counts.items():
            lines.append(f"- **{reason}**: {cnt} partidas")
        lines.append("\n### Detalhe por liga (top motivos)\n")
        for (source, div, country, tournament), g in fail.groupby(["source", "div", "country", "tournament"], dropna=False):
            top_reason = g["match_reason_if_failed"].value_counts().index[0]
            lines.append(f"- [{source}/{div}] {country}/{tournament}: {len(g)} falhas -- principal motivo: {top_reason}")
    else:
        lines.append("(nenhuma)")

    OUT_COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_COVERAGE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Relatorio de cobertura -> {OUT_COVERAGE}")


if __name__ == "__main__":
    main()
