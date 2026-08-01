#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/build_ou_calibrators_clube.py
================================================
Equivalente a build_ou_calibrators.py, pra CLUBE (assimetria Grupo 5 do
docs/PLANO_EXPANSAO_MERCADOS.md: `ou_calibrators.joblib` so existe pra
selecao -- os 8 mercados de contagem de clube saem crus). Mesma logica de
enriquecimento (OOF de chutes + ortho residuals + corner_interactions) usada
em build_clubs_production_artifacts.py, pra nao divergir de como o artefato
de producao foi realmente ajustado.

Saida: model_artifacts_clubes/ou_calibrators.joblib
"""
from __future__ import annotations
import warnings, sys, json
from pathlib import Path
import numpy as np, pandas as pd, joblib
from sklearn.isotonic import IsotonicRegression

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from ortho_sinais import apply_ortho_residuals
from corner_interactions import add_corner_interactions
from scripts.clubs_train_counts import base_feats, oof_shots_for_train
from scripts.battery_dataset import load_clubs_df

ART = ROOT / "model_artifacts_clubes"
OUT = ART / "ou_calibrators.joblib"
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
META = json.load(open(ART / "meta.json", encoding="utf-8"))
FULL_FEATS = META["full_feats"]

# (mercado, artefato, col_home, col_away, linhas O/U, precisa OOF de chutes)
MARKETS = [
    ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners",
     [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5], True),
    ("finalizacoes_gol", "shots_on_target_nb.joblib", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target",
     [4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5], False),
    ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards",
     [1.5, 2.5, 3.5, 4.5, 5.5, 6.5], True),
]


def main():
    df = load_clubs_df(min_matches=0)
    adv = df[df["has_advanced_stats"] == 1].copy()
    adv = apply_ortho_residuals(adv, ORTHO_W)
    shots_feats = base_feats(adv, FULL_FEATS, extra_exclude=["pred_home_shots", "pred_away_shots"])
    print(f"Base clube: {len(df)} jogos | com box-score avancado: {len(adv)}", flush=True)

    cals = {}
    for mkt, art, ch, ca, lines, need_oof in MARKETS:
        model = joblib.load(ART / art)
        sub = adv.dropna(subset=[ch, ca]).copy().sort_values("date").reset_index(drop=True)
        if need_oof:
            ph, pa = oof_shots_for_train(sub, shots_feats, "home_cur_sb_shots", "away_cur_sb_shots", 55, H=2)
            sub["pred_home_shots"], sub["pred_away_shots"] = ph, pa
        sub = add_corner_interactions(sub)
        feats = [f for f in model.feats if f in sub.columns]
        missing = [f for f in model.feats if f not in sub.columns]
        if missing:
            print(f"  [{mkt}] AVISO: {len(missing)} feats do modelo ausentes no dataset enriquecido, "
                  f"predict_distributions vai falhar se forem essenciais: {missing[:5]}...", flush=True)
        Pt = model.predict_distributions(sub[feats])["total"]
        ytot = sub[ch].astype(int).values + sub[ca].astype(int).values
        probs, ys = [], []
        for L in lines:
            k0 = int(np.floor(L)) + 1
            probs.append(Pt[:, k0:].sum(1)); ys.append((ytot > L).astype(float))
        p = np.concatenate(probs); y = np.concatenate(ys)
        iso = IsotonicRegression(out_of_bounds="clip").fit(p, y)
        cals[mkt] = iso

        def ece(yv, pv, nb=10):
            edges = np.linspace(0, 1, nb + 1); e = 0
            for b in range(nb):
                mk = (pv >= edges[b]) & (pv < edges[b + 1])
                if mk.mean() > 0: e += mk.mean() * abs(yv[mk].mean() - pv[mk].mean())
            return e
        print(f"[{mkt}] N_pares={len(p)} ECE_in: cru {ece(y,p)*100:.1f}% -> cal {ece(y,iso.predict(p))*100:.1f}%", flush=True)

    joblib.dump(cals, OUT)
    print(f"FEITO -> {OUT}  (mercados: {list(cals.keys())})", flush=True)


if __name__ == "__main__":
    main()
