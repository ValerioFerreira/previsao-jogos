#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp13_goals_counts_copula.py — dependência CRUZADA gols × contagens ofensivas
=====================================================================================
Hipótese: gols (resultado/DC) e contagens ofensivas (finalizações, escanteios) partilham
domínio territorial — um time que domina gera contagens E marca mais do que os modelos,
tratados como INDEPENDENTES, preveem em conjunto. Isso afeta combos MISTOS do "Monte sua
Aposta" (ex.: "time vence" + "mais de X escanteios"). Cópula gaussiana sobre gols totais (DC),
finalizações e escanteios; NLL conjunto independente vs cópula, CV temporal (método EXP7).
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from scipy.stats import norm
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from ortho_sinais import apply_ortho_residuals
from corner_interactions import add_corner_interactions
ART = ROOT / "model_artifacts"; CSV = ROOT / "international_features_enriched_apifootball.csv"
META = __import__("json").load(open(ART / "meta.json", encoding="utf-8"))
BASE = [f for f in META["base_feats"]]
ORTHO_W = joblib.load(ART / "style_ortho_weights.joblib")
OOF = pd.read_csv(ROOT / "data" / "built" / "oof_shots.csv")


def enrich(te):
    te = apply_ortho_residuals(te, ORTHO_W); te = te.merge(OOF, on="match_id", how="left")
    if "pred_home_shots_oof" in te.columns:
        te["pred_home_shots"] = te["pred_home_shots_oof"]; te["pred_away_shots"] = te["pred_away_shots_oof"]
    return add_corner_interactions(te)


def mid_pit(pmf, obs):
    cdf = np.cumsum(pmf, axis=1); k = np.clip(obs.astype(int), 0, pmf.shape[1] - 1); idx = np.arange(len(obs))
    Fk = cdf[idx, k]; Fk1 = np.where(k > 0, cdf[idx, np.maximum(k - 1, 0)], 0.0)
    return np.clip(0.5 * (Fk + Fk1), 1e-4, 1 - 1e-4), np.clip(pmf[idx, k], 1e-9, None)


def dc_total_goals_pmf(dc, X):
    J = dc.predict_proba_markets(X)["joint"]  # (N, G+1, G+1)
    G = J.shape[1] - 1
    N = J.shape[0]; tot = np.zeros((N, 2 * G + 1))
    for s in range(2 * G + 1):
        for x in range(max(0, s - G), min(G, s) + 1):
            tot[:, s] += J[:, x, s - x]
    return tot / tot.sum(1, keepdims=True)


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_shots", "away_cur_sb_shots", "home_cur_sb_corners", "away_cur_sb_corners", "home_score", "away_score"]).copy()
    adv = enrich(adv).sort_values("date").reset_index(drop=True)
    base_in = [c for c in BASE if c in adv.columns]
    dc = joblib.load(ART / "dixon_coles_goals.joblib")
    sh = joblib.load(ART / "shots_nb.joblib"); co = joblib.load(ART / "corners_cascade_rfixo.joblib")
    pg = dc_total_goals_pmf(dc, adv[base_in])
    psh = sh.predict_distributions(adv[sh.feats])["total"]; pco = co.predict_distributions(adv[co.feats])["total"]
    og = (adv.home_score + adv.away_score).astype(int).values
    osh = (adv.home_cur_sb_shots + adv.away_cur_sb_shots).astype(int).values
    oco = (adv.home_cur_sb_corners + adv.away_cur_sb_corners).astype(int).values
    ug, qg = mid_pit(pg, og); ush, qsh = mid_pit(psh, osh); uco, qco = mid_pit(pco, oco)
    adv["_z0"] = norm.ppf(ug); adv["_z1"] = norm.ppf(ush); adv["_z2"] = norm.ppf(uco)
    adv["_lp"] = np.log(qg) + np.log(qsh) + np.log(qco)
    Z = adv[["_z0", "_z1", "_z2"]].values
    print("mercados: [gols_total, finalizacoes, escanteios]")
    print("corr(z) global:\n", np.round(np.corrcoef(Z.T), 3), flush=True)

    cuts = np.linspace(0.5, 0.85, 4); rows = []
    for c in cuts:
        n = int(len(adv) * c); m = int(len(adv) * min(c + 0.15, 1.0))
        tr, te = adv.iloc[:n], adv.iloc[n:m]
        if len(te) < 80: continue
        S = np.corrcoef(tr[["_z0", "_z1", "_z2"]].values.T); Sinv = np.linalg.inv(S); _, logdet = np.linalg.slogdet(S)
        Zte = te[["_z0", "_z1", "_z2"]].values
        log_c = -0.5 * logdet - 0.5 * np.einsum("ij,jk,ik->i", Zte, (Sinv - np.eye(3)), Zte)
        ni = -te["_lp"].values; nc = ni - log_c
        rows.append(dict(fold=round(c, 2), dNLL=(nc - ni).mean(),
                         corr_g_sh=S[0, 1], corr_g_co=S[0, 2], corr_sh_co=S[1, 2]))
    R = pd.DataFrame(rows); print(R.to_string(index=False))
    dn = R.dNLL.mean()
    print(f">> dNLL {dn:+.4f} (cópula melhora {int((R.dNLL<0).sum())}/{len(R)}) | "
          f"corr gols↔fin {R.corr_g_sh.mean():+.3f} gols↔esc {R.corr_g_co.mean():+.3f} | "
          f"VEREDITO: {'APROVADO' if (dn<0 and int((R.dNLL<0).sum())>=len(R)-1) else 'REPROVADO'}")


if __name__ == "__main__":
    main()
