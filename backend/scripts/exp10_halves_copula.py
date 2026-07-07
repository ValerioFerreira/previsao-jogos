#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp10_halves_copula.py — Hipótese: gols do 1º x 2º tempo são correlacionados?
=====================================================================================
Os modelos de meio-tempo (gols_1t_nb, gols_2t_nb) preveem os tempos de forma INDEPENDENTE.
Testa a dependência entre o TOTAL de gols do 1º tempo e do 2º tempo via cópula gaussiana
(mesmo método do EXP7), point-in-time. Se correlacionados, combos "gols nos dois tempos" /
"placar por tempo" são precificados errado assumindo independência.
Métrica: NLL conjunto (1º+2º) independente vs cópula, CV temporal. Saída: docs/EXP10_*.md.
"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, joblib
from scipy.stats import norm
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
ART = ROOT / "model_artifacts"; CSV = ROOT / "international_features_enriched_apifootball.csv"


def mid_pit(pmf, obs):
    cdf = np.cumsum(pmf, axis=1); k = np.clip(obs.astype(int), 0, pmf.shape[1] - 1); idx = np.arange(len(obs))
    Fk = cdf[idx, k]; Fk1 = np.where(k > 0, cdf[idx, np.maximum(k - 1, 0)], 0.0)
    return np.clip(0.5 * (Fk + Fk1), 1e-4, 1 - 1e-4), np.clip(pmf[idx, k], 1e-9, None)


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    ht = pd.read_parquet(ROOT / "data" / "built" / "halftime_targets.parquet"); ht["date"] = pd.to_datetime(ht["date"])
    d = df.merge(ht, on=["date", "home_team", "away_team"], how="inner").dropna(
        subset=["home_goals_1t", "away_goals_1t", "home_goals_2t", "away_goals_2t"]).sort_values("date").reset_index(drop=True)
    bf = joblib.load(ART / "gols_1t_nb.joblib").feats
    m1 = joblib.load(ART / "gols_1t_nb.joblib"); m2 = joblib.load(ART / "gols_2t_nb.joblib")
    p1 = m1.predict_distributions(d[bf])["total"]; p2 = m2.predict_distributions(d[bf])["total"]
    o1 = (d.home_goals_1t + d.away_goals_1t).astype(int).values; o2 = (d.home_goals_2t + d.away_goals_2t).astype(int).values
    u1, q1 = mid_pit(p1, o1); u2, q2 = mid_pit(p2, o2)
    d["_z0"] = norm.ppf(u1); d["_z1"] = norm.ppf(u2); d["_lp"] = np.log(q1) + np.log(q2)
    print(f"jogos: {len(d)} | corr(z1t, z2t) global = {np.corrcoef(d._z0, d._z1)[0,1]:+.3f}", flush=True)

    cuts = np.linspace(0.5, 0.85, 4); rows = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 80: continue
        S = np.corrcoef(tr[["_z0", "_z1"]].values.T); Sinv = np.linalg.inv(S); _, logdet = np.linalg.slogdet(S)
        Zte = te[["_z0", "_z1"]].values
        quad = np.einsum("ij,jk,ik->i", Zte, (Sinv - np.eye(2)), Zte)
        log_c = -0.5 * logdet - 0.5 * quad
        ni = -te["_lp"].values; nc = ni - log_c
        rows.append(dict(fold=round(c, 2), nll_indep=ni.mean(), nll_cop=nc.mean(), dNLL=(nc - ni).mean(), corr_z=S[0, 1]))
    R = pd.DataFrame(rows)
    print(R.to_string(index=False))
    dn = R.dNLL.mean()
    print(f">> dNLL {dn:+.4f} (cópula melhora {int((R.dNLL<0).sum())}/{len(R)}) | corr média {R.corr_z.mean():+.3f} | "
          f"VEREDITO: {'APROVADO' if (dn<0 and int((R.dNLL<0).sum())>=len(R)-1) else 'REPROVADO'}")


if __name__ == "__main__":
    main()
