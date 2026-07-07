#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp14_combo_backtest.py — a cópula melhora a probabilidade de COMBOS de 2 pernas?
=========================================================================================
Teste decisivo do valor prático da cópula (EXP7/EXP13): para combos "over A + over B", compara
  P_indep = p_A·p_B                (assumindo independência — como o Monte sua Aposta hoje)
  P_cop   = P(Z_A>z_A, Z_B>z_B; ρ) (cópula gaussiana bivariada)
e mede o log-loss/Brier do DESFECHO real do combo (as duas pernas baterem), CV temporal.
Se a cópula reduz o log-loss do combo, precificar combinadas com ela é uma melhoria concreta.
Pares testados: finalizações+escanteios, gols+finalizações (linhas centrais).
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from scipy.stats import norm, multivariate_normal
from sklearn.metrics import log_loss, brier_score_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ortho_sinais import apply_ortho_residuals
from corner_interactions import add_corner_interactions
ART = ROOT / "model_artifacts"; CSV = ROOT / "international_features_enriched_apifootball.csv"
META = __import__("json").load(open(ART / "meta.json", encoding="utf-8")); BASE = [f for f in META["base_feats"]]
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib"); OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")


def enrich(te):
    te = apply_ortho_residuals(te, ORTHO_W); te = te.merge(OOF, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]; te["pred_away_shots"] = te["pred_away_shots_oof"]
    return add_corner_interactions(te)


def over_prob_and_z(pmf, line):
    """p_over(>line) e z = Φ⁻¹(P(<=line)) por linha."""
    k0 = int(np.floor(line)) + 1
    pov = np.clip(pmf[:, k0:].sum(1), 1e-5, 1 - 1e-5)
    z = norm.ppf(1 - pov)
    return pov, z


def dc_total_goals_pmf(dc, X):
    J = dc.predict_proba_markets(X)["joint"]; G = J.shape[1] - 1; N = J.shape[0]
    tot = np.zeros((N, 2 * G + 1))
    for s in range(2 * G + 1):
        for x in range(max(0, s - G), min(G, s) + 1): tot[:, s] += J[:, x, s - x]
    return tot / tot.sum(1, keepdims=True)


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_shots", "away_cur_sb_shots", "home_cur_sb_corners", "away_cur_sb_corners", "home_score", "away_score"]).copy()
    adv = enrich(adv).sort_values("date").reset_index(drop=True)
    base_in = [c for c in BASE if c in adv.columns]
    dc = joblib.load(ART / "dixon_coles_goals.joblib")
    sh = joblib.load(ART / "shots_nb.joblib"); co = joblib.load(ART / "corners_cascade_rfixo.joblib")
    P = {"gols": dc_total_goals_pmf(dc, adv[base_in]),
         "finalizacoes": sh.predict_distributions(adv[sh.feats])["total"],
         "escanteios": co.predict_distributions(adv[co.feats])["total"]}
    OBS = {"gols": (adv.home_score + adv.away_score).astype(int).values,
           "finalizacoes": (adv.home_cur_sb_shots + adv.away_cur_sb_shots).astype(int).values,
           "escanteios": (adv.home_cur_sb_corners + adv.away_cur_sb_corners).astype(int).values}
    LINES = {"gols": 2.5, "finalizacoes": 22.5, "escanteios": 9.5}

    PAIRS = [("finalizacoes", "escanteios"), ("gols", "finalizacoes"), ("gols", "escanteios")]
    cuts = np.linspace(0.5, 0.85, 4)
    print(f"{'Combo (over+over)':30s} | LL indep -> cópula | dLL | Brier i->c | corr")
    print("-" * 84)
    for A, B in PAIRS:
        povA, zA = over_prob_and_z(P[A], LINES[A]); povB, zB = over_prob_and_z(P[B], LINES[B])
        yA = (OBS[A] > LINES[A]).astype(int); yB = (OBS[B] > LINES[B]).astype(int)
        ycombo = (yA & yB).astype(int)
        # z para a correlação da cópula (mid-PIT dos observados)
        zobsA = norm.ppf(np.clip([np.cumsum(P[A], 1)[i, min(int(OBS[A][i]), P[A].shape[1]-1)] for i in range(len(adv))], 1e-4, 1-1e-4))
        zobsB = norm.ppf(np.clip([np.cumsum(P[B], 1)[i, min(int(OBS[B][i]), P[B].shape[1]-1)] for i in range(len(adv))], 1e-4, 1-1e-4))
        rows = []
        for c in cuts:
            n = int(len(adv) * c); m = int(len(adv) * min(c + 0.15, 1.0))
            tr = slice(0, n); teS = slice(n, m)
            if m - n < 80: continue
            rho = np.corrcoef(zobsA[tr], zobsB[tr])[0, 1]; rho = np.clip(rho, -0.95, 0.95)
            p_ind = np.clip(povA[teS] * povB[teS], 1e-6, 1 - 1e-6)
            # P(Z_A>z_A, Z_B>z_B) sob cópula bivariada
            cov = [[1, rho], [rho, 1]]
            zz = np.column_stack([zA[teS], zB[teS]])
            p_cop = np.clip(1 - norm.cdf(zA[teS]) - norm.cdf(zB[teS]) + np.array([multivariate_normal.cdf(zz[i], mean=[0, 0], cov=cov) for i in range(len(zz))]), 1e-6, 1 - 1e-6)
            yt = ycombo[teS]
            rows.append(dict(fold=round(c, 2), ll_ind=log_loss(yt, p_ind, labels=[0, 1]), ll_cop=log_loss(yt, p_cop, labels=[0, 1]),
                             br_ind=brier_score_loss(yt, p_ind), br_cop=brier_score_loss(yt, p_cop), rho=rho, base=yt.mean()))
        R = pd.DataFrame(rows)
        dll = (R.ll_cop - R.ll_ind).mean()
        print(f"{A[:12]+'+'+B[:12]:30s} | {R.ll_ind.mean():.4f} -> {R.ll_cop.mean():.4f} | {dll:+.4f} ({int((R.ll_cop<R.ll_ind).sum())}/{len(R)}) | "
              f"{R.br_ind.mean():.4f}->{R.br_cop.mean():.4f} | {R.rho.mean():+.3f}")


if __name__ == "__main__":
    main()
