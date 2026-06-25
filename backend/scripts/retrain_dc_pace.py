#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retreino cirúrgico do Dixon-Coles com as features de PACE (grupo P do estudo).
Adiciona pace ao CSV, confirma o ganho num holdout, retreina o DC na base completa,
atualiza model_artifacts/{dixon_coles_goals.joblib, meta.json}. Não toca os demais
artefatos (clf_*, qm, snapshot)."""
import json, warnings, contextlib, io
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import nbinom
from sklearn.metrics import log_loss
from dixon_coles_model import DixonColesNBRegressor

warnings.filterwarnings("ignore")
RS, M = 42, 12
CSV = "international_features_enriched_apifootball.csv"
ART = Path("model_artifacts")
PACE = ["pace_gf", "pace_ga", "pace_total", "btts_sum"]


def add_pace(df):
    df["pace_gf"] = df["home_gf_l10"] + df["away_gf_l10"]
    df["pace_ga"] = df["home_ga_l10"] + df["away_ga_l10"]
    df["pace_total"] = df["pace_gf"] + df["pace_ga"]
    df["btts_sum"] = df["home_bttsrate_l10"] + df["away_bttsrate_l10"]
    return df


def fit(df, feats):
    dc = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=M, random_state=RS)
    with contextlib.redirect_stdout(io.StringIO()):
        dc.fit(df[feats], df["home_score"], df["away_score"])
    return dc


def btts(dc, df, feats):
    return dc.predict_proba_markets(df[feats])["btts"]


def ll(y, p): return float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]))


def main():
    df = pd.read_csv(CSV, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df = add_pace(df)

    meta = json.loads((ART / "meta.json").read_text(encoding="utf-8"))
    base = meta["base_feats"]
    new_base = base + [c for c in PACE if c not in base]
    new_full = meta["full_feats"] + [c for c in PACE if c not in meta["full_feats"]]
    print(f"base_feats: {len(base)} -> {len(new_base)} (+{len(new_base)-len(base)} pace)")

    # ---- confirmação em holdout (mesmo split do projeto) ----
    adv = df[df["has_advanced_stats"] == 1]
    cut = adv.iloc[int(len(adv) * 0.8)]["date"]
    tr = df[df["date"] <= cut]; te = df[(df["date"] > cut) & (df["has_advanced_stats"] == 1)]
    yte = te["btts"].astype(int).values
    ll_base = ll(yte, btts(fit(tr, base), te, base))
    ll_pace = ll(yte, btts(fit(tr, new_base), te, new_base))
    print(f"HOLDOUT BTTS log-loss: base={ll_base:.5f} | base+pace={ll_pace:.5f} | delta={ll_pace-ll_base:+.5f}")

    # ---- treino FINAL na base completa e salvar ----
    print(f"Treinando DC final na base completa (N={len(df)})...")
    dc = fit(df, new_base)
    dc.save(ART / "dixon_coles_goals.joblib")
    meta["base_feats"] = new_base
    meta["full_feats"] = new_full
    (ART / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_csv(CSV, index=False)  # CSV agora com pace (consistente p/ Neon e rebuilds)
    print("Salvos: dixon_coles_goals.joblib + meta.json (+pace) e CSV atualizado.")


if __name__ == "__main__":
    main()
