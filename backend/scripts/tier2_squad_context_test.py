#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier2_squad_context_test.py
=====================================
Fase 5 do PLANO 7 -- gate §6 nas squad_context_features (backend/data/built/
squad_context_features.parquet, 326.386 linhas, custo ZERO de cota -- ver
backend/scripts/build_squad_context_features.py e MANIFEST.yaml). Mesmo
protocolo/template de scripts/tier2_shot_quality_test.py: 5 folds temporais,
170 feats de producao (base_feats_170()) + candidato vs baseline (170 sem o
candidato), controle negativo (embaralha a feature no treino do ultimo fold).

4 candidatos, testados UM DE CADA VEZ (nunca juntos -- e o que o PLANO 7 pede,
pra atribuir credito a cada um separadamente):
  coach      -- mandato de tecnico (matches/days/is_new/changed_last)
  formation  -- estabilidade de formacao (stability/changed_last)
  squad      -- continuidade de elenco (continuity/core_size)
  injuries   -- desfalques da PROPRIA partida (has_data/missing/questionable
                -- excecao declarada de usar dado da partida atual, e
                informacao publica PRE-jogo, nao vazamento de resultado)

Uso: python -m scripts.tier2_squad_context_test --candidate coach
     python -m scripts.tier2_squad_context_test --candidate formation
     python -m scripts.tier2_squad_context_test --candidate squad
     python -m scripts.tier2_squad_context_test --candidate injuries
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (
    temporal_folds, multiclass_logloss, ece_multiclass, accuracy, compare, FoldResult,
)
from scripts.battery_dataset import load_clubs_df, base_feats_170, DC_PARAMS

SQUAD_FEATURES = ROOT / "data" / "built" / "squad_context_features.parquet"
Y_MAP = {"H": 0, "D": 1, "A": 2}

CANDIDATES = {
    "coach": ["home_coach_matches", "home_coach_days", "home_coach_is_new", "home_coach_changed_last",
              "away_coach_matches", "away_coach_days", "away_coach_is_new", "away_coach_changed_last"],
    "formation": ["home_formation_stability", "home_formation_changed_last",
                  "away_formation_stability", "away_formation_changed_last"],
    "squad": ["home_squad_continuity", "home_squad_core_size",
              "away_squad_continuity", "away_squad_core_size"],
    "injuries": ["home_inj_has_data", "home_inj_missing", "home_inj_questionable",
                 "away_inj_has_data", "away_inj_missing", "away_inj_questionable"],
}


def fit_and_predict(tr, te, feats, random_state=42):
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": random_state})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats])
    return probs["result"][:, ::-1]  # [A,D,H] -> [H,D,A]


def evaluate(df, feats, label):
    results = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        t0 = time.time()
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        p = fit_and_predict(tr, te, feats)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        metrics = {
            "logloss": multiclass_logloss(y_idx, p),
            "ece": ece_multiclass(y_idx, p),
            "accuracy": accuracy(y_idx, p),
        }
        results.append(FoldResult(fold=fold, n_test=len(te), metrics=metrics))
        print(f"  [{label}][{fold}] n={len(te)} logloss={metrics['logloss']:.4f} "
              f"ece={metrics['ece']:.4f} ({time.time()-t0:.1f}s)", flush=True)
    return results


