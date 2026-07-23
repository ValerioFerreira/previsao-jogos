#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/adhoc_corners_halftime_candidate_b_train.py
=====================================================
Runner do Candidato B (hazard/simulação de ritmo pré-jogo) pra pesquisa de
escanteios por tempo (1T/2T) de clube.

Contexto: o dataset de clubes (API-Football, 272918 jogos) não tem
escanteio por tempo em lugar nenhum (nem eventos "Corner", nem estatística
por tempo) — não existe alvo de treino real. Este candidato constrói uma
previsão heurística, fundamentada em literatura de event-history de
escanteios (ver docstring de research_clubs/corners_halftime/
candidate_b_hazard_sim.py), aplicando uma fração de 2º tempo sobre o TOTAL
de escanteios já validado (model_artifacts_clubes/corners_cascade_rfixo.joblib,
NÃO retreinado aqui). Outros 2 candidatos (A/C) usam abordagens diferentes,
independentes; a comparação/validação contra gabarito externo (StatsBomb
open data) é uma etapa posterior, fora do escopo deste script.

Universo: fixtures de La Liga / Champions League / Bundesliga / Ligue 1 /
Premier League / Serie A Italia em club_features_enriched.parquet.

Saída: data/reports/corners_halftime/candidate_b_predictions.csv (formato
LONGO: fixture_id, market in {home_1t,away_1t,home_2t,away_2t}, lambda, pmf
— 16 floats 0..15 separados por vírgula).

Uso: python scripts/adhoc_corners_halftime_candidate_b_train.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from research_clubs.corners_halftime.candidate_b_hazard_sim import (  # noqa: E402
    TOURNAMENTS, build_predictions,
)

FEATURES_PATH = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_PATH = ROOT / "data" / "reports" / "corners_halftime" / "candidate_b_predictions.csv"


def main():
    print("=" * 80)
    print(" CANDIDATO B — escanteios 1T/2T via hazard/simulação de ritmo pré-jogo")
    print("=" * 80)

    df_full = pd.read_parquet(FEATURES_PATH)
    print(f"Dataset completo: {len(df_full)} jogos")

    df_universe = df_full[df_full["tournament"].isin(TOURNAMENTS)].copy()
    print(f"Universo (6 competições-alvo): {len(df_universe)} fixtures")
    print(df_universe["tournament"].value_counts().to_string())

    out = build_predictions(df_universe, df_full)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.drop(columns=[], errors="ignore")[["fixture_id", "market", "lambda", "pmf"]].to_csv(
        OUT_PATH, index=False)
    print(f"\nSalvo em: {OUT_PATH} ({len(out)} linhas, {out['fixture_id'].nunique()} fixtures)")

    # ─── sanity check ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(" SANITY CHECK")
    print("=" * 80)

    n_fixtures = out["fixture_id"].nunique()
    print(f"(a) fixtures processados: {n_fixtures}")

    # atenção: `out` (formato longo) preserva a ordem original de df_universe
    # dentro de cada bloco de mercado, mas .pivot() ORDENA o índice resultante
    # por fixture_id — por isso realinhamos os totais de produção (que estão
    # na ordem original de df_universe) pelo índice de fixture_id antes de
    # comparar ponto-a-ponto.
    lam_total_home = pd.Series(out.attrs["lambda_total_home"],
                                index=df_universe["fixture_id"].to_numpy())
    lam_total_away = pd.Series(out.attrs["lambda_total_away"],
                                index=df_universe["fixture_id"].to_numpy())
    piv = out.pivot(index="fixture_id", columns="market", values="lambda")
    sum_home = piv["home_1t"] + piv["home_2t"]
    sum_away = piv["away_1t"] + piv["away_2t"]
    lam_total_home = lam_total_home.reindex(piv.index)
    lam_total_away = lam_total_away.reindex(piv.index)
    print(f"(b) media (home_1t+home_2t): {sum_home.mean():.4f}  "
          f"vs media lambda TOTAL mandante (producao): {lam_total_home.mean():.4f}")
    print(f"    media (away_1t+away_2t): {sum_away.mean():.4f}  "
          f"vs media mu TOTAL visitante (producao): {lam_total_away.mean():.4f}")
    max_abs_diff_home = np.max(np.abs(sum_home.to_numpy() - lam_total_home.to_numpy()))
    max_abs_diff_away = np.max(np.abs(sum_away.to_numpy() - lam_total_away.to_numpy()))
    print(f"    diferenca maxima absoluta (deveria ser ~0, e' so soma 1T+2T): "
          f"home={max_abs_diff_home:.6f} away={max_abs_diff_away:.6f}")

    frac_home = out.attrs["frac_2t_home"]
    frac_away = out.attrs["frac_2t_away"]
    frac_all = np.concatenate([frac_home, frac_away])
    print(f"(c) fracao media prevista de 2T: {frac_all.mean():.4f}")
    print(f"    fracao 2T mandante: media={frac_home.mean():.4f} "
          f"min={frac_home.min():.4f} max={frac_home.max():.4f} std={frac_home.std():.4f}")
    print(f"    fracao 2T visitante: media={frac_away.mean():.4f} "
          f"min={frac_away.min():.4f} max={frac_away.max():.4f} std={frac_away.std():.4f}")
    if frac_all.std() < 1e-4:
        print("    ALERTA: fracao praticamente constante -> curva virou baseline ingenuo!")
    else:
        print("    OK: curva varia por jogo (nao e' baseline constante).")


if __name__ == "__main__":
    main()
