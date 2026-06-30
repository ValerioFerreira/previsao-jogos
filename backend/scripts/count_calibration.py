#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/count_calibration.py
====================================
JANELA NOVA — calibracao das linhas Over/Under dos MERCADOS DE CONTAGEM nos modelos
DEPLOYADOS (ShotsNB, CornersNB, ShotsOnTargetNB, CardsGP). A producao fit r/dispersao
global; sera que a prob. Over de cada linha esta bem calibrada fora-do-tempo?

Teste honesto (sem leakage temporal): ordena por data, ajusta o calibrador ISOTONICO
na METADE ANTIGA (over_prob -> frequencia observada) e AVALIA na metade recente.
Compara, por mercado x linha: ECE e log-loss de Bernoulli (Over/Under) cru vs calibrado.
Gate: reduzir ECE sem piorar log-loss, CONSISTENTE entre linhas e no bloco recente.
Saida: data/reports/count_calibration.csv
"""
from __future__ import annotations
import warnings, json, sys
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
OUT = ROOT / "data" / "reports" / "count_calibration.csv"
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")

# (mercado, artefato, col_home, col_away, linhas O/U do TOTAL a avaliar)
MARKETS = [
    ("finalizacoes", "shots_nb.joblib", "home_cur_sb_shots", "away_cur_sb_shots", [18.5, 20.5, 22.5, 24.5, 26.5]),
    ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners", [7.5, 8.5, 9.5, 10.5, 11.5]),
    ("finalizacoes_gol", "shots_on_target_nb.joblib", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", [5.5, 6.5, 7.5, 8.5, 9.5]),
    ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards", [2.5, 3.5, 4.5, 5.5]),
]

def enrich(te):
    te = apply_ortho_residuals(te, ORTHO_W)
    te = te.merge(OOF, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]; te["pred_away_shots"] = te["pred_away_shots_oof"]
    te = add_corner_interactions(te)
    return te

def ece_bin(y, p, nb=10):
    edges = np.linspace(0, 1, nb + 1); e = 0.0
    for b in range(nb):
        mk = (p >= edges[b]) & (p < edges[b + 1])
        if mk.mean() > 0: e += mk.mean() * abs(y[mk].mean() - p[mk].mean())
    return float(e)

def bll(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    rows = []
    for mkt, art, ch, ca, lines in MARKETS:
        model = joblib.load(ART / art)
        sub = adv.dropna(subset=[ch, ca]).copy().sort_values("date").reset_index(drop=True)
        sub = enrich(sub)
        miss = [f for f in model.feats if f not in sub.columns]
        if miss:
            print(f"[{mkt}] faltam {miss[:4]} — pulado", flush=True); continue
        d = model.predict_distributions(sub[model.feats])
        Pt = d["total"]  # (N, 2M+1)
        ytot = (sub[ch].astype(int).values + sub[ca].astype(int).values)
        half = len(sub) // 2
        for line in lines:
            k0 = int(np.floor(line)) + 1
            over = Pt[:, k0:].sum(1)
            yb = (ytot > line).astype(float)
            # split temporal: calibra no antigo, avalia no recente
            o_tr, o_te = over[:half], over[half:]
            y_tr, y_te = yb[:half], yb[half:]
            iso = IsotonicRegression(out_of_bounds="clip").fit(o_tr, y_tr)
            o_te_cal = iso.predict(o_te)
            rows.append({"mercado": mkt, "linha": line, "n_te": len(o_te), "base_rate": float(y_te.mean()),
                         "ece_raw": ece_bin(y_te, o_te), "ece_cal": ece_bin(y_te, o_te_cal),
                         "bll_raw": bll(y_te, o_te), "bll_cal": bll(y_te, o_te_cal),
                         "dECE": ece_bin(y_te, o_te_cal) - ece_bin(y_te, o_te),
                         "dBLL": bll(y_te, o_te_cal) - bll(y_te, o_te)})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        sm = pd.DataFrame([r for r in rows if r["mercado"] == mkt])
        print(f"[{mkt}] ECE_raw_med={sm.ece_raw.mean()*100:.1f}% -> ECE_cal={sm.ece_cal.mean()*100:.1f}% | "
              f"dBLL_med={sm.dBLL.mean():+.4f} | linhas que melhoram ECE: {(sm.dECE<0).sum()}/{len(sm)}", flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