def negative_control(df, feats_cand, new_cols, seed=42):
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    tr, te = df.loc[tr_idx].copy(), df.loc[te_idx]

    p_normal = fit_and_predict(tr, te, feats_cand, seed)
    y_idx = te["result"].map(Y_MAP).to_numpy()
    ll_normal = multiclass_logloss(y_idx, p_normal)

    rng = np.random.RandomState(seed)
    perm = rng.permutation(len(tr))
    tr_shuffled = tr.copy()
    for c in new_cols:
        tr_shuffled[c] = tr[c].to_numpy()[perm]

    p_shuf = fit_and_predict(tr_shuffled, te, feats_cand, seed)
    ll_shuf = multiclass_logloss(y_idx, p_shuf)

    out = {
        "fold": fold_name,
        "logloss_candidato_normal": ll_normal,
        "logloss_candidato_feature_embaralhada": ll_shuf,
        "diferenca": ll_shuf - ll_normal,
        "veredito": ("OK -- ganho desaparece com a feature embaralhada"
                     if ll_shuf >= ll_normal - 0.0005
                     else "SUSPEITO -- feature embaralhada ainda ganha, investigar vazamento"),
    }
    print(f">> controle negativo: normal={ll_normal:.4f} embaralhada={ll_shuf:.4f} -> {out['veredito']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", choices=list(CANDIDATES.keys()), required=True)
    a = ap.parse_args()
    new_cols = CANDIDATES[a.candidate]

    out_dir = ROOT / "data" / "reports" / f"tier2_squad_context_{a.candidate}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"TIER 2 -- squad_context_features / candidato={a.candidate} (Fase 5, PLANO 7)")
    print("=" * 80)

    df = load_clubs_df(min_matches=0)
    sq = pd.read_parquet(SQUAD_FEATURES)
    df = df.merge(sq, on="fixture_id", how="inner", suffixes=("", "_sq"))
    print(f"Base casada: {len(df)} jogos (de {len(sq)} em squad_context_features)", flush=True)

    missing = [c for c in new_cols if c not in df.columns]
    if missing:
        print(f"!! ERRO: colunas ausentes apos merge: {missing}")
        sys.exit(1)

    cov = df[new_cols].notna().all(axis=1).mean()
    print(f"Cobertura (todas as colunas do candidato nao-nulas): {cov:.1%} de {len(df)} jogos", flush=True)

    feats_base = base_feats_170()
    feats_cand = feats_base + new_cols

    df_imp = df.copy()
    for c in new_cols:
        df_imp[c] = df_imp[c].fillna(df_imp[c].median())

    print(f"\n>> Avaliando baseline (170 feats) vs candidato (170 + {a.candidate})...", flush=True)
    base_results = evaluate(df_imp, feats_base, "baseline")
    cand_results = evaluate(df_imp, feats_cand, "candidato")

    cmp_logloss = compare(base_results, cand_results, metric="logloss")
    cmp_ece = compare(base_results, cand_results, metric="ece")
    cmp_logloss.to_csv(out_dir / "fold_comparison_logloss.csv", index=False)
    cmp_ece.to_csv(out_dir / "fold_comparison_ece.csv", index=False)
    print("\n--- LOG-LOSS (candidato vs baseline) ---")
    print(cmp_logloss.to_string(index=False))
    print("\n--- ECE (candidato vs baseline) ---")
    print(cmp_ece.to_string(index=False))

    n_folds_melhora = int(cmp_logloss.iloc[:-1]["melhora"].sum())
    n_folds = len(cmp_logloss) - 1
    mean_delta_ll = cmp_logloss.iloc[-1]["delta"]
    mean_delta_ece = cmp_ece.iloc[-1]["delta"]

    print("\n>> Controle negativo (feature embaralhada no ultimo fold)...", flush=True)
    neg_ctrl = negative_control(df_imp, feats_cand, new_cols)
    (out_dir / "negative_control.json").write_text(
        json.dumps(neg_ctrl, ensure_ascii=False, indent=2), encoding="utf-8")

    gate_pass = (n_folds_melhora >= 4) and (mean_delta_ll < -0.001) and (mean_delta_ece < 0.005)

    veredito = f"""# Tier 2 -- squad_context_features / candidato: {a.candidate} -- veredito

## Colunas testadas
{new_cols}

## Cobertura
{cov:.1%} de {len(df)} jogos casados (fixture_id) com squad_context_features.parquet.

## Gate (research_clubs/protocol.py, 5 folds temporais)
170 feats de producao (base_feats_170()) + {a.candidate} vs baseline (170 sem o candidato).

- Folds com melhora de log-loss: **{n_folds_melhora}/{n_folds}**
- Delta medio de log-loss (candidato - baseline): **{mean_delta_ll:.5f}**
- Delta medio de ECE (candidato - baseline): **{mean_delta_ece:.5f}**

Criterio: >=4/5 folds com melhora E delta medio de log-loss < -0.001 E ECE nao piora de forma relevante.

## Controle negativo
normal={neg_ctrl['logloss_candidato_normal']:.4f} embaralhada={neg_ctrl['logloss_candidato_feature_embaralhada']:.4f}
(diferenca {neg_ctrl['diferenca']:.5f}) -> **{neg_ctrl['veredito']}**.

## Veredito final
**{"PASSA" if gate_pass else "NAO PASSA"} o gate §6.**
"""
    (out_dir / "veredito.md").write_text(veredito, encoding="utf-8")
    print(f"\n>> veredito.md escrito em {out_dir}")
    print(f">> GATE [{a.candidate}]: {'PASSA' if gate_pass else 'NAO PASSA'} "
          f"({n_folds_melhora}/{n_folds} folds, delta_ll={mean_delta_ll:.5f}, delta_ece={mean_delta_ece:.5f})")


if __name__ == "__main__":
    main()
