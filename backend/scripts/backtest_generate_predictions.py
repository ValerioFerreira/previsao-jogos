#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backtest_generate_predictions.py
=========================================
Etapa 4 (geracao) do modulo de backtest: roda o modelo CONGELADO
(model_artifacts_clubes_2025frozen/, ver backtest_train_frozen_model.py) sobre
toda partida de 2025 que aparece em `backtest_matched.parquet` (as que tem
correspondencia em `/data-test`), usando `Predictor.predict_from_row` (metodo
aditivo em predictor.py) -- ou seja, gera a previsao EXATAMENTE como o sistema
faria antes do jogo, sem o modelo ter visto esse jogo (nem a temporada 2025/26
inteira) durante o treino.

Uso: python scripts/backtest_generate_predictions.py
"""
from __future__ import annotations

import json
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

from predictor import Predictor  # noqa: E402
from scripts.battery_dataset import load_clubs_df  # noqa: E402

MATCHED = ROOT / "data" / "built" / "backtest_matched.parquet"
OUT = ROOT / "data" / "built" / "backtest_predictions.parquet"
FROZEN_ART = ROOT / "model_artifacts_clubes_2025frozen"


def main():
    print("=" * 80)
    print(" GERACAO DE PREVISOES -- modelo congelado 2025")
    print("=" * 80)

    if not FROZEN_ART.exists():
        raise SystemExit(f"Artefato congelado nao encontrado em {FROZEN_ART} -- "
                          f"rode scripts/backtest_train_frozen_model.py primeiro.")

    matched = pd.read_parquet(MATCHED)
    fixture_ids = sorted(set(matched.loc[matched["fixture_id"].notna(), "fixture_id"].astype("int64")))
    print(f"Partidas casadas com odds (fixture_id unicos): {len(fixture_ids)}")

    print(">> Carregando dataset de clubes (features point-in-time)...")
    df = load_clubs_df(min_matches=0)
    # fixture_id tem ~70 duplicatas em 272.918 linhas (reprocessamento de cache, achado
    # incidental) -- dedup defensivo antes de indexar por fixture_id (mesmo padrao usado
    # pro bug de tier2_goalkeeper_saves_test.py nesta sessao).
    df = df[df["fixture_id"].isin(fixture_ids)].drop_duplicates(subset=["fixture_id"]).reset_index(drop=True)
    print(f"Partidas encontradas no dataset para gerar previsao: {len(df)}")

    print(f">> Carregando Predictor congelado ({FROZEN_ART})...")
    predictor = Predictor(art_dir=str(FROZEN_ART))

    rows = []
    n_err = 0
    for i, row in df.iterrows():
        try:
            pred = predictor.predict_from_row(row)
        except Exception as e:
            n_err += 1
            if n_err <= 5:
                print(f"  [erro] fixture_id={row['fixture_id']}: {e}")
            continue
        rows.append({
            "fixture_id": int(row["fixture_id"]),
            "date": row["date"],
            "country": row["country"],
            "tournament": row["tournament"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "home_score": int(row["home_score"]),
            "away_score": int(row["away_score"]),
            "ht_home": row.get("ht_home"),
            "ht_away": row.get("ht_away"),
            "prediction_json": json.dumps(pred, ensure_ascii=False),
        })
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(df)}...")

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"\n>> {len(out)} previsoes geradas ({n_err} erros) -> {OUT}")


if __name__ == "__main__":
    main()
