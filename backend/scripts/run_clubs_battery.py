#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/run_clubs_battery.py
============================
Bateria de RESULTADO (H/D/A) da pesquisa de clubes — Linhas A e B sob o MESMO
protocolo (research_clubs/protocol.py). Resumível: cada candidato grava seu
resultado em data/reports/clubs_battery/<nome>.csv e é pulado se o CSV existir.

Candidatos (fase 1 — resultado):
  A_dc_nb        : arquitetura de PRODUÇÃO (DixonColesNBRegressor, GBM->NB+rho) treinada
                   nas 158 base_feats do dataset de clubes  ← baseline da pesquisa
  B1_cat_pi      : CatBoost + pi-ratings + Elo (SOTA challenges)
  B1_lgbm_pi     : LightGBM + pi-ratings + Elo
  B2_cat_berrar  : CatBoost + Berrar ratings + Elo
  B3_ordlogit_pi : ordered logit + pi-ratings (baseline literatura)
  B4_dc_classic  : DC clássico por liga (estático e xi=1.5)
  B7_bivpois     : Poisson bivariado K&N por liga

Uso: python scripts/run_clubs_battery.py [--only A_dc_nb,B1_cat_pi] [--min-mpb 5]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_clubs.protocol import (evaluate_result_model, summarize, temporal_folds,
                                     multiclass_logloss, rps_hda, ece_multiclass,
                                     brier_multiclass, accuracy, RESULT_ORDER)
from research_clubs.gbm_models import (add_rating_features, fit_predict_catboost,
                                       fit_predict_lgbm, fit_predict_ordered_logit,
                                       PI_FEATS, BR_FEATS, ELO_FEATS)
from research_clubs.stat_models import DixonColesClassic, BivariatePoissonKN

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
OUT_DIR = ROOT / "data" / "reports" / "clubs_battery"
META = ROOT / "model_artifacts" / "meta.json"


def load_data(min_mpb: int) -> pd.DataFrame:
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # burn-in: exige histórico mínimo dos DOIS lados (Elo/forma estabilizados)
    m = (df["home_matches_played_before"] >= min_mpb) & \
        (df["away_matches_played_before"] >= min_mpb)
    df = df[m].reset_index(drop=True)
    print(f"dataset: {len(df)} jogos após burn-in >= {min_mpb} jogos/lado")
    return df


def base_feats_for_clubs(df) -> list:
    bf = json.load(open(META, encoding="utf-8"))["base_feats"]
    have = [c for c in bf if c in df.columns]
    missing = [c for c in bf if c not in df.columns]
    if missing:
        print(f"  [aviso] {len(missing)} base_feats ausentes em clubes (ok): {missing[:8]}...")
    return have


# ─── wrappers fit_predict ────────────────────────────────────────────────────
def make_fp_dc_nb(feats):
    from dixon_coles_model import DixonColesNBRegressor

    def fp(tr, te):
        X = tr[feats].fillna(tr[feats].median(numeric_only=True))
        Xt = te[feats].fillna(tr[feats].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        probs_adh = m.predict_proba_markets(Xt)["result"]  # ordem [A, D, H]
        return probs_adh[:, ::-1]  # -> [H, D, A]
    return fp


def make_fp_per_league(model_cls, **kw):
    """Ajusta um modelo de força POR LIGA no treino; prevê cada jogo do teste com o
    modelo da sua liga (fallback: probs de frequência do treino)."""
    def fp(tr, te):
        out = np.zeros((len(te), 3))
        freq = tr["result"].value_counts(normalize=True)
        fallback = np.array([freq.get(c, 1e-3) for c in RESULT_ORDER])
        fallback = fallback / fallback.sum()
        for lid, te_grp in te.groupby("league_id"):
            tr_grp = tr[tr["league_id"] == lid]
            pos = te.index.get_indexer(te_grp.index)
            if len(tr_grp) < 300:
                out[pos] = fallback
                continue
            try:
                m = model_cls(**kw).fit(tr_grp)
                out[pos] = m.predict_hda(te_grp)
            except Exception as e:
                print(f"    [aviso] liga {lid}: {e}")
                out[pos] = fallback
        return out
    return fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--min-mpb", type=int, default=5)
    a = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data(a.min_mpb)
    df = add_rating_features(df)  # pi + Berrar (pré-jogo, sem leakage)
    bf = base_feats_for_clubs(df)

    candidates = {
        "A_dc_nb": lambda: make_fp_dc_nb(bf),
        "B1_cat_pi": lambda: (lambda tr, te: fit_predict_catboost(tr, te, PI_FEATS + ELO_FEATS)),
        "B1_lgbm_pi": lambda: (lambda tr, te: fit_predict_lgbm(tr, te, PI_FEATS + ELO_FEATS)),
        "B2_cat_berrar": lambda: (lambda tr, te: fit_predict_catboost(tr, te, BR_FEATS + ELO_FEATS)),
        "B3_ordlogit_pi": lambda: (lambda tr, te: fit_predict_ordered_logit(tr, te, PI_FEATS)),
        "B4_dc_classic": lambda: make_fp_per_league(DixonColesClassic, xi=0.0),
        "B4_dc_dynamic": lambda: make_fp_per_league(DixonColesClassic, xi=1.5),
        "B7_bivpois": lambda: make_fp_per_league(BivariatePoissonKN),
    }
    only = set(a.only.split(",")) if a.only else None

    for name, factory in candidates.items():
        if only and name not in only:
            continue
        out_csv = OUT_DIR / f"{name}.csv"
        if out_csv.exists():
            print(f"[skip] {name} (já existe {out_csv.name})")
            continue
        print(f"\n=== {name} ===", flush=True)
        t0 = time.time()
        try:
            results = evaluate_result_model(df, factory())
        except Exception as e:
            print(f"  [ERRO] {name}: {e}")
            continue
        summ = summarize(results, label=name)
        seg_rows = []
        for r in results:
            for seg, m in r.segments.items():
                seg_rows.append({"fold": r.fold, "segmento": seg, **m})
        summ.to_csv(out_csv, index=False)
        if seg_rows:
            pd.DataFrame(seg_rows).to_csv(OUT_DIR / f"{name}_segments.csv", index=False)
        media = summ[summ["fold"] == "MEDIA"].iloc[0]
        print(f"  {name}: logloss {media['logloss']:.4f} | rps {media['rps']:.4f} | "
              f"ece {media['ece']:.4f} | acc {media['accuracy']:.4f} | {time.time()-t0:.0f}s")

    # tabela comparativa final
    all_csv = sorted(OUT_DIR.glob("*.csv"))
    frames = [pd.read_csv(c) for c in all_csv if not c.name.endswith("_segments.csv")]
    if frames:
        comp = pd.concat(frames, ignore_index=True)
        comp = comp[comp["fold"] == "MEDIA"].sort_values("logloss")
        print("\n===== RANKING (média dos folds) =====")
        print(comp[["modelo", "logloss", "rps", "brier", "ece", "accuracy"]].to_string(index=False))
        comp.to_csv(OUT_DIR / "_ranking.csv", index=False)


if __name__ == "__main__":
    main()
