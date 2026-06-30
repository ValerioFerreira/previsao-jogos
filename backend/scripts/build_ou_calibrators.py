#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/build_ou_calibrators.py
=======================================
Constroi o artefato de CALIBRACAO O/U dos mercados de contagem (escanteios, a-gol,
cartoes) — validado por walk-forward em count_calibration_walkforward.py (ECE cai e
Bernoulli-LL melhora out-of-time; chutes EXCLUIDO porque piora). Ajusta um isotonico
por mercado sobre (over_prob_TOTAL, desfecho) pooled em varias linhas, no historico
COMPLETO. O predictor aplica essa curva monotona a qualquer linha O/U do TOTAL.

Saida: model_artifacts/ou_calibrators.joblib  (dict {mercado: IsotonicRegression}).
"""
from __future__ import annotations
import warnings, sys
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.isotonic import IsotonicRegression

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ortho_sinais import apply_ortho_residuals
from corner_interactions import add_corner_interactions
ART = ROOT / "model_artifacts"
CSV = ROOT / "international_features_enriched_apifootball.csv"
OUT = ART / "ou_calibrators.joblib"
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")

# Apenas mercados que PASSARAM o gate de calibracao (chutes excluido)
MARKETS = [
    ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners",
     [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]),
    ("finalizacoes_gol", "shots_on_target_nb.joblib", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target",
     [4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5]),
    ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards",
     [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]),
]

def enrich(te):
    te = apply_ortho_residuals(te, ORTHO_W)
    te = te.merge(OOF, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]; te["pred_away_shots"] = te["pred_away_shots_oof"]
    te = add_corner_interactions(te)
    return te

def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    cals = {}
    for mkt, art, ch, ca, lines in MARKETS:
        model = joblib.load(ART / art)
        sub = adv.dropna(subset=[ch, ca]).copy().sort_values("date").reset_index(drop=True)
        sub = enrich(sub)
        Pt = model.predict_distributions(sub[model.feats])["total"]
        ytot = sub[ch].astype(int).values + sub[ca].astype(int).values
        probs, ys = [], []
        for L in lines:
            k0 = int(np.floor(L)) + 1
            probs.append(Pt[:, k0:].sum(1)); ys.append((ytot > L).astype(float))
        p = np.concatenate(probs); y = np.concatenate(ys)
        iso = IsotonicRegression(out_of_bounds="clip").fit(p, y)
        cals[mkt] = iso
        # sanity: ECE in-sample (apenas referencia)
        def ece(yv, pv, nb=10):
            edges = np.linspace(0, 1, nb + 1); e = 0
            for b in range(nb):
                mk = (pv >= edges[b]) & (pv < edges[b + 1])
                if mk.mean() > 0: e += mk.mean() * abs(yv[mk].mean() - pv[mk].mean())
            return e
        print(f"[{mkt}] N_pares={len(p)} ECE_in: raw {ece(y,p)*100:.1f}% -> cal {ece(y,iso.predict(p))*100:.1f}%", flush=True)
    joblib.dump(cals, OUT)
    print(f"FEITO -> {OUT}  (mercados: {list(cals.keys())})", flush=True)

if __name__ == "__main__":
    main()
