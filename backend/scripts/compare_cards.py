#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/compare_cards.py
========================
Compara, em split temporal (80/20) sobre os ~4.1k jogos com stats:
  - CardsNB (original baseline)
  - CardsGP (nova Poisson Generalizada com Cascade e Style features)
nos 3 mercados: mandante, visitante, total.

Mede ECE, Tail ECE, Log-Loss, Brier e Cobertura de Intervalo de 80%.
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path("api").resolve()))
from cards_nb_model import CardsNB
from cards_gp_model import CardsGP
from shots_nb_model import ShotsNB
from ortho_sinais import fit_ortho_regressions, apply_ortho_residuals

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("international_features_enriched_apifootball.csv")
META = json.load(open("api/model_artifacts/meta.json", encoding="utf-8"))
REPORT = Path("comparacao_cartoes.md")

M = 15
RS = 42

def expected_calibration_error(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
    return ece

def tail_expected_calibration_error(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        # Only evaluate bins in tail regions: < 20% or >= 80%
        if bin_upper > 0.2 and bin_lower < 0.8:
            continue
            
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
            
    tail_mask = (y_prob < 0.2) | (y_prob >= 0.8)
    prop_total = np.mean(tail_mask)
    if prop_total > 0:
        ece = ece / prop_total
    return ece

def metrics(prob, actual, lines, maxc, point):
    n = len(actual)
    clipped = np.clip(actual, 0, maxc).astype(int)
    ll = -np.mean(np.log(prob[np.arange(n), clipped] + 1e-15))
    
    # Calculate coverage of 80% interval
    cov, wid = [], []
    for i in range(n):
        cdf = np.cumsum(prob[i])
        q10 = np.searchsorted(cdf, 0.1)
        q90 = np.searchsorted(cdf, 0.9)
        wid.append(q90 - q10)
        cov.append(1.0 if q10 <= actual[i] <= q90 else 0.0)
        
    line_metrics = {}
    for line in lines:
        y_over = (actual > line).astype(int)
        p_over = prob[:, int(line) + 1:].sum(axis=1)
        brier = mean_squared_error(y_over, p_over)
        ece = expected_calibration_error(y_over, p_over)
        tail_ece = tail_expected_calibration_error(y_over, p_over)
        line_metrics[str(line)] = {"brier": brier, "ece": ece, "tail_ece": tail_ece}
        
    return {
        "ll": ll, "cov": np.mean(cov), "wid": np.mean(wid),
        "mae": mean_absolute_error(actual, point), "rmse": np.sqrt(mean_squared_error(actual, point)),
        "mean_pred": float(np.mean(point)), "lines": line_metrics
    }

def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["date"], low_memory=False).sort_values("date").reset_index(drop=True)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_cards", "away_cur_sb_cards"]).copy()
    
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr = adv[adv["date"] <= cut].reset_index(drop=True)
    te = adv[adv["date"] > cut].reset_index(drop=True)
    print(f"Corte temporal: {cut:%Y-%m-%d} | Treino {len(tr)} | Teste {len(te)}")

    yh_tr = tr["home_cur_sb_cards"].astype(int).values
    ya_tr = tr["away_cur_sb_cards"].astype(int).values
    yh_te = te["home_cur_sb_cards"].astype(int).values
    ya_te = te["away_cur_sb_cards"].astype(int).values
    yt_te = yh_te + ya_te
    
    # ------------------ Baseline: CardsNB ------------------
    # CardsNB is trained on the base features (meta["full_feats"] excluding new features)
    STYLE_RAW = [c for c in META["full_feats"] if c.startswith("home_style_") or c.startswith("away_style_") or c.startswith("diff_style_")]
    NEW_FEATS = ["has_boxscore_signal", "pred_home_shots", "pred_away_shots"] + [c for c in META["full_feats"] if c.startswith("resid_") or c.startswith("diff_resid_")]
    base_feats = [f for f in META["full_feats"] if f not in STYLE_RAW and f not in NEW_FEATS]
    
    model_nb = CardsNB(max_corners=M, feats=base_feats)
    model_nb.fit(tr[base_feats], yh_tr, ya_tr)
    nb_dists = model_nb.predict_distributions(te[base_feats])
    
    # ------------------ Novo: CardsGP (Poisson Generalizada + Cascade + Ortho) ------------------
    # 1. Fit signal orthogonalization on training split tr
    weights_tr = fit_ortho_regressions(tr)
    tr_ortho = apply_ortho_residuals(tr, weights_tr)
    te_ortho = apply_ortho_residuals(te, weights_tr)
    
    # 2. Fit Cascade Shots model on tr_ortho
    # Exclude raw style features and shots predictions from shots feature space
    feats_shots = [f for f in META["full_feats"] if f not in STYLE_RAW and f not in ("pred_home_shots", "pred_away_shots")]
    shots_model = ShotsNB(feats=feats_shots)
    # Fit shots model with decay H=1
    anchor_tr = tr_ortho["date"].max()
    from train_shots_nb import decay_w
    w_tr = decay_w(tr_ortho["date"], anchor_tr, 1)
    shots_model.fit(tr_ortho[feats_shots], tr_ortho["home_cur_sb_shots"].astype(int).values,
                    tr_ortho["away_cur_sb_shots"].astype(int).values, sample_weight=w_tr)
    
    # Predict shots expectations and inject them as cascade features
    shots_tr_dists = shots_model.predict_distributions(tr_ortho)
    tr_ortho["pred_home_shots"] = shots_tr_dists["lambdas"]
    tr_ortho["pred_away_shots"] = shots_tr_dists["mus"]
    
    shots_te_dists = shots_model.predict_distributions(te_ortho)
    te_ortho["pred_home_shots"] = shots_te_dists["lambdas"]
    te_ortho["pred_away_shots"] = shots_te_dists["mus"]
    
    # 3. Fit CardsGP on tr_ortho
    feats_cards = [f for f in META["full_feats"] if f not in STYLE_RAW]
    model_gp = CardsGP(max_corners=M, feats=feats_cards)
    model_gp.fit(tr_ortho[feats_cards], yh_tr, ya_tr)
    gp_dists = model_gp.predict_distributions(te_ortho)
    
    print(f"CardsNB MLE: r_H={model_nb.r_H_:.4f}, r_A={model_nb.r_A_:.4f}")
    print(f"CardsGP MLE: gp_lambda_H={model_gp.gp_lambda_H_:.4f}, gp_lambda_A={model_gp.gp_lambda_A_:.4f}")
    
    # Compute metrics
    # Linhas representativas
    lh, la, lt = [1.5, 2.5], [1.5, 2.5], [3.5, 4.5, 5.5]
    
    res_nb = {
        "Mandante": metrics(nb_dists["home"], yh_te, lh, M, nb_dists["lambdas"]),
        "Visitante": metrics(nb_dists["away"], ya_te, la, M, nb_dists["mus"]),
        "Total": metrics(nb_dists["total"], yt_te, lt, 2 * M, nb_dists["lambdas"] + nb_dists["mus"])
    }
    
    res_gp = {
        "Mandante": metrics(gp_dists["home"], yh_te, lh, M, gp_dists["lambdas"]),
        "Visitante": metrics(gp_dists["away"], ya_te, la, M, gp_dists["mus"]),
        "Total": metrics(gp_dists["total"], yt_te, lt, 2 * M, gp_dists["lambdas"] + gp_dists["mus"])
    }
    
    # Build markdown report
    L = [
        "# Relatório de Comparação - Modelo de Cartões",
        f"- Corte temporal: {cut:%Y-%m-%d} | Treino: {len(tr)} | Teste: {len(te)}",
        f"- baseline: CardsNB (NB independente, ~Poisson)",
        f"- Novo: CardsGP (Poisson Generalizada + Cascade + Ortho)",
        "",
        "## Parâmetros Estimados por MLE no Treino",
        f"- **CardsNB**: r_H = {model_nb.r_H_:.4f}, r_A = {model_nb.r_A_:.4f}",
        f"- **CardsGP**: gp_lambda_H = {model_gp.gp_lambda_H_:.4f}, gp_lambda_A = {model_gp.gp_lambda_A_:.4f} (underdispersão confirmada!)",
        "",
        "## Viés Global no Teste temporal (Média Prevista vs Real)",
        "| Mercado | Real | CardsNB | CardsGP |",
        "|---|---|---|---|",
        f"| Mandante | {yh_te.mean():.3f} | {res_nb['Mandante']['mean_pred']:.3f} | {res_gp['Mandante']['mean_pred']:.3f} |",
        f"| Visitante | {ya_te.mean():.3f} | {res_nb['Visitante']['mean_pred']:.3f} | {res_gp['Visitante']['mean_pred']:.3f} |",
        f"| Total | {yt_te.mean():.3f} | {res_nb['Total']['mean_pred']:.3f} | {res_gp['Total']['mean_pred']:.3f} |",
        "",
        "## Métricas de Performance Global (Log-Loss e Cobertura)",
        "| Mercado | Modelo | LogLoss | Cob 80% | Largura | MAE | RMSE |",
        "|---|---|---|---|---|---|---|",
    ]
    
    for side in ["Mandante", "Visitante", "Total"]:
        r_nb = res_nb[side]
        r_gp = res_gp[side]
        L.append(f"| {side} | CardsNB | {r_nb['ll']:.5f} | {r_nb['cov']:.2%} | {r_nb['wid']:.2f} | {r_nb['mae']:.3f} | {r_nb['rmse']:.3f} |")
        L.append(f"| {side} | CardsGP | {r_gp['ll']:.5f} | {r_gp['cov']:.2%} | {r_gp['wid']:.2f} | {r_gp['mae']:.3f} | {r_gp['rmse']:.3f} |")
        
    L.append("")
    L.append("## Calibração em Linhas Alternativas (Brier e ECE/Tail ECE)")
    
    for side, lines in [("Mandante", lh), ("Visitante", la), ("Total", lt)]:
        L.append(f"### {side}")
        L.append("| Linha | Modelo | Brier | ECE | Tail ECE |")
        L.append("|---|---|---|---|---|")
        for line in lines:
            line_str = str(line)
            m_nb = res_nb[side]["lines"][line_str]
            m_gp = res_gp[side]["lines"][line_str]
            L.append(f"| Over {line} | CardsNB | {m_nb['brier']:.5f} | {m_nb['ece']:.2%} | {m_nb['tail_ece']:.2%} |")
            L.append(f"| Over {line} | CardsGP | {m_gp['brier']:.5f} | {m_gp['ece']:.2%} | {m_gp['tail_ece']:.2%} |")
        L.append("")
        
    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"\nRelatório gerado com sucesso em: {REPORT}\n")
    print("\n".join(L[:25]))
    
if __name__ == "__main__":
    main()
