#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/train_possession_market.py
====================================
Mercado novo: POSSE DE BOLA -- Grupo 1 custo A do docs/PLANO_EXPANSAO_MERCADOS.md
(`home_cur_sb_possession` ja e coluna pronta). Posse NAO e contagem (soma-zero,
home+away=100) -- arquitetura DIFERENTE da cascata CornersNB usada nos outros
mercados: regressao Beta (media via GradientBoostingRegressor sobre base_feats,
precisao/phi por metodo dos momentos no residuo do treino). Visitante e
complemento (1 - home). Mercado: "Over/Under 50,5% de posse do mandante".

Cru ate passar por gate proprio (a metrica pmf_logloss do gate_count_market.py
nao serve pra Beta -- comparar log-loss Bernoulli em Over/Under 50,5% contra
baseline de media global e media rolante, mesmo espirito do gate §6-C).

Uso: python -m scripts.train_possession_market --scope clube
"""
import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from scipy.stats import beta as beta_dist
from sklearn.ensemble import GradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.battery_dataset import load_clubs_df  # noqa: E402

CONFIG = {
    "selecao": {
        "csv": ROOT / "international_features_enriched_apifootball.csv",
        "art": ROOT / "model_artifacts",
    },
    "clube": {
        "csv": ROOT / "data" / "built" / "club_features_enriched.parquet",
        "art": ROOT / "model_artifacts_clubes",
    },
}

EPS = 0.02  # clip de borda (0%/100% de posse sao impossiveis na pratica)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], required=True)
    a = ap.parse_args()
    cfg = CONFIG[a.scope]

    meta = json.load(open(cfg["art"] / "meta.json", encoding="utf-8"))
    base_feats = meta["base_feats"]

    if a.scope == "clube":
        df = load_clubs_df(min_matches=0)
    else:
        df = pd.read_csv(cfg["csv"], low_memory=False)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    base_feats = [f for f in base_feats if f in df.columns]

    d = df.dropna(subset=["home_cur_sb_possession"]).copy()
    p = (d["home_cur_sb_possession"].astype(float) / 100.0).clip(EPS, 1 - EPS).values
    print(f"[{a.scope}] N={len(d)} | posse media mandante {p.mean()*100:.2f}%", flush=True)

    X = d[base_feats].fillna(d[base_feats].median(numeric_only=True))
    reg = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
    reg.fit(X, p)
    mu_hat = np.clip(reg.predict(X), EPS, 1 - EPS)

    resid_var = float(np.var(p - mu_hat))
    mu_bar = float(mu_hat.mean())
    var_binomial = mu_bar * (1 - mu_bar)
    phi = max(var_binomial / max(resid_var, 1e-6) - 1.0, 2.0)  # precisao Beta, piso 2.0

    a_par, b_par = mu_hat * phi, (1 - mu_hat) * phi
    over_prob = 1 - beta_dist.cdf(0.505, a_par, b_par)
    print(f"  phi(precisao)={phi:.2f} | P(posse mandante > 50,5%) media in-sample: {over_prob.mean()*100:.1f}%", flush=True)

    out = cfg["art"] / "possession_beta.joblib"
    joblib.dump({"regressor": reg, "phi": phi, "feats": base_feats}, out)
    print(f"  salvo: {out}", flush=True)


if __name__ == "__main__":
    main()
