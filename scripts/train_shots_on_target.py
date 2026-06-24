#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_shots_on_target.py
================================
Treina o modelo de CHUTES A GOL (shots on target) — NB independente, MESMA receita
do ShotsNB de chutes (cascata/estilo ortogonalizado + time decay selecionado por ECE),
porém com alvo `*_sb_shots_on_target` e grade menor (contagem mais baixa).

Persiste api/model_artifacts/shots_on_target_nb.joblib. Não toca outros artefatos.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, str(Path("api").resolve()))
from shots_nb_model import ShotsNB
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals

warnings.filterwarnings("ignore")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CSV = Path("international_features_enriched_apifootball.csv")
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
STYLE_RAW = [c for c in META["full_feats"] if c.startswith("home_style_") or c.startswith("away_style_") or c.startswith("diff_style_")]
FEATS = [f for f in META["full_feats"] if f not in STYLE_RAW and f not in ("pred_home_shots", "pred_away_shots")]
OUT = Path("api/model_artifacts/shots_on_target_nb.joblib")
H_GRID = [None, 3, 2, 1]
TH, TA = "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target"


def decay_w(dates, anchor, H):
    return None if H is None else 0.5 ** ((anchor - dates).dt.days.values.astype(float) / (H * 365.0))


def _ece(y_over, p, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1); e = 0.0
    for i in range(n_bins):
        m = (p >= bins[i]) & (p < bins[i + 1])
        if m.mean() > 0: e += m.mean() * abs(y_over[m].mean() - p[m].mean())
    return e


def main():
    print("=" * 78)
    print(" TREINO — ShotsOnTargetNB (chutes a gol, NB + time decay)")
    print("=" * 78)
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=[TH, TA]).sort_values("date").reset_index(drop=True)
    print(f"Jogos com chutes a gol validos: {len(adv)}")
    yh = adv[TH].astype(int).values; ya = adv[TA].astype(int).values

    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tri, val = adv[adv["date"] <= cut], adv[adv["date"] > cut]
    anchor_tri = tri["date"].max()
    ytv = val[TH].astype(int).values + val[TA].astype(int).values
    print(f">> Selecao de H por ECE (treino<= {cut:%Y-%m-%d})")
    scores = []
    for H in H_GRID:
        w_tri = fit_ortho_regressions(tri)
        tri_o = apply_ortho_residuals(tri, w_tri); val_o = apply_ortho_residuals(val, w_tri)
        w = decay_w(tri_o["date"], anchor_tri, H)
        m = ShotsNB(feats=FEATS, max_corners=30)
        m.fit(tri_o[FEATS], tri_o[TH].astype(int).values, tri_o[TA].astype(int).values, sample_weight=w)
        pt = m.predict_distributions(val_o[FEATS])["total"]
        ece = _ece((ytv > 7.5).astype(int), pt[:, 8:].sum(axis=1))
        scores.append((H, ece)); print(f"   {'sem decay' if H is None else f'H={H}':10s} -> val ECE(O7.5) {ece:.2%}")
    best_ece = min(s[1] for s in scores)
    cand = [H for H, e in scores if e <= best_ece + 0.003]
    best_H = max([H for H in cand if H is not None], default=None)
    print(f">> H escolhido: {best_H if best_H else 'sem decay'}")

    weights_full = fit_ortho_regressions(adv)
    adv_o = apply_ortho_residuals(adv, weights_full)
    w_full = decay_w(adv_o["date"], adv_o["date"].max(), best_H)
    model = ShotsNB(feats=FEATS, max_corners=30)
    model.fit(adv_o[FEATS], yh, ya, sample_weight=w_full)
    model.decay_H_ = best_H
    d = model.predict_distributions(adv_o[FEATS])
    ks = np.arange(model.max_corners + 1); kt = np.arange(2 * model.max_corners + 1)
    print("\n>> Vies global (in-sample):")
    print(f"  Mandante  real {yh.mean():.2f}  E[PMF] {(d['home']@ks).mean():.2f}")
    print(f"  Visitante real {ya.mean():.2f}  E[PMF] {(d['away']@ks).mean():.2f}")
    print(f"  Total     real {(yh+ya).mean():.2f}  E[PMF] {(d['total']@kt).mean():.2f}")
    model.save(str(OUT))
    print(f"\nOK. Artefato salvo: {OUT} (decay_H={best_H}).")


if __name__ == "__main__":
    main()
