#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/clubs_hyp10_calibration_bucket.py
==========================================
Hipótese H10: calibração isotônica PÓS-HOC por bucket de |elo_diff| (equilibrado/
médio/desequilibrado). Diferente de "elo_conditioned" (Fase 4, REPROVADO) -- aquele
mudava o MODELO (lambda/mu condicionados no Elo); este só recalibra a probabilidade
final de H/D/A por bucket, mesmo padrão já promovido pra O/U (calibracao-ou-promovida).
Gate: ECE melhora em >=4/5 folds sem piorar logloss médio.
"""
import sys, json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import temporal_folds, multiclass_logloss, ece_multiclass

FEATURES = ROOT / "data" / "built" / "club_features_enriched.parquet"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE_FEATS = META["base_feats"]
OUT_DIR = ROOT / "data" / "reports" / "clubs_new_hyp"
Y_MAP = {"H": 0, "D": 1, "A": 2}
BANDS = (80, 150)


def calibrate_bucket(probs_tr, y_tr, probs_te, bucket_tr, bucket_te, bucket_name):
    """Isotônico one-vs-rest por classe, treinado SÓ no bucket, aplicado no mesmo bucket."""
    out = probs_te.copy()
    m_tr = bucket_tr == bucket_name
    m_te = bucket_te == bucket_name
    if m_tr.sum() < 200 or m_te.sum() == 0:
        return out, m_te
    for k in range(3):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
        iso.fit(probs_tr[m_tr, k], (y_tr[m_tr] == k).astype(float))
        out[m_te, k] = iso.predict(probs_te[m_te, k])
    row_sum = out[m_te].sum(axis=1, keepdims=True)
    out[m_te] = out[m_te] / np.clip(row_sum, 1e-9, None)
    return out, m_te


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(FEATURES)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df2 = df[(df["home_matches_played_before"] >= 5) &
             (df["away_matches_played_before"] >= 5)].reset_index(drop=True)

    rows = []
    for fold, tr_idx, te_idx in temporal_folds(df2):
        tr, te = df2.loc[tr_idx], df2.loc[te_idx]
        X_tr = tr[BASE_FEATS].fillna(tr[BASE_FEATS].median(numeric_only=True))
        X_te = te[BASE_FEATS].fillna(tr[BASE_FEATS].median(numeric_only=True))
        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                  max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        probs_tr = m.predict_proba_markets(X_tr)["result"][:, ::-1]
        probs_te = m.predict_proba_markets(X_te)["result"][:, ::-1]
        y_tr = tr["result"].map(Y_MAP).to_numpy()
        y_te = te["result"].map(Y_MAP).to_numpy()

        def bucket_of(d):
            a = d["elo_diff"].abs().to_numpy()
            b = np.full(len(a), "desequil", dtype=object)
            b[a <= BANDS[0]] = "equil"
            b[(a > BANDS[0]) & (a <= BANDS[1])] = "medio"
            return b
        bkt_tr, bkt_te = bucket_of(tr), bucket_of(te)

        cal_probs = probs_te.copy()
        for bname in ("equil", "medio", "desequil"):
            cal_probs, m_te = calibrate_bucket(probs_tr, y_tr, probs_te, bkt_tr, bkt_te, bname)
            probs_te = np.where(m_te[:, None], cal_probs, probs_te)

        ll_raw, ece_raw = multiclass_logloss(y_te, cal_probs), ece_multiclass(y_te, cal_probs)
        ll_cal, ece_cal = ll_raw, ece_raw  # cal_probs already holds calibrated result post-loop
        print(f"  [{fold}] n={len(te)} logloss_cal={ll_cal:.4f} ece_cal={ece_cal:.4f}", flush=True)
        rows.append({"fold": fold, "n": len(te), "logloss_cal": ll_cal, "ece_cal": ece_cal})

    R = pd.DataFrame(rows)
    R.to_csv(OUT_DIR / "h10_calibration_bucket.csv", index=False)
    print(f"\n>> media pos-calibracao: logloss={R.logloss_cal.mean():.4f} ece={R.ece_cal.mean():.4f}")
    print(">> comparar contra baseline (Fase1 producao: logloss~0.9938) pra veredito final.")


if __name__ == "__main__":
    main()
