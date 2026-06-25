#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/generate_oof_shots.py
=============================
Gera previsões Out-of-Fold (OOF) de chutes (ShotsNB) usando cross-validation de 5 folds.
Impede vazamento de dados ao treinar o modelo de escanteios (CornersNB) em cascata.
"""
import sys
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold
import joblib

sys.path.insert(0, str(Path("api").resolve()))
from shots_nb_model import ShotsNB
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals

warnings.filterwarnings("ignore")

CSV = Path("international_features_enriched_apifootball.csv")
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
STYLE_RAW = [c for c in META["full_feats"] if c.startswith("home_style_") or c.startswith("away_style_") or c.startswith("diff_style_")]
FEATS = [f for f in META["full_feats"] if f not in STYLE_RAW and f not in ("pred_home_shots", "pred_away_shots")]
OUT_CSV = Path("data/built/oof_shots.csv")

def decay_w(dates, anchor, H=1):
    if H is None:
        return None
    return 0.5 ** ((anchor - dates).dt.days.values.astype(float) / (H * 365.0))

def main():
    print("Generating Out-of-Fold (OOF) Shots Predictions...")
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(
        subset=["home_cur_sb_shots", "away_cur_sb_shots"]
    ).sort_values("date").reset_index(drop=True)
    
    print(f"Total advanced matches: {len(adv)}")
    
    adv["pred_home_shots_oof"] = np.nan
    adv["pred_away_shots_oof"] = np.nan
    
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    
    for fold, (train_idx, val_idx) in enumerate(kf.split(adv)):
        print(f"Processing Fold {fold+1}/5...")
        tri = adv.iloc[train_idx].copy()
        val = adv.iloc[val_idx].copy()
        
        # Fit style orthogonalization strictly on the training fold
        weights_tri = fit_ortho_regressions(tri)
        tri_ortho = apply_ortho_residuals(tri, weights_tri)
        val_ortho = apply_ortho_residuals(val, weights_tri)
        
        # Compute time decay (H=1, as chosen for ShotsNB)
        anchor_tri = tri_ortho["date"].max()
        w = decay_w(tri_ortho["date"], anchor_tri, H=1)
        
        # Fit ShotsNB on training split
        m = ShotsNB(feats=FEATS)
        m.fit(tri_ortho[FEATS], tri_ortho["home_cur_sb_shots"].astype(int).values,
              tri_ortho["away_cur_sb_shots"].astype(int).values, sample_weight=w)
        
        # Predict on validation split
        dists = m.predict_distributions(val_ortho[FEATS])
        
        adv.loc[val_idx, "pred_home_shots_oof"] = dists["lambdas"]
        adv.loc[val_idx, "pred_away_shots_oof"] = dists["mus"]
        
    # Verify all predictions are populated
    assert not adv["pred_home_shots_oof"].isna().any()
    assert not adv["pred_away_shots_oof"].isna().any()
    
    # Save OOF predictions to file
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    adv[["match_id", "pred_home_shots_oof", "pred_away_shots_oof"]].to_csv(OUT_CSV, index=False)
    print(f"OOF shots predictions saved successfully to {OUT_CSV}")

if __name__ == "__main__":
    main()
