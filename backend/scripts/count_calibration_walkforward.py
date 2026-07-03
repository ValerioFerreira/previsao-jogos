#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/scripts/count_calibration_walkforward.py
================================================
Validacao RIGOROSA da calibracao isotonica das linhas O/U dos mercados de contagem
(deployados). Confirma o achado do count_calibration.py sob CV TEMPORAL EXPANDING e
com calibrador POOLED por mercado (uma curva monotona aplicavel a QUALQUER linha ->
deployavel). Tambem segmenta por competicao/equilibrio para checar consistencia.

Por fold (cuts 0.5..0.85): ajusta isotonico em (over_prob, outcome) de TODAS as linhas
no treino; avalia no bloco seguinte. Reporta ECE e Bernoulli-LL cru vs calibrado.
Gate: reduzir ECE sem piorar LL, consistente em folds E segmentos.
Saida: data/reports/count_calibration_wf.csv
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
OUT = ROOT / "data" / "reports" / "count_calibration_wf.csv"
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")

MARKETS = [
    ("finalizacoes", "shots_nb.joblib", "home_cur_sb_shots", "away_cur_sb_shots", [18.5, 20.5, 22.5, 24.5, 26.5]),
    ("escanteios", "corners_cascade_rfixo.joblib", "home_cur_sb_corners", "away_cur_sb_corners", [7.5, 8.5, 9.5, 10.5, 11.5]),
    ("finalizacoes_gol", "shots_on_target_nb.joblib", "home_cur_sb_shots_on_target", "away_cur_sb_shots_on_target", [5.5, 6.5, 7.5, 8.5, 9.5]),
    ("cartoes", "cards_gp.joblib", "home_cur_sb_cards", "away_cur_sb_cards", [2.5, 3.5, 4.5, 5.5]),
]

def comp_group(t):
    t = str(t)
    if 'World Cup' in t and 'qualif' in t.lower(): return 'Eliminatorias'
    if t == 'FIFA World Cup': return 'Copa do Mundo'
    if 'Nations League' in t: return 'Nations League'
    if t in ('Friendly', 'Friendlies'): return 'Amistoso'
    if 'qualif' in t.lower(): return 'Eliminatorias'
    if any(k in t for k in ['Euro', 'Copa Am', 'African Cup', 'Asian Cup', 'Gold Cup']): return 'Continental'
    return 'Outros'

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

def build_pooled(sub, Pt, ytot, lines):
    """Empilha (over_prob, outcome, idx_linha, comp) para todas as linhas."""
    recs = []
    for line in lines:
        k0 = int(np.floor(line)) + 1
        over = Pt[:, k0:].sum(1)
        yb = (ytot > line).astype(float)
        recs.append(pd.DataFrame({"over": over, "y": yb, "line": line,
                                  "pos": np.arange(len(sub))}))
    return pd.concat(recs, ignore_index=True)

def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].copy().sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4)
    rows = []
    for mkt, art, ch, ca, lines in MARKETS:
        model = joblib.load(ART / art)
        sub = adv.dropna(subset=[ch, ca]).copy().sort_values("date").reset_index(drop=True)
        sub = enrich(sub)
        if [f for f in model.feats if f not in sub.columns]:
            print(f"[{mkt}] features faltando — pulado", flush=True); continue
        Pt = model.predict_distributions(sub[model.feats])["total"]
        ytot = sub[ch].astype(int).values + sub[ca].astype(int).values
        comp = sub["tournament"].map(comp_group).values
        pooled = build_pooled(sub, Pt, ytot, lines)
        pooled["comp"] = comp[pooled["pos"].values]
        N = len(sub)
        for c in cuts:
            n = int(N * c); m = int(N * min(c + 0.15, 1.0))
            tr = pooled[pooled.pos < n]; te = pooled[(pooled.pos >= n) & (pooled.pos < m)]
            if len(te) < 100: continue
            iso = IsotonicRegression(out_of_bounds="clip").fit(tr["over"].values, tr["y"].values)
            cal = iso.predict(te["over"].values)
            rows.append({"mercado": mkt, "fold": round(c, 2), "n_te_rows": len(te),
                         "ece_raw": ece_bin(te["y"].values, te["over"].values),
                         "ece_cal": ece_bin(te["y"].values, cal),
                         "bll_raw": bll(te["y"].values, te["over"].values),
                         "bll_cal": bll(te["y"].values, cal)})
        pd.DataFrame(rows).to_csv(OUT, index=False)
        sm = pd.DataFrame([r for r in rows if r["mercado"] == mkt])
        print(f"[{mkt}] folds: " + " ".join(
            f"ECE {r.ece_raw*100:.1f}->{r.ece_cal*100:.1f} dBLL{r.bll_cal-r.bll_raw:+.3f}" for _, r in sm.iterrows()),
            flush=True)
        print(f"    MEDIA ECE {sm.ece_raw.mean()*100:.1f}%->{sm.ece_cal.mean()*100:.1f}% | "
              f"dBLL={sm.bll_cal.mean()-sm.bll_raw.mean():+.4f} | folds melhora ECE: {(sm.ece_cal<sm.ece_raw).sum()}/{len(sm)}",
              flush=True)
    print(f"FEITO -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
